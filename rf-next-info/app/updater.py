from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .license import CLOCK_SKEW, PRODUCT, _b64, _utc

RELEASES = "https://rflicenca.karvalho.dev.br/api/v2/updates"
UPDATE_SIGNATURE_CONTEXT = b"RFQOL-UPDATE-V2\0"
HEADERS = {"Accept": "application/json", "User-Agent": "RFQOL"}
ARCHITECTURE = "windows-x64"
MAX_INSTALLER_BYTES = 2 * 1024 * 1024 * 1024
UPDATE_PUBLIC_KEYS = {
    "update-production-pending": "hMzgTmtD3bwxGXzSBj-bUEcE6aVY9cwRu176tGgoJdM",
}


def _canonical(unsigned: dict) -> bytes:
    return json.dumps(unsigned, separators=(",", ":"), sort_keys=True).encode()


def verify_manifest(
    manifest: dict,
    public_keys: dict[str, str] | str = UPDATE_PUBLIC_KEYS,
    *,
    now: datetime | None = None,
    current_sequence: int = 0,
    rollback: bool = False,
) -> dict:
    """Valida por completo o manifesto v2 antes de confiar em qualquer campo."""
    try:
        if not isinstance(manifest, dict):
            raise ValueError
        unsigned = dict(manifest)
        signature = unsigned.pop("signature")
        required = {
            "manifest_version",
            "product",
            "channel",
            "architecture",
            "version",
            "release_sequence",
            "published_at",
            "expires_at",
            "key_id",
            "file",
            "size",
            "sha256",
            "rollback_compatible_from",
        }
        if set(unsigned) != required:
            raise ValueError
        key_id = unsigned["key_id"]
        if not isinstance(key_id, str) or not key_id.startswith("update-"):
            raise ValueError
        public_key = (
            public_keys
            if isinstance(public_keys, str)
            else public_keys.get(key_id)
        )
        if not public_key:
            raise ValueError
        Ed25519PublicKey.from_public_bytes(_b64(public_key)).verify(
            _b64(signature), UPDATE_SIGNATURE_CONTEXT + _canonical(unsigned)
        )
        if (
            unsigned["manifest_version"] != 2
            or unsigned["product"] != PRODUCT
            or unsigned["channel"] not in {"stable", "beta"}
            or unsigned["architecture"] != ARCHITECTURE
        ):
            raise ValueError
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", unsigned["version"]):
            raise ValueError
        sequence = unsigned["release_sequence"]
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence <= 0:
            raise ValueError
        if not rollback and sequence <= int(current_sequence):
            raise ValueError
        published = _utc(unsigned["published_at"])
        expires = _utc(unsigned["expires_at"])
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if published > current + CLOCK_SKEW or expires <= current or expires <= published:
            raise ValueError
        if expires - published > timedelta(days=31):
            raise ValueError
        file_name = unsigned["file"]
        if (
            not isinstance(file_name, str)
            or Path(file_name).name != file_name
            or not file_name.casefold().endswith(".exe")
            or len(file_name) > 160
        ):
            raise ValueError
        size = unsigned["size"]
        if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_INSTALLER_BYTES:
            raise ValueError
        if not re.fullmatch(r"[0-9a-fA-F]{64}", unsigned["sha256"]):
            raise ValueError
        compatible = unsigned["rollback_compatible_from"]
        if not isinstance(compatible, list) or not all(
            isinstance(item, str) and len(item) <= 80 for item in compatible
        ):
            raise ValueError
        return unsigned
    except Exception as error:
        raise ValueError("Manifesto de atualização inválido") from error


def latest(channel: str = "stable") -> dict:
    if channel not in {"stable", "beta"}:
        raise ValueError("Canal de atualização inválido")
    request = urllib.request.Request(RELEASES, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=12) as response:
        releases = json.loads(response.read(512 * 1024))
    if not isinstance(releases, list):
        raise ValueError("Feed de atualização inválido")
    candidates = [item for item in releases if isinstance(item, dict) and not item.get("draft")]
    if channel == "stable":
        candidates = [item for item in candidates if not item.get("prerelease")]
    if not candidates:
        raise ValueError("Nenhuma versão publicada neste canal")
    return candidates[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_downloaded(installer: Path, manifest: dict) -> Path:
    installer = Path(installer)
    if installer.name != manifest["file"]:
        raise ValueError("Nome do instalador não confere")
    if installer.stat().st_size != manifest["size"]:
        raise ValueError("Tamanho do instalador não confere")
    if _sha256(installer).casefold() != manifest["sha256"].casefold():
        raise ValueError("SHA-256 do instalador não confere")
    return installer


def verify_authenticode(installer: Path, expected_publisher: str = "Karvalho") -> None:
    """Usa o verificador nativo do Windows e exige o publicador esperado."""
    if os.name != "nt":
        raise OSError("Authenticode requer Windows")
    # Um processo iniciado pelo PowerShell 7 pode herdar um PSModulePath que
    # impede o Windows PowerShell de carregar Microsoft.PowerShell.Security.
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.casefold() != "psmodulepath"
    }
    environment["RFQOL_VERIFY_PATH"] = str(Path(installer).resolve(strict=True))
    script = (
        "$s=Get-AuthenticodeSignature -LiteralPath $env:RFQOL_VERIFY_PATH;"
        "$o=[ordered]@{Status=[string]$s.Status;Subject=[string]$s.SignerCertificate.Subject};"
        "$o|ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
        status = json.loads(result.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, IndexError) as error:
        raise ValueError("Não foi possível verificar a assinatura Authenticode") from error
    if status.get("Status") != "Valid" or expected_publisher.casefold() not in str(
        status.get("Subject") or ""
    ).casefold():
        raise ValueError("Assinatura Authenticode ou publicador inválido")


def download_verified(
    release: dict,
    progress: Callable[[str, int, int | None], None] | None = None,
    download_dir: Path | None = None,
    *,
    public_keys: dict[str, str] | str = UPDATE_PUBLIC_KEYS,
    current_sequence: int = 0,
    rollback: bool = False,
) -> Path:
    assets = {
        asset["name"]: asset["browser_download_url"]
        for asset in release.get("assets", [])
        if isinstance(asset, dict) and asset.get("name") and asset.get("browser_download_url")
    }
    manifest_url = assets.get("update-manifest.json")
    if not manifest_url:
        raise ValueError("Versão sem manifesto assinado")
    if progress:
        progress("manifest", 0, None)
    request = urllib.request.Request(manifest_url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        raw_manifest = response.read(64 * 1024)
    manifest = verify_manifest(
        json.loads(raw_manifest),
        public_keys,
        current_sequence=current_sequence,
        rollback=rollback,
    )
    file_name = manifest["file"]
    if file_name not in assets:
        raise ValueError("Instalador não encontrado")
    target_dir = Path(download_dir or Path.cwd() / "updates").resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = (target_dir / file_name).resolve()
    if target.parent != target_dir:
        raise ValueError("Destino de atualização inválido")
    partial = target.with_suffix(target.suffix + ".part")
    installer_request = urllib.request.Request(
        assets[file_name], headers={"User-Agent": "RFQOL"}
    )
    try:
        with urllib.request.urlopen(installer_request, timeout=120) as response, partial.open("wb") as output:
            header = response.headers.get("Content-Length")
            total = int(header) if header and header.isdigit() else None
            if total is not None and total != manifest["size"]:
                raise ValueError("Tamanho anunciado do instalador não confere")
            downloaded = 0
            if progress:
                progress("download", downloaded, manifest["size"])
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                downloaded += len(chunk)
                if downloaded > manifest["size"]:
                    raise ValueError("Instalador excede o tamanho assinado")
                if progress:
                    progress("download", downloaded, manifest["size"])
        if progress:
            progress("verify", downloaded, manifest["size"])
        if partial.stat().st_size != manifest["size"] or _sha256(partial).casefold() != manifest["sha256"].casefold():
            raise ValueError("Instalador baixado não corresponde ao manifesto")
        os.replace(partial, target)
        (target_dir / "update-manifest.json").write_bytes(raw_manifest)
        return target
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def validate_release_configuration() -> None:
    if any(key.endswith("-pending") for key in UPDATE_PUBLIC_KEYS):
        raise RuntimeError("Chave pública de update de produção ainda não foi instalada")
