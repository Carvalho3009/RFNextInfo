from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .protected_state import protect, unprotect

KEY_RE = re.compile(r"^RFQ(?:-[A-Z2-7]{5}){6}$")
ISSUER = "rflicenca.karvalho.dev.br"
PRODUCT = "rf-qol"
AUDIENCE = "rf-qol-windows"
MAX_OFFLINE = timedelta(hours=24)
MAX_NEXT_CHECK = timedelta(hours=6)
CLOCK_SKEW = timedelta(minutes=5)
FEATURE_ORDER = ("base", "monitor-pve", "monitor-pvp", "monitor-boss")
FEATURE_SET = frozenset(FEATURE_ORDER)
CONNECTION_TIERS = (
    {"pc": 2, "emulators": 1},
    {"pc": 2, "emulators": 5},
)

# Pública definitiva de lease; a privada correspondente permanece fora do
# repositório e do cliente, sob custódia exclusiva do emissor.
LEASE_PUBLIC_KEYS = {
    "lease-2026-01": "xZgKtYVUkbKkisEe8qwvFKD72FVsu8sXN3KVC5EGeJ8",
}


def validate_release_configuration() -> None:
    if any(key.endswith("-pending") for key in LEASE_PUBLIC_KEYS):
        raise RuntimeError("Chave pública de lease de produção ainda não foi instalada")


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Data sem fuso horário")
    return parsed.astimezone(timezone.utc)


def _b64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _activation_error(error: urllib.error.HTTPError) -> str:
    try:
        detail = json.loads(error.read(32 * 1024)).get("detail", "")
    except (OSError, ValueError, AttributeError):
        detail = ""
    ray = error.headers.get("CF-Ray", "") if error.headers else ""
    reference = f", CF-Ray {ray}" if ray else ""
    return f"{detail or 'servidor recusou a ativação'} (HTTP {error.code}{reference})"


def _features(value) -> list[str]:
    if not isinstance(value, list) or (
        not value
        or any(not isinstance(feature, str) for feature in value)
        or len(value) != len(set(value))
        or "base" not in value
        or not set(value).issubset(FEATURE_SET)
    ):
        raise ValueError("Módulos inválidos")
    normalized = [feature for feature in FEATURE_ORDER if feature in value]
    if value != normalized:
        raise ValueError("Ordem de módulos inválida")
    return normalized


def _connection_limits(value) -> dict[str, int]:
    if (
        not isinstance(value, dict)
        or set(value) != {"pc", "emulators"}
        or type(value["pc"]) is not int
        or type(value["emulators"]) is not int
        or value not in CONNECTION_TIERS
    ):
        raise ValueError("Limites de conexão inválidos")
    return dict(value)


def verify_lease(
    lease: str,
    public_keys: dict[str, str] | str = LEASE_PUBLIC_KEYS,
    *,
    installation_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Valida assinatura, papel, produto, instalação e janela da lease v2."""
    try:
        payload, signature = lease.split(".", 1)
        raw = _b64(payload)
        if len(raw) > 32 * 1024:
            raise ValueError
        claims = json.loads(raw)
        if not isinstance(claims, dict):
            raise ValueError
        required = {
            "v",
            "iss",
            "product",
            "aud",
            "key_id",
            "lease_id",
            "license_id",
            "installation_id",
            "issued_at",
            "next_check_at",
            "valid_until",
            "entitlement_expires_at",
            "features",
            "connection_limits",
        }
        if set(claims) != required:
            raise ValueError
        key_id = claims["key_id"]
        if not isinstance(key_id, str) or not key_id.startswith("lease-"):
            raise ValueError
        public_key = (
            public_keys
            if isinstance(public_keys, str)
            else public_keys.get(key_id)
        )
        if not public_key:
            raise ValueError
        Ed25519PublicKey.from_public_bytes(_b64(public_key)).verify(
            _b64(signature), raw
        )
        if (
            claims["v"] != 2
            or claims["iss"] != ISSUER
            or claims["product"] != PRODUCT
            or claims["aud"] != AUDIENCE
        ):
            raise ValueError
        _features(claims["features"])
        _connection_limits(claims["connection_limits"])
        for field in ("lease_id", "license_id", "installation_id"):
            if not isinstance(claims[field], str) or not 1 <= len(claims[field]) <= 200:
                raise ValueError
        if str(uuid.UUID(claims["installation_id"])) != claims["installation_id"].lower():
            raise ValueError
        if installation_id is not None and claims["installation_id"] != installation_id:
            raise ValueError
        issued = _utc(claims["issued_at"])
        next_check = _utc(claims["next_check_at"])
        valid_until = _utc(claims["valid_until"])
        entitlement = _utc(claims["entitlement_expires_at"])
        if not issued <= next_check <= valid_until <= entitlement:
            raise ValueError
        if next_check - issued > MAX_NEXT_CHECK or valid_until - issued > MAX_OFFLINE:
            raise ValueError
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if issued > current + CLOCK_SKEW or current > valid_until:
            raise ValueError
        return claims
    except Exception as error:
        raise ValueError("Comprovante de licença inválido") from error


class LicenseClient:
    def __init__(
        self,
        state_dir: Path,
        server: str = "https://rflicenca.karvalho.dev.br",
        version: str = "unknown",
        trusted_public_keys: dict[str, str] | None = None,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / "license.dat"
        self.backup_path = self.state_dir / "license.backup.dat"
        self.server = server.rstrip("/")
        self.user_agent = f"RFQOL/{version}"
        self.trusted_public_keys = dict(trusted_public_keys or LEASE_PUBLIC_KEYS)
        self._validated_online = False
        primary = self._read_protected(self.path)
        backup = self._read_protected(self.backup_path)
        self.load_status = (
            "primary"
            if primary
            else "backup"
            if backup
            else "corrupt"
            if self.path.exists() or self.backup_path.exists()
            else "none"
        )
        self.state = primary or backup or {"installation_id": str(uuid.uuid4())}
        removed_mutable_key = self.state.pop("public_key", None) is not None
        if self.lease:
            try:
                self._sync_dates(self.claims())
            except ValueError:
                self.load_status = "invalid"
        if removed_mutable_key or primary is None:
            self._save()

    @staticmethod
    def _read_protected(path: Path) -> dict | None:
        try:
            value = json.loads(unprotect(path.read_bytes()))
            if isinstance(value, dict) and value.get("installation_id"):
                return value
        except (OSError, ValueError):
            pass
        return None

    def _sync_dates(self, claims: dict) -> None:
        previous = self.state.get("last_server_time")
        issued = claims["issued_at"]
        if not previous or _utc(issued) > _utc(previous):
            self.state["last_server_time"] = issued
        self.state.update(
            license_started_at=issued,
            license_expires_at=claims["entitlement_expires_at"],
            next_check_at=claims["next_check_at"],
            offline_valid_until=claims["valid_until"],
        )

    def _save(self) -> None:
        self.state.pop("public_key", None)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = protect(
            json.dumps(
                self.state, ensure_ascii=False, separators=(",", ":")
            ).encode()
        )
        temporary = self.path.with_name(f"{self.path.name}.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, self.path)
        if self._read_protected(self.path) != self.state:
            raise OSError("estado protegido da licença não foi confirmado")
        try:
            backup = self.backup_path.with_name(f"{self.backup_path.name}.tmp")
            backup.write_bytes(payload)
            os.replace(backup, self.backup_path)
        except OSError:
            pass

    def _json(self, path: str, payload: dict | None = None) -> dict:
        body = None if payload is None else json.dumps(
            payload, separators=(",", ":")
        ).encode()
        request = urllib.request.Request(
            self.server + path,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": self.user_agent,
            },
            method="GET" if body is None else "POST",
        )
        with urllib.request.urlopen(request, timeout=12) as response:
            result = json.loads(response.read(32 * 1024))
        if not isinstance(result, dict):
            raise ValueError("Resposta inválida do servidor de licença")
        return result

    def activate(self, key: str, version: str) -> dict:
        key = key.strip().upper()
        if not KEY_RE.fullmatch(key):
            raise ValueError("Formato inválido. Use RFQ-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX.")
        try:
            response = self._json(
                "/api/v2/activate",
                {
                    "license_key": key,
                    "installation_id": self.installation_id,
                    "app_version": version,
                    "product": PRODUCT,
                    "audience": AUDIENCE,
                },
            )
        except urllib.error.HTTPError as error:
            raise ValueError(_activation_error(error)) from None
        claims = verify_lease(
            response["lease"],
            self.trusted_public_keys,
            installation_id=self.installation_id,
        )
        self.state["lease"] = response["lease"]
        self._sync_dates(claims)
        self._validated_online = True
        self._save()
        return claims

    def refresh_if_due(self, version: str) -> tuple[bool, str]:
        try:
            claims = self.claims()
        except (KeyError, TypeError, ValueError):
            return False, "Ative uma licença válida para usar os recursos protegidos."
        now = datetime.now(timezone.utc)
        if now < _utc(claims["next_check_at"]):
            return True, "Licença válida."
        try:
            response = self._json(
                "/api/v2/validate",
                {
                    "lease": self.lease,
                    "app_version": version,
                    "product": PRODUCT,
                    "audience": AUDIENCE,
                },
            )
            refreshed = verify_lease(
                response["lease"],
                self.trusted_public_keys,
                installation_id=self.installation_id,
            )
            self.state["lease"] = response["lease"]
            self._sync_dates(refreshed)
            self._validated_online = True
            self._save()
            return True, "Licença validada agora."
        except urllib.error.HTTPError:
            self._clear_lease()
            return False, "Licença inativa, expirada ou revogada."
        except (OSError, urllib.error.URLError, ValueError, KeyError):
            self._validated_online = False
            try:
                self.claims(now=now)
            except ValueError:
                return False, "Prazo offline encerrado. Conecte para validar."
            return True, f"Servidor indisponível; prazo offline até {claims['valid_until']}."

    def _clear_lease(self) -> None:
        for field in (
            "lease",
            "license_started_at",
            "license_expires_at",
            "next_check_at",
            "offline_valid_until",
        ):
            self.state.pop(field, None)
        self.load_status = "revoked"
        self._validated_online = False
        self._save()

    def claims(self, *, now: datetime | None = None) -> dict:
        claims = verify_lease(
            self.state["lease"],
            self.trusted_public_keys,
            installation_id=self.installation_id,
            now=now,
        )
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        last_server = self.state.get("last_server_time")
        if last_server and current + CLOCK_SKEW < _utc(last_server):
            raise ValueError("Relógio local requer revalidação online")
        return claims

    def require(self, capability: str, feature: str = "base") -> dict:
        try:
            claims = self.claims()
            if feature not in _features(claims["features"]):
                raise ValueError("módulo ausente")
            return claims
        except (KeyError, TypeError, ValueError) as error:
            label = capability.replace("_", " ")
            raise PermissionError(
                f"Sua licença não permite {label}."
            ) from error

    def local_status(self) -> dict:
        try:
            claims = self.claims()
            return {
                "active": True,
                "state": (
                    "ACTIVE_ONLINE" if self._validated_online else "ACTIVE_OFFLINE"
                ),
                "message": "Licença válida",
                "source": self.load_status,
                "valid_until": claims["valid_until"],
                "next_check_at": claims["next_check_at"],
                "features": claims["features"],
                "connection_limits": claims["connection_limits"],
            }
        except (KeyError, TypeError, ValueError):
            state = self.license_state()
            return {
                "active": False,
                "state": state,
                "message": (
                    "Licença expirada"
                    if state == "EXPIRED"
                    else "Relógio local requer revalidação online"
                    if state == "REVALIDATION_REQUIRED"
                    else "Licença revogada"
                    if state == "REVOKED"
                    else "Comprovante local inválido"
                    if state == "INVALID_STATE"
                    else "Licença ainda não ativada"
                ),
                "source": self.load_status,
                "valid_until": None,
                "next_check_at": None,
                "features": [],
                "connection_limits": {},
            }

    def license_state(self, *, now: datetime | None = None) -> str:
        if self.load_status == "revoked":
            return "REVOKED"
        if not self.lease:
            return (
                "INVALID_STATE"
                if self.load_status in {"corrupt", "invalid"}
                else "UNACTIVATED"
            )
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        last_server = self.state.get("last_server_time")
        try:
            if last_server and current + CLOCK_SKEW < _utc(last_server):
                return "REVALIDATION_REQUIRED"
            self.claims(now=current)
            return "ACTIVE_ONLINE" if self._validated_online else "ACTIVE_OFFLINE"
        except (KeyError, TypeError, ValueError):
            try:
                payload = self.lease.split(".", 1)[0]
                unsigned = json.loads(_b64(payload))
                if current > _utc(unsigned["valid_until"]):
                    return "EXPIRED"
            except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                pass
            return "INVALID_STATE"

    @property
    def highest_release_sequence(self) -> int:
        try:
            return max(0, int(self.state.get("release_sequence", 0)))
        except (TypeError, ValueError):
            return 0

    def record_release_sequence(self, sequence: int) -> None:
        sequence = int(sequence)
        if sequence > self.highest_release_sequence:
            self.state["release_sequence"] = sequence
            self._save()

    def upload_diagnostic(self, path: Path, version: str) -> dict:
        self.require("enviar diagnóstico")
        raw = Path(path).read_bytes()
        if len(raw) > 5 * 1024 * 1024:
            raise ValueError("Diagnóstico excede o limite de 5 MiB")
        diagnostic = json.loads(raw)
        return self._json(
            "/api/v2/diagnostics",
            {
                "lease": self.lease,
                "app_version": version,
                "diagnostic": diagnostic,
            },
        )

    @property
    def lease(self) -> str | None:
        return self.state.get("lease")

    @property
    def installation_id(self) -> str:
        return self.state["installation_id"]
