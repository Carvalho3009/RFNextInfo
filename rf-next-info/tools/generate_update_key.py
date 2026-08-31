from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path

import cryptography
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _storage_id(path: Path) -> str:
    return path.resolve().drive.casefold()


def _write_new(path: Path, data: bytes) -> None:
    try:
        with path.open("xb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def create_key(
    key_id: str,
    copies: list[Path],
    public_out: Path,
    evidence_out: Path,
    passphrase: str,
) -> dict:
    if not key_id.startswith("update-") or key_id.endswith("-pending"):
        raise ValueError("key_id de update inválido")
    if len(copies) != 2 or len({_storage_id(path) for path in copies}) != 2:
        raise ValueError("As duas cópias privadas devem usar unidades distintas")
    outputs = [*copies, public_out, evidence_out]
    if len({path.resolve() for path in outputs}) != len(outputs):
        raise ValueError("Os destinos devem ser arquivos distintos")
    if any(not path.parent.is_dir() for path in outputs):
        raise ValueError("Crie previamente todas as pastas de destino")
    if any(path.exists() for path in outputs):
        raise FileExistsError("A cerimônia não sobrescreve arquivos existentes")
    if len(passphrase) < 20:
        raise ValueError("A senha deve ter pelo menos 20 caracteres")

    private = Ed25519PrivateKey.generate()
    public_raw = private.public_key().public_bytes_raw()
    password = passphrase.encode()
    encrypted_copies = [
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(password),
        )
        for _ in copies
    ]
    for encrypted in encrypted_copies:
        restored = serialization.load_pem_private_key(encrypted, password=password)
        if restored.public_key().public_bytes_raw() != public_raw:
            raise RuntimeError("Falha no autoteste da cópia privada")

    created: list[Path] = []
    try:
        for path, encrypted in zip(copies, encrypted_copies, strict=True):
            _write_new(path, encrypted)
            created.append(path)
        _write_new(public_out, (_b64(public_raw) + "\n").encode("ascii"))
        created.append(public_out)
        evidence = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "key_id": key_id,
            "algorithm": "Ed25519",
            "environment": f"{platform.system()} {platform.release()}; offline confirmado pelo operador",
            "tool": f"Python {platform.python_version()}; cryptography {cryptography.__version__}",
            "public_key_b64url": _b64(public_raw),
            "public_key_sha256": hashlib.sha256(public_raw).hexdigest(),
            "encrypted_copies": [
                {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}
                for path, data in zip(copies, encrypted_copies, strict=True)
            ],
            "copy_restore_tests": "passed",
            "witness_review": "pending",
            "promotion": "not_deployed",
        }
        _write_new(
            evidence_out,
            (json.dumps(evidence, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
        created.append(evidence_out)
        return evidence
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera a chave offline de update do RF QOL")
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--copy", required=True, action="append", type=Path)
    parser.add_argument("--public-out", required=True, type=Path)
    parser.add_argument("--evidence-out", required=True, type=Path)
    parser.add_argument("--confirm-offline", required=True, action="store_true")
    args = parser.parse_args()
    password = getpass.getpass("Senha nova (mínimo 20 caracteres): ")
    if password != getpass.getpass("Confirme a senha: "):
        raise ValueError("As senhas não correspondem")
    evidence = create_key(
        args.key_id,
        args.copy,
        args.public_out,
        args.evidence_out,
        password,
    )
    print(json.dumps({
        "key_id": evidence["key_id"],
        "public_key_b64url": evidence["public_key_b64url"],
        "public_key_sha256": evidence["public_key_sha256"],
        "copy_restore_tests": evidence["copy_restore_tests"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
