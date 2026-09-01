"""Identidade criptografica local do Agent Windows."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.protected_state import protect_for_current_user, unprotect


IDENTITY_SCHEMA = "rf-qol.agent-identity/v1"
REGISTRATION_SCHEMA = "rf-qol.installation-registration/v1"
SIGNATURE_CONTEXT = b"RFQOL-INGEST-V1\0"
REGISTRATION_SIGNATURE_CONTEXT = b"RFQOL-REGISTER-V1\0"


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: object) -> bytes:
    if not isinstance(value, str) or len(value) > 512:
        raise ValueError("Campo criptografico invalido")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _installation_id(value: object) -> str:
    result = str(uuid.UUID(str(value)))
    if result != str(value).lower():
        raise ValueError("installation_id invalido")
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


@dataclass(frozen=True)
class AgentIdentity:
    installation_id: str
    key_id: str
    public_key_b64url: str
    created_at: str
    _private_key: Ed25519PrivateKey = field(repr=False)
    _pseudonym_key: bytes = field(repr=False)

    @property
    def pseudonym_key(self) -> bytes:
        return bytes(self._pseudonym_key)

    def sign(self, value: bytes) -> str:
        return _b64(self._private_key.sign(SIGNATURE_CONTEXT + value))

    def registration(self) -> dict[str, str]:
        payload = {
            "schema": REGISTRATION_SCHEMA,
            "installation_id": self.installation_id,
            "key_id": self.key_id,
            "public_key": self.public_key_b64url,
            "created_at": self.created_at,
            "algorithm": "Ed25519",
        }
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return {
            **payload,
            "proof": _b64(self._private_key.sign(
                REGISTRATION_SIGNATURE_CONTEXT + canonical
            )),
        }


class AgentIdentityStore:
    """Cria uma vez e recupera a chave privada somente via DPAPI do usuário."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / "web-agent-identity.dat"
        self.backup_path = self.state_dir / "web-agent-identity.backup.dat"

    @staticmethod
    def _decode(value: bytes, expected_installation_id: str) -> AgentIdentity:
        payload = json.loads(unprotect(value))
        required = {
            "schema", "installation_id", "created_at", "private_key",
            "pseudonym_key",
        }
        if not isinstance(payload, dict) or set(payload) != required:
            raise ValueError("Estado de identidade invalido")
        if payload["schema"] != IDENTITY_SCHEMA:
            raise ValueError("Schema de identidade invalido")
        installation_id = _installation_id(payload["installation_id"])
        if installation_id != expected_installation_id:
            raise ValueError("Identidade pertence a outra instalacao")
        private_bytes = _unb64(payload["private_key"])
        pseudonym_key = _unb64(payload["pseudonym_key"])
        if len(private_bytes) != 32 or len(pseudonym_key) != 32:
            raise ValueError("Tamanho de chave invalido")
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        public_bytes = private_key.public_key().public_bytes_raw()
        key_id = "agent-" + hashlib.sha256(public_bytes).hexdigest()[:24]
        created_at = str(payload["created_at"])
        if len(created_at) > 40 or not created_at.endswith("Z"):
            raise ValueError("Data de identidade invalida")
        return AgentIdentity(
            installation_id=installation_id,
            key_id=key_id,
            public_key_b64url=_b64(public_bytes),
            created_at=created_at,
            _private_key=private_key,
            _pseudonym_key=pseudonym_key,
        )

    @classmethod
    def _read(
        cls, path: Path, expected_installation_id: str
    ) -> AgentIdentity | None:
        try:
            return cls._decode(path.read_bytes(), expected_installation_id)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def _atomic_write(self, path: Path, value: bytes) -> None:
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(value)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)

    def _save(self, identity: AgentIdentity) -> None:
        private_bytes = identity._private_key.private_bytes_raw()
        payload = {
            "schema": IDENTITY_SCHEMA,
            "installation_id": identity.installation_id,
            "created_at": identity.created_at,
            "private_key": _b64(private_bytes),
            "pseudonym_key": _b64(identity._pseudonym_key),
        }
        protected = protect_for_current_user(
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            description="RF QOL Agent web",
        )
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.path, protected)
        restored = self._read(self.path, identity.installation_id)
        if restored is None or restored.key_id != identity.key_id:
            raise OSError("Identidade protegida do Agent nao foi confirmada")
        try:
            self._atomic_write(self.backup_path, protected)
        except OSError:
            pass

    def load_or_create(self, installation_id: str) -> AgentIdentity:
        expected = _installation_id(installation_id)
        primary = self._read(self.path, expected)
        if primary is not None:
            return primary
        backup = self._read(self.backup_path, expected)
        if backup is not None:
            self._atomic_write(self.path, self.backup_path.read_bytes())
            return backup
        if self.path.exists() or self.backup_path.exists():
            raise OSError(
                "Identidade protegida do Agent esta corrompida ou pertence a outra instalacao"
            )
        private_key = Ed25519PrivateKey.generate()
        public_bytes = private_key.public_key().public_bytes_raw()
        identity = AgentIdentity(
            installation_id=expected,
            key_id="agent-" + hashlib.sha256(public_bytes).hexdigest()[:24],
            public_key_b64url=_b64(public_bytes),
            created_at=_now(),
            _private_key=private_key,
            _pseudonym_key=os.urandom(32),
        )
        self._save(identity)
        return identity
