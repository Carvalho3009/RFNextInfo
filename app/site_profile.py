from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .protected_state import protect, unprotect


class SiteProfileClient:
    def __init__(
        self,
        state_dir: Path,
        server: str = "https://rfnext.karvalho.dev.br",
        version: str = "unknown",
    ) -> None:
        self.path = Path(state_dir) / "site-profile.dat"
        self.server = server.rstrip("/")
        self.user_agent = f"RFNextInfo/{version}"
        self.state = self._load()

    def _load(self) -> dict[str, str]:
        try:
            state = json.loads(unprotect(self.path.read_bytes()))
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

    def upload(self, path: Path, idempotency_key: str) -> dict:
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
        if not self.connected:
            raise ValueError("Conecte o token do Profile antes de enviar")
        if mode not in {
            "character",
            "market",
            "codex",
            "memory_chips",
            "subsession",
        }:
            raise ValueError("Tipo de envio inválido")
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

    def _request(
        self,
        route: str,
        body: bytes,
        token: str,
        content_type: str,
        idempotency_key: str = "",
    ) -> dict:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
            "User-Agent": self.user_agent,
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = urllib.request.Request(
            self.server + route,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read(64 * 1024)
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
            raise ValueError(detail or f"Envio recusado (HTTP {error.code})") from None
        except urllib.error.URLError as error:
            raise ValueError("Não foi possível alcançar o site") from error
        except TimeoutError:
            raise ValueError(
                "O site não confirmou o envio em 20 segundos. "
                "Os dados podem ter sido recebidos; aguarde antes de reenviar."
            ) from None
