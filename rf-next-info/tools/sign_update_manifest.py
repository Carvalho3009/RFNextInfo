from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.updater import ARCHITECTURE, UPDATE_SIGNATURE_CONTEXT, VERSION_RE


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _private_key(path: Path) -> Ed25519PrivateKey:
    raw = path.read_bytes()
    if raw.lstrip().startswith(b"-----BEGIN"):
        password = None
        if b"ENCRYPTED PRIVATE KEY" in raw[:80]:
            password = getpass.getpass("Senha da chave privada de update: ").encode()
        try:
            key = serialization.load_pem_private_key(raw, password=password)
        except (TypeError, ValueError) as error:
            raise ValueError("Chave privada inválida ou senha incorreta") from error
    else:
        decoded = base64.urlsafe_b64decode(raw.strip() + b"=" * (-len(raw.strip()) % 4))
        key = Ed25519PrivateKey.from_private_bytes(decoded)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("A chave não é Ed25519")
    return key


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Assina manifesto de update RF QOL v2")
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--sequence", required=True, type=int)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--channel", choices=("stable", "beta"), default="stable")
    parser.add_argument("--rollback-compatible-from", action="append", default=[])
    args = parser.parse_args()

    installer = args.installer.resolve(strict=True)
    if (
        args.sequence <= 0
        or not args.key_id.startswith("update-")
        or args.key_id.endswith("-pending")
        or not re.fullmatch(VERSION_RE, args.version)
        or len(set(args.rollback_compatible_from))
        != len(args.rollback_compatible_from)
        or not all(
            re.fullmatch(VERSION_RE, version)
            for version in args.rollback_compatible_from
        )
    ):
        raise ValueError("Parâmetros do manifesto inválidos")
    if installer.name != Path(installer.name).name or not installer.name.casefold().endswith(".exe"):
        raise ValueError("Nome do instalador inválido")
    now = datetime.now(timezone.utc)
    manifest = {
        "manifest_version": 2,
        "product": "rf-qol",
        "channel": args.channel,
        "architecture": ARCHITECTURE,
        "version": args.version,
        "release_sequence": args.sequence,
        "published_at": now.isoformat(),
        "expires_at": (now + timedelta(days=7)).isoformat(),
        "key_id": args.key_id,
        "file": installer.name,
        "size": installer.stat().st_size,
        "sha256": _sha256(installer),
        "rollback_compatible_from": args.rollback_compatible_from,
    }
    canonical = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
    manifest["signature"] = _b64(
        _private_key(args.private_key).sign(UPDATE_SIGNATURE_CONTEXT + canonical)
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
