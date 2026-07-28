from __future__ import annotations

import hashlib
import json
import tempfile
import urllib.request
from pathlib import Path

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


def download_verified(release: dict, public_key: str) -> Path:
    assets = {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}
    manifest_url = assets.get("update-manifest.json")
    if not manifest_url:
        raise ValueError("Versão sem manifesto assinado")
    manifest_request = urllib.request.Request(manifest_url, headers=HEADERS)
    with urllib.request.urlopen(manifest_request, timeout=20) as response:
        manifest = verify_manifest(json.loads(response.read(64 * 1024)), public_key)
    file_name = manifest.get("file")
    if not file_name or file_name not in assets:
        raise ValueError("Instalador não encontrado")
    target = Path(tempfile.gettempdir()) / Path(file_name).name
    installer_request = urllib.request.Request(
        assets[file_name], headers={"User-Agent": "RFNextInfo"}
    )
    with urllib.request.urlopen(installer_request, timeout=120) as response, target.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    if hashlib.sha256(target.read_bytes()).hexdigest().lower() != str(manifest.get("sha256", "")).lower():
        target.unlink(missing_ok=True)
        raise ValueError("SHA-256 do instalador não confere")
    return target
