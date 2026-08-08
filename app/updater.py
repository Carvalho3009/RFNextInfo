from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Callable

from .license import _b64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

RELEASES = "https://rflicenca.karvalho.dev.br/api/v1/updates"
UPDATE_SIGNATURE_CONTEXT = b"RFNEXT-UPDATE-V1\0"
HEADERS = {"Accept": "application/json", "User-Agent": "RFNextInfo"}


def verify_manifest(manifest: dict, public_key: str) -> dict:
    unsigned = dict(manifest)
    signature = unsigned.pop("signature", "")
    canonical = json.dumps(unsigned, separators=(",", ":"), sort_keys=True).encode()
    Ed25519PublicKey.from_public_bytes(_b64(public_key)).verify(
        _b64(signature), UPDATE_SIGNATURE_CONTEXT + canonical
    )
    return unsigned


def latest(channel: str = "stable") -> dict:
    request = urllib.request.Request(
        RELEASES,
        headers=HEADERS,
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        releases = json.loads(response.read(512 * 1024))
    candidates = [item for item in releases if not item.get("draft")]
    if channel == "stable":
        candidates = [item for item in candidates if not item.get("prerelease")]
    if not candidates:
        raise ValueError("Nenhuma versão publicada neste canal")
    return candidates[0]


def download_verified(
    release: dict,
    public_key: str,
    progress: Callable[[str, int, int | None], None] | None = None,
    download_dir: Path | None = None,
) -> Path:
    assets = {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}
    manifest_url = assets.get("update-manifest.json")
    if not manifest_url:
        raise ValueError("Versão sem manifesto assinado")
    if progress:
        progress("manifest", 0, None)
    manifest_request = urllib.request.Request(manifest_url, headers=HEADERS)
    with urllib.request.urlopen(manifest_request, timeout=20) as response:
        manifest = verify_manifest(json.loads(response.read(64 * 1024)), public_key)
    file_name = manifest.get("file")
    if not file_name or file_name not in assets:
        raise ValueError("Instalador não encontrado")
    target_dir = Path(download_dir or Path.cwd() / "updates")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / Path(file_name).name
    partial = target.with_suffix(target.suffix + ".part")
    installer_request = urllib.request.Request(
        assets[file_name], headers={"User-Agent": "RFNextInfo"}
    )
    try:
        with urllib.request.urlopen(installer_request, timeout=120) as response, partial.open("wb") as output:
            try:
                total = int(response.headers.get("Content-Length", "0")) or None
            except (TypeError, ValueError):
                total = None
            downloaded = 0
            if progress:
                progress("download", downloaded, total)
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                downloaded += len(chunk)
                if progress:
                    progress("download", downloaded, total)
        if progress:
            progress("verify", downloaded, total)
        digest = hashlib.sha256()
        with partial.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest().lower() != str(manifest.get("sha256", "")).lower():
            raise ValueError("SHA-256 do instalador não confere")
        partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return target
