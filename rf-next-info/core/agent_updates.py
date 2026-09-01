"""Atualização verificável e visível do executável independente do Agent."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


UPDATE_SCHEMA = "rf-qol.agent-update/v1"
UPDATE_PRODUCT = "rf-qol-agent"
UPDATE_ARCHITECTURE = "windows-x64"
UPDATE_SIGNATURE_CONTEXT = b"RFQOL-AGENT-UPDATE-V1\0"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_INSTALLER_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_LIFETIME = timedelta(days=31)
VERSION_RE = r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?"
ALLOWED_DOWNLOAD_HOST = "raw.githubusercontent.com"
ALLOWED_DOWNLOAD_PREFIX = "/Carvalho3009/RFNextInfo/"
USER_AGENT = "RFQOL-Agent-Updater/1"


@dataclass(frozen=True)
class UpdateCandidate:
    version: str
    release_sequence: int
    installer: Path | None
    manifest: dict


def _b64decode(value: object) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("Valor base64url inválido")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as error:
        raise ValueError("Valor base64url inválido") from error


def _canonical(value: dict) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def _utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Horário inválido")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Horário sem fuso")
    return parsed.astimezone(timezone.utc)


def validate_update_url(value: object) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("URL de atualização inválida")
    parsed = urlsplit(value)
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname != ALLOWED_DOWNLOAD_HOST
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith(ALLOWED_DOWNLOAD_PREFIX)
    ):
        raise ValueError("Origem de atualização não autorizada")
    return value


def verify_manifest(
    manifest: object,
    public_keys: dict[str, str],
    *,
    channel: str,
    now: datetime | None = None,
) -> dict:
    """Confere assinatura e todos os campos antes de confiar no download."""
    try:
        if not isinstance(manifest, dict):
            raise ValueError
        unsigned = dict(manifest)
        signature = unsigned.pop("signature")
        required = {
            "schema",
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
            "url",
            "rollback_compatible_from",
        }
        if set(unsigned) != required:
            raise ValueError
        if (
            unsigned["schema"] != UPDATE_SCHEMA
            or unsigned["product"] != UPDATE_PRODUCT
            or unsigned["channel"] != channel
            or channel not in {"beta", "stable"}
            or unsigned["architecture"] != UPDATE_ARCHITECTURE
            or not re.fullmatch(VERSION_RE, str(unsigned["version"]))
        ):
            raise ValueError
        key_id = unsigned["key_id"]
        if not isinstance(key_id, str) or not key_id.startswith("update-agent-"):
            raise ValueError
        public_raw = _b64decode(public_keys.get(key_id))
        signature_raw = _b64decode(signature)
        if len(public_raw) != 32 or len(signature_raw) != 64:
            raise ValueError
        Ed25519PublicKey.from_public_bytes(public_raw).verify(
            signature_raw, UPDATE_SIGNATURE_CONTEXT + _canonical(unsigned)
        )
        sequence = unsigned["release_sequence"]
        size = unsigned["size"]
        if (
            not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or sequence <= 0
            or not isinstance(size, int)
            or isinstance(size, bool)
            or not 0 < size <= MAX_INSTALLER_BYTES
        ):
            raise ValueError
        published = _utc(unsigned["published_at"])
        expires = _utc(unsigned["expires_at"])
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if (
            published > current + timedelta(minutes=5)
            or expires <= current
            or expires <= published
            or expires - published > MAX_MANIFEST_LIFETIME
        ):
            raise ValueError
        file_name = unsigned["file"]
        if (
            not isinstance(file_name, str)
            or Path(file_name).name != file_name
            or not file_name.casefold().endswith(".exe")
            or len(file_name) > 160
            or not re.fullmatch(r"[0-9a-fA-F]{64}", str(unsigned["sha256"]))
        ):
            raise ValueError
        validate_update_url(unsigned["url"])
        compatible = unsigned["rollback_compatible_from"]
        if not isinstance(compatible, list) or not all(
            isinstance(item, str) and re.fullmatch(VERSION_RE, item)
            for item in compatible
        ):
            raise ValueError
        return unsigned
    except Exception as error:
        raise ValueError("Manifesto de atualização do Agent inválido") from error


def _read_response(response, maximum: int) -> bytes:
    raw = response.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("Resposta de atualização excedeu o limite")
    return raw


def fetch_latest(
    feed_url: str,
    public_keys: dict[str, str],
    *,
    channel: str,
    current_sequence: int,
    opener: Callable = urllib.request.urlopen,
) -> UpdateCandidate | None:
    validate_update_url(feed_url)
    request = urllib.request.Request(
        feed_url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with opener(request, timeout=15) as response:
        validate_update_url(response.geturl())
        raw = _read_response(response, MAX_MANIFEST_BYTES)
    manifest = verify_manifest(json.loads(raw), public_keys, channel=channel)
    if manifest["release_sequence"] <= int(current_sequence):
        return None
    return UpdateCandidate(
        version=manifest["version"],
        release_sequence=manifest["release_sequence"],
        installer=None,
        manifest=manifest,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified(
    candidate: UpdateCandidate,
    download_dir: Path,
    *,
    opener: Callable = urllib.request.urlopen,
    progress: Callable[[int, int], None] | None = None,
) -> UpdateCandidate:
    manifest = candidate.manifest
    target_dir = Path(download_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = (target_dir / manifest["file"]).resolve()
    if target.parent != target_dir:
        raise ValueError("Destino de atualização inválido")
    partial = target.with_suffix(target.suffix + ".part")
    partial.unlink(missing_ok=True)
    request = urllib.request.Request(
        validate_update_url(manifest["url"]), headers={"User-Agent": USER_AGENT}
    )
    try:
        with opener(request, timeout=180) as response, partial.open("xb") as output:
            validate_update_url(response.geturl())
            header = response.headers.get("Content-Length")
            if header and header.isdigit() and int(header) != manifest["size"]:
                raise ValueError("Tamanho anunciado não confere")
            downloaded = 0
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                downloaded += len(chunk)
                if downloaded > manifest["size"]:
                    raise ValueError("Instalador excedeu o tamanho assinado")
                if progress:
                    progress(downloaded, manifest["size"])
            output.flush()
            os.fsync(output.fileno())
        if (
            partial.stat().st_size != manifest["size"]
            or _sha256(partial).casefold() != manifest["sha256"].casefold()
        ):
            raise ValueError("Instalador não corresponde ao manifesto assinado")
        os.replace(partial, target)
        return UpdateCandidate(
            version=candidate.version,
            release_sequence=candidate.release_sequence,
            installer=target,
            manifest=manifest,
        )
    except Exception:
        partial.unlink(missing_ok=True)
        raise
