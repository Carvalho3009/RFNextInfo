"""Assina o manifesto público de atualização do RF QOL Agent."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.agent_updates import (
    UPDATE_ARCHITECTURE,
    UPDATE_PRODUCT,
    UPDATE_SCHEMA,
    UPDATE_SIGNATURE_CONTEXT,
    VERSION_RE,
    validate_update_url,
)
from tools.agent_update_key import load_private_key


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def create_manifest(
    installer: Path,
    *,
    version: str,
    release_sequence: int,
    key_id: str,
    private_key: Path,
    download_url: str,
    channel: str,
    rollback_compatible_from: list[str] | None = None,
    now: datetime | None = None,
) -> dict:
    installer = Path(installer).resolve(strict=True)
    compatible = list(rollback_compatible_from or [])
    if (
        not re.fullmatch(VERSION_RE, version)
        or release_sequence <= 0
        or not key_id.startswith("update-agent-")
        or key_id.endswith("-pending")
        or channel not in {"beta", "stable"}
        or installer.name != Path(installer.name).name
        or not installer.name.casefold().endswith(".exe")
        or len(set(compatible)) != len(compatible)
        or not all(re.fullmatch(VERSION_RE, value) for value in compatible)
    ):
        raise ValueError("Parâmetros do manifesto inválidos")
    validate_update_url(download_url)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    manifest = {
        "schema": UPDATE_SCHEMA,
        "product": UPDATE_PRODUCT,
        "channel": channel,
        "architecture": UPDATE_ARCHITECTURE,
        "version": version,
        "release_sequence": release_sequence,
        "published_at": current.isoformat(),
        "expires_at": (current + timedelta(days=30)).isoformat(),
        "key_id": key_id,
        "file": installer.name,
        "size": installer.stat().st_size,
        "sha256": _sha256(installer),
        "url": download_url,
        "rollback_compatible_from": compatible,
    }
    canonical = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
    manifest["signature"] = _b64(
        load_private_key(private_key).sign(UPDATE_SIGNATURE_CONTEXT + canonical)
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Assina update do RF QOL Agent")
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--sequence", required=True, type=int)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--download-url", required=True)
    parser.add_argument("--channel", choices=("beta", "stable"), default="beta")
    parser.add_argument("--rollback-compatible-from", action="append", default=[])
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    manifest = create_manifest(
        args.installer,
        version=args.version,
        release_sequence=args.sequence,
        key_id=args.key_id,
        private_key=args.private_key,
        download_url=args.download_url,
        channel=args.channel,
        rollback_compatible_from=args.rollback_compatible_from,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
