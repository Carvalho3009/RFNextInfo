from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .protected_state import protect, unprotect


MAX_RESPONSE_BYTES = 8 * 1024 * 1024
ALL_SITE_FEATURES = frozenset({
    "character",
    "market",
    "codex",
    "memory_chips",
    "inventory",
    "subsession",
    "export",
    "observations",
    "pve-observations",
    "exp-ranking",
    "auction-bank",
    "pvp-sync",
})


class SiteProfileClient:
    def __init__(
        self,
        state_dir: Path,
        server: str = "https://rfnext.karvalho.dev.br",
        version: str = "unknown",
        legacy_paths: tuple[Path, ...] = (),
        features: frozenset[str] | set[str] | tuple[str, ...] = ALL_SITE_FEATURES,
    ) -> None:
        self.path = Path(state_dir) / "site-profile.dat"
        self.server = server.rstrip("/")
        self.user_agent = f"RFQOL/{version}"
        self.features = frozenset(str(feature) for feature in features)
        self.state = self._load()
        if not self.state:
            for legacy_path in map(Path, legacy_paths):
                legacy_state = self._load_path(legacy_path)
                if legacy_state:
                    self.state = legacy_state
                    self._save()
                    break

    def _load(self) -> dict[str, str]:
        return self._load_path(self.path)

    @staticmethod
    def _load_path(path: Path) -> dict[str, str]:
        try:
            state = json.loads(unprotect(path.read_bytes()))
            if state.get("profile") and state.get("token"):
                return state
        except (OSError, ValueError):
            pass
        return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(
            protect(json.dumps(self.state, separators=(",", ":")).encode())
        )
        os.replace(temporary, self.path)

    @property
    def profile(self) -> str:
        return self.state.get("profile", "")

    @property
    def connected(self) -> bool:
        return bool(self.profile and self.state.get("token"))

    def connect(self, profile: str, token: str) -> dict:
        profile, token = profile.strip(), token.strip()
        if not profile or not 20 <= len(token) <= 256:
            raise ValueError("Profile ou token inválido")
        result = self._request(
            "/api/profile-token/validate",
            json.dumps({"profile": profile}).encode(),
            token,
            "application/json",
        )
        if result.get("profile") != profile:
            raise ValueError("O token pertence a outro Profile")
        self.state = {"profile": profile, "token": token}
        self._save()
        return result

    def disconnect(self) -> None:
        self.state = {}
        self.path.unlink(missing_ok=True)

    def allows(self, feature: str) -> bool:
        return str(feature) in self.features

    def _require_feature(self, feature: str) -> None:
        if not self.allows(feature):
            labels = {
                "market": "Mercado",
                "exp-ranking": "Ranking de EXP",
                "auction-bank": "Banco de Leilão",
            }
            enabled = sorted(
                labels[feature]
                for feature in self.features
                if feature in labels
            )
            raise ValueError(
                "Nesta versão, a integração com o site está liberada somente para "
                + " e ".join(enabled)
            )

    def upload(self, path: Path, idempotency_key: str) -> dict:
        self._require_feature("export")
        if not self.connected:
            raise ValueError("Conecte o token do Profile antes de enviar")
        envelope = json.loads(Path(path).read_text(encoding="utf-8"))
        metadata = envelope.get("metadata") or {}
        payload = {
            "metadata": metadata,
            "profiles": envelope.get("profiles") or [],
            "capture": envelope.get("capture") or {},
            "subsession_reports": metadata.get("subsession_reports") or [],
        }
        return self._request(
            "/api/import/farm-session",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
            self.state["token"],
            "application/json",
            idempotency_key,
        )

    def upload_live(
        self, mode: str, payload: dict, idempotency_key: str
    ) -> dict:
        if mode not in {
            "character",
            "market",
            "codex",
            "memory_chips",
            "inventory",
            "subsession",
        }:
            raise ValueError("Tipo de envio inválido")
        self._require_feature(mode)
        if not self.connected:
            raise ValueError("Conecte o token do Profile antes de enviar")
        if mode == "market":
            groups: dict[int, list[dict]] = {}
            for row in payload.get("rows") or []:
                groups.setdefault(int(row.get("ServerType", 0)), []).append(row)
            responses = []
            for server_type, rows in sorted(groups.items()):
                grouped = {
                    **payload,
                    "metadata": {
                        **(payload.get("metadata") or {}),
                        "market_server_type": server_type,
                    },
                    "rows": rows,
                }
                key = hashlib.sha256(
                    f"{idempotency_key}:{server_type}".encode()
                ).hexdigest()
                responses.append(self._request(
                    "/api/import/market",
                    json.dumps(grouped, ensure_ascii=False, separators=(",", ":")).encode(),
                    self.state["token"],
                    "application/json",
                    key,
                ))
            if responses:
                return {
                    "receipt": ", ".join(str(item.get("receipt", "")) for item in responses),
                    "server_types": sorted(groups),
                    "responses": responses,
                }
        return self._request(
            (
                "/api/import/market"
                if mode == "market"
                else "/api/import/farm-session"
            ),
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode(),
            self.state["token"],
            "application/json",
            idempotency_key,
        )

    def upload_observations(self, payload: dict, idempotency_key: str) -> dict:
        self._require_feature("observations")
        if not self.connected:
            raise ValueError("Conecte o token do Profile antes de enviar")
        return self._request(
            "/api/import/observations",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
            self.state["token"],
            "application/json",
            idempotency_key,
        )

    def upload_pve_observations(self, payload: dict, idempotency_key: str) -> dict:
        self._require_feature("pve-observations")
        if not self.connected:
            raise ValueError("Conecte o token do Profile antes de enviar")
        return self._request(
            "/api/import/pve-observations",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
            self.state["token"],
            "application/json",
            idempotency_key,
        )

    def upload_exp_rank(self, payload: dict, idempotency_key: str) -> dict:
        self._require_feature("exp-ranking")
        if not self.connected:
            raise ValueError("Conecte o token do Profile antes de enviar")
        return self._request(
            "/api/import/exp-rank",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
            self.state["token"],
            "application/json",
            idempotency_key,
        )

    def upload_auction_bank(self, payload: dict, idempotency_key: str) -> dict:
        self._require_feature("auction-bank")
        if not self.connected:
            raise ValueError("Conecte o token do Profile antes de enviar")
        return self._request(
            "/api/import/auction-bank",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
            self.state["token"],
            "application/json",
            idempotency_key,
        )

    def download_observations(self) -> dict:
        self._require_feature("pvp-sync")
        if not self.connected:
            raise ValueError("Conecte o token do Profile antes de receber")
        return self._request(
            "/api/pvp-sync/final",
            None,
            self.state["token"],
            "",
            method="GET",
        )

    def _request(
        self,
        route: str,
        body: bytes | None,
        token: str,
        content_type: str,
        idempotency_key: str = "",
        method: str = "POST",
    ) -> dict:
        if not self.server:
            raise ValueError(
                "Integração com o site está desativada no perfil de homologação"
            )
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": self.user_agent,
        }
        if content_type:
            headers["Content-Type"] = content_type
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = urllib.request.Request(
            self.server + route,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
                if len(payload) > MAX_RESPONSE_BYTES:
                    raise ValueError("A resposta do site excedeu o limite seguro")
                try:
                    result = json.loads(payload)
                except (TypeError, ValueError):
                    raise ValueError(
                        "O site respondeu com uma página de acesso em vez da API. "
                        "Atualize o programa ou tente novamente mais tarde."
                    ) from None
                if not isinstance(result, dict):
                    raise ValueError("Resposta inválida do site")
                return result
        except urllib.error.HTTPError as error:
            try:
                response = json.loads(error.read(32 * 1024))
                detail = response.get("error") or response.get("detail") or ""
            except (OSError, ValueError, AttributeError):
                detail = ""
            raise ValueError(detail or f"Operação recusada (HTTP {error.code})") from None
        except urllib.error.URLError as error:
            raise ValueError("Não foi possível alcançar o site") from error
        except TimeoutError:
            raise ValueError(
                "O site não confirmou a operação em 20 segundos. "
                "Se era um envio, os dados podem ter sido recebidos; aguarde antes de reenviar."
            ) from None
