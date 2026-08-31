"""Gera e usa a chave local de release do Agent protegida por DPAPI."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.protected_state import protect_for_current_user, unprotect


KEY_SCHEMA = "rf-qol.agent-update-key/v1"


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def generate(
    key_id: str,
    private_copies: list[Path],
    public_out: Path,
    evidence_out: Path,
) -> dict:
    if not key_id.startswith("update-agent-") or key_id.endswith("-pending"):
        raise ValueError("Identificador de chave inválido")
    if len(private_copies) != 2 or len(
        {path.resolve().drive.casefold() for path in private_copies}
    ) != 2:
        raise ValueError("As cópias privadas devem estar em duas unidades")
    outputs = [*private_copies, public_out, evidence_out]
    if len({path.resolve() for path in outputs}) != len(outputs):
        raise ValueError("Destinos de chave repetidos")
    if any(path.exists() for path in outputs):
        raise FileExistsError("A geração não sobrescreve chaves existentes")

    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes_raw()
    public_raw = private.public_key().public_bytes_raw()
    protected = protect_for_current_user(
        private_raw, description=f"RF QOL Agent update {key_id}"
    )
    record = {
        "schema": KEY_SCHEMA,
        "key_id": key_id,
        "protection": "windows-dpapi-current-user",
        "private_key": _b64(protected),
        "public_key": _b64(public_raw),
    }
    encoded = (json.dumps(record, sort_keys=True) + "\n").encode()
    created: list[Path] = []
    try:
        for path in private_copies:
            _write_new(path, encoded)
            created.append(path)
            restored = load_private_key(path)
            if restored.public_key().public_bytes_raw() != public_raw:
                raise RuntimeError("Falha no autoteste da cópia privada")
        _write_new(public_out, (_b64(public_raw) + "\n").encode("ascii"))
        created.append(public_out)
        evidence = {
            "schema": "rf-qol.agent-update-key-evidence/v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "key_id": key_id,
            "algorithm": "Ed25519",
            "protection": "Windows DPAPI current-user",
            "public_key_b64url": _b64(public_raw),
            "public_key_sha256": hashlib.sha256(public_raw).hexdigest(),
            "private_copy_sha256": [hashlib.sha256(encoded).hexdigest()] * 2,
            "copy_restore_tests": "passed",
            "authenticode": "not-used-by-project-decision",
        }
        _write_new(
            evidence_out,
            (json.dumps(evidence, ensure_ascii=False, indent=2) + "\n").encode(),
        )
        created.append(evidence_out)
        return evidence
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise


def load_private_key(path: Path) -> Ed25519PrivateKey:
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        not isinstance(record, dict)
        or record.get("schema") != KEY_SCHEMA
        or not str(record.get("key_id") or "").startswith("update-agent-")
        or record.get("protection") != "windows-dpapi-current-user"
    ):
        raise ValueError("Arquivo de chave do Agent inválido")
    raw = unprotect(_decode(record["private_key"]))
    if len(raw) != 32:
        raise ValueError("Chave privada do Agent inválida")
    key = Ed25519PrivateKey.from_private_bytes(raw)
    if _b64(key.public_key().public_bytes_raw()) != record.get("public_key"):
        raise ValueError("Chave pública não corresponde à privada")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera chave local de update do Agent")
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--copy", action="append", required=True, type=Path)
    parser.add_argument("--public-out", required=True, type=Path)
    parser.add_argument("--evidence-out", required=True, type=Path)
    args = parser.parse_args()
    evidence = generate(args.key_id, args.copy, args.public_out, args.evidence_out)
    print(json.dumps({
        "key_id": evidence["key_id"],
        "public_key_b64url": evidence["public_key_b64url"],
        "public_key_sha256": evidence["public_key_sha256"],
        "copy_restore_tests": evidence["copy_restore_tests"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
