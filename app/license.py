from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .protected_state import protect, unprotect

KEY_RE = re.compile(r"^KRV(?:-[A-Z2-7]{5}){6}$")


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


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


def verify_lease(lease: str, public_key: str) -> dict:
    payload, signature = lease.split(".", 1)
    raw = _b64(payload)
    Ed25519PublicKey.from_public_bytes(_b64(public_key)).verify(_b64(signature), raw)
    claims = json.loads(raw)
    required = {"v", "iss", "license_id", "installation_id", "valid_until", "next_check_at"}
    if (
        claims.get("v") != 1
        or claims.get("iss") != "rflicenca.karvalho.dev.br"
        or not required.issubset(claims)
    ):
        raise ValueError("Comprovante de licença inválido")
    return claims


class LicenseClient:
    def __init__(
        self,
        state_dir: Path,
        server: str = "https://rflicenca.karvalho.dev.br",
        version: str = "unknown",
        legacy_paths: tuple[Path, ...] = (),
    ) -> None:
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / "license.dat"
        self.backup_path = self.state_dir / "license.backup.dat"
        self.server = server.rstrip("/")
        self.user_agent = f"RFNextInfo/{version}"
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
        legacy_json = [
            self.state_dir / "license.json",
            self.state_dir / "license.backup.json",
        ]
        legacy_protected = []
        for legacy_path in map(Path, legacy_paths):
            if legacy_path.suffix == ".dat":
                legacy_protected.extend(
                    (
                        legacy_path,
                        legacy_path.with_name("license.backup.dat"),
                    )
                )
            else:
                legacy_json.extend(
                    (
                        legacy_path,
                        legacy_path.with_name("license.backup.json"),
                    )
                )
        migrated = False
        if not self.lease:
            for legacy_path in dict.fromkeys(legacy_protected):
                legacy_state = self._read_protected(legacy_path)
                if legacy_state and legacy_state.get("lease"):
                    self.state = legacy_state
                    migrated = True
                    self.load_status = "migrated"
                    break
        if not self.lease:
            for legacy_path in dict.fromkeys(legacy_json):
                legacy_state = self._read_json(legacy_path)
                if legacy_state and legacy_state.get("lease"):
                    self.state = legacy_state
                    migrated = True
                    self.load_status = "migrated"
                    break
        if self.lease:
            try:
                self._sync_dates(self.claims())
            except Exception:
                self.load_status = "invalid"
        if primary is None and (self.lease or not self.path.exists()):
            self._save()
        if migrated:
            for legacy_path in dict.fromkeys(legacy_json):
                legacy_state = self._read_json(legacy_path)
                if (
                    legacy_state
                    and legacy_state.get("installation_id")
                    == self.installation_id
                ):
                    legacy_path.unlink(missing_ok=True)

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and value.get("installation_id"):
                return value
        except (OSError, ValueError):
            pass
        return None

    @classmethod
    def _read_protected(cls, path: Path) -> dict | None:
        try:
            value = json.loads(unprotect(path.read_bytes()))
            if isinstance(value, dict) and value.get("installation_id"):
                return value
        except (OSError, ValueError):
            pass
        return None

    def _sync_dates(self, claims: dict) -> None:
        self.state.update(
            license_started_at=claims.get(
                "license_starts_at", claims.get("issued_at")
            ),
            license_expires_at=claims.get(
                "license_expires_at", claims.get("valid_until")
            ),
            next_check_at=claims.get("next_check_at"),
            offline_valid_until=claims.get("valid_until"),
        )

    def _save(self) -> None:
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
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
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
            return json.loads(response.read(32 * 1024))

    def activate(self, key: str, version: str) -> dict:
        key = key.strip().upper()
        if not KEY_RE.fullmatch(key):
            raise ValueError("Formato inválido. Use KRV-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX.")
        try:
            public = self._json("/api/v1/public-key")
            response = self._json("/api/v1/activate", {
                "license_key": key,
                "installation_id": self.state["installation_id"],
                "app_version": version,
            })
        except urllib.error.HTTPError as error:
            raise ValueError(_activation_error(error)) from None
        claims = verify_lease(response["lease"], public["public_key"])
        if claims["installation_id"] != self.state["installation_id"]:
            raise ValueError("Servidor vinculou outra instalação")
        self.state.update(lease=response["lease"], public_key=public["public_key"])
        self._sync_dates(claims)
        self._save()
        return claims

    def refresh_if_due(self, version: str) -> tuple[bool, str]:
        try:
            claims = self.claims()
        except Exception:
            return False, "Ative uma licença para iniciar capturas."
        now = datetime.now(timezone.utc)
        if now < _utc(claims["next_check_at"]):
            return now <= _utc(claims["valid_until"]), "Licença válida."
        try:
            response = self._json("/api/v1/validate", {
                "lease": self.state["lease"], "app_version": version
            })
            claims = verify_lease(response["lease"], self.state["public_key"])
            if claims["installation_id"] != self.installation_id:
                raise ValueError("Servidor vinculou outra instalação")
            self.state["lease"] = response["lease"]
            self._sync_dates(claims)
            self._save()
            return True, "Licença validada agora."
        except urllib.error.HTTPError:
            return False, "Licença inativa, expirada ou revogada."
        except (OSError, urllib.error.URLError, ValueError, KeyError):
            if now <= _utc(claims["valid_until"]):
                return True, f"Servidor indisponível; prazo offline até {claims['valid_until']}."
            return False, "Prazo offline encerrado. Exporte os dados ou conecte para validar."

    def claims(self) -> dict:
        claims = verify_lease(self.state["lease"], self.state["public_key"])
        if claims["installation_id"] != self.installation_id:
            raise ValueError("Comprovante pertence a outra instalação")
        return claims

    def upload_diagnostic(self, path: Path, version: str) -> dict:
        if not self.lease:
            raise ValueError("Ative a licença antes de enviar o diagnóstico")
        raw = Path(path).read_bytes()
        if len(raw) > 5 * 1024 * 1024:
            raise ValueError("Diagnóstico excede o limite de 5 MiB")
        diagnostic = json.loads(raw)
        return self._json(
            "/api/v1/diagnostics",
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
