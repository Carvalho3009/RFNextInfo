from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import urllib.request
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .license import CLOCK_SKEW, PRODUCT, _b64, _utc

RELEASES = "https://rflicenca.karvalho.dev.br/api/v2/updates"
UPDATE_SIGNATURE_CONTEXT = b"RFQOL-UPDATE-V2\0"
HEADERS = {"Accept": "application/json", "User-Agent": "RFQOL"}
ARCHITECTURE = "windows-x64"
MAX_INSTALLER_BYTES = 2 * 1024 * 1024 * 1024
UPDATE_MANIFEST_NAME = "update-manifest.json"
ROLLBACK_MANIFEST_NAME = "rollback-manifest.json"
VERSION_RE = r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?"
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
    rollback_from_version: str | None = None,
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
        if not re.fullmatch(VERSION_RE, unsigned["version"]):
            raise ValueError
        sequence = unsigned["release_sequence"]
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence <= 0:
            raise ValueError
        if rollback:
            if sequence >= int(current_sequence):
                raise ValueError
        elif sequence <= int(current_sequence):
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
            isinstance(item, str) and re.fullmatch(VERSION_RE, item)
            for item in compatible
        ):
            raise ValueError
        if rollback and (
            not rollback_from_version or rollback_from_version not in compatible
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


def _release_assets(release: dict) -> dict[str, str]:
    assets: dict[str, str] = {}
    for asset in release.get("assets", []):
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        url = asset.get("browser_download_url")
        if not isinstance(name, str) or not name or not isinstance(url, str):
            continue
        if name in assets or urlsplit(url).scheme.casefold() != "https":
            raise ValueError("Assets de atualização inválidos")
        assets[name] = url
    return assets


def _verified_manifest(
    release: dict,
    manifest_name: str,
    public_keys: dict[str, str] | str,
    *,
    current_sequence: int,
    rollback: bool = False,
    rollback_from_version: str | None = None,
) -> tuple[dict[str, str], bytes, dict]:
    assets = _release_assets(release)
    manifest_url = assets.get(manifest_name)
    if not manifest_url:
        raise ValueError(f"Versão sem {manifest_name}")
    request = urllib.request.Request(manifest_url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        raw_manifest = response.read(64 * 1024 + 1)
    if len(raw_manifest) > 64 * 1024:
        raise ValueError("Manifesto excede 64 KiB")
    manifest = verify_manifest(
        json.loads(raw_manifest),
        public_keys,
        current_sequence=current_sequence,
        rollback=rollback,
        rollback_from_version=rollback_from_version,
    )
    if manifest["file"] not in assets:
        raise ValueError("Instalador não encontrado")
    return assets, raw_manifest, manifest


def _download_asset(
    assets: dict[str, str],
    raw_manifest: bytes,
    manifest: dict,
    manifest_name: str,
    progress: Callable[[str, int, int | None], None] | None,
    download_dir: Path,
) -> Path:
    target_dir = Path(download_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = (target_dir / manifest["file"]).resolve()
    if target.parent != target_dir:
        raise ValueError("Destino de atualização inválido")
    partial = target.with_suffix(target.suffix + ".part")
    manifest_target = target_dir / manifest_name
    manifest_partial = manifest_target.with_suffix(manifest_target.suffix + ".part")
    partial.unlink(missing_ok=True)
    manifest_partial.unlink(missing_ok=True)
    installer_request = urllib.request.Request(
        assets[manifest["file"]], headers={"User-Agent": "RFQOL"}
    )
    try:
        with urllib.request.urlopen(installer_request, timeout=120) as response, partial.open("xb") as output:
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
        if (
            partial.stat().st_size != manifest["size"]
            or _sha256(partial).casefold() != manifest["sha256"].casefold()
        ):
            raise ValueError("Instalador baixado não corresponde ao manifesto")
        with manifest_partial.open("xb") as output:
            output.write(raw_manifest)
            output.flush()
            os.fsync(output.fileno())
        os.replace(partial, target)
        os.replace(manifest_partial, manifest_target)
        return target
    except Exception:
        partial.unlink(missing_ok=True)
        manifest_partial.unlink(missing_ok=True)
        raise


def verify_downloaded(installer: Path, manifest: dict) -> Path:
    installer = Path(installer)
    if installer.name != manifest["file"]:
        raise ValueError("Nome do instalador não confere")
    if installer.stat().st_size != manifest["size"]:
        raise ValueError("Tamanho do instalador não confere")
    if _sha256(installer).casefold() != manifest["sha256"].casefold():
        raise ValueError("SHA-256 do instalador não confere")
    return installer


def download_verified(
    release: dict,
    progress: Callable[[str, int, int | None], None] | None = None,
    download_dir: Path | None = None,
    *,
    public_keys: dict[str, str] | str = UPDATE_PUBLIC_KEYS,
    current_sequence: int = 0,
    rollback: bool = False,
    rollback_from_version: str | None = None,
    manifest_name: str = UPDATE_MANIFEST_NAME,
) -> Path:
    if progress:
        progress("manifest", 0, None)
    assets, raw_manifest, manifest = _verified_manifest(
        release,
        manifest_name,
        public_keys,
        current_sequence=current_sequence,
        rollback=rollback,
        rollback_from_version=rollback_from_version,
    )
    return _download_asset(
        assets,
        raw_manifest,
        manifest,
        manifest_name,
        progress,
        Path(download_dir or Path.cwd() / "updates"),
    )


def download_release_with_rollback(
    release: dict,
    progress: Callable[[str, int, int | None], None] | None,
    download_dir: Path,
    *,
    current_version: str,
    current_sequence: int,
    public_keys: dict[str, str] | str = UPDATE_PUBLIC_KEYS,
) -> Path:
    assets, raw_manifest, manifest = _verified_manifest(
        release,
        UPDATE_MANIFEST_NAME,
        public_keys,
        current_sequence=current_sequence,
    )
    if current_sequence > 0:
        rollback_assets, rollback_raw, rollback_manifest = _verified_manifest(
            release,
            ROLLBACK_MANIFEST_NAME,
            public_keys,
            current_sequence=manifest["release_sequence"],
            rollback=True,
            rollback_from_version=manifest["version"],
        )
        if (
            rollback_manifest["version"] != current_version
            or rollback_manifest["release_sequence"] != current_sequence
        ):
            raise ValueError("Rollback não corresponde à versão instalada")
        _download_asset(
            rollback_assets,
            rollback_raw,
            rollback_manifest,
            ROLLBACK_MANIFEST_NAME,
            None,
            Path(download_dir) / "rollback",
        )
    if progress:
        progress("manifest", 0, None)
    return _download_asset(
        assets,
        raw_manifest,
        manifest,
        UPDATE_MANIFEST_NAME,
        progress,
        Path(download_dir),
    )


def cached_rollback(
    rollback_dir: Path,
    *,
    current_version: str,
    current_sequence: int,
    public_keys: dict[str, str] | str = UPDATE_PUBLIC_KEYS,
) -> Path:
    root = Path(rollback_dir).resolve()
    manifest = verify_manifest(
        json.loads((root / ROLLBACK_MANIFEST_NAME).read_text(encoding="utf-8")),
        public_keys,
        current_sequence=current_sequence,
        rollback=True,
        rollback_from_version=current_version,
    )
    installer = (root / manifest["file"]).resolve()
    if installer.parent != root:
        raise ValueError("Cache de rollback inválido")
    return verify_downloaded(installer, manifest)


def backup_database(database: Path, backup_dir: Path, version: str) -> tuple[Path, Path]:
    source = Path(database).resolve(strict=True)
    root = Path(backup_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = root / f"database-before-rollback-{stamp}.sqlite3"
    partial = target.with_suffix(".sqlite3.part")
    evidence = target.with_suffix(".json")
    evidence_partial = evidence.with_suffix(".json.part")
    try:
        with closing(sqlite3.connect(source)) as origin, closing(
            sqlite3.connect(partial)
        ) as copy:
            origin.backup(copy)
        with closing(
            sqlite3.connect(f"file:{partial.as_posix()}?mode=ro", uri=True)
        ) as copy:
            if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup do banco não passou na integridade")
        os.replace(partial, target)
        record = {
            "schema_version": 1,
            "product": "rf-qol",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_version": version,
            "file": target.name,
            "size": target.stat().st_size,
            "sha256": _sha256(target),
            "integrity_check": "ok",
        }
        with evidence_partial.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(record, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(evidence_partial, evidence)
        return target, evidence
    except Exception:
        partial.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        evidence_partial.unlink(missing_ok=True)
        evidence.unlink(missing_ok=True)
        raise


def validate_release_configuration() -> None:
    if any(key.endswith("-pending") for key in UPDATE_PUBLIC_KEYS):
        raise RuntimeError("Chave pública de update de produção ainda não foi instalada")
