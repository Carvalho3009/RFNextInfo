"""Instalação e reprodução segura de alertas WAV locais."""

from __future__ import annotations

import hashlib
import shutil
import wave
from pathlib import Path
from typing import Callable


MAX_ALERT_SOUND_BYTES = 5 * 1024 * 1024
MAX_ALERT_SOUND_SECONDS = 10.0


def validate_alert_sound(path: Path) -> dict[str, float | int]:
    path = Path(path)
    if path.suffix.casefold() != ".wav" or not path.is_file():
        raise ValueError("Escolha um arquivo WAV local.")
    size = path.stat().st_size
    if not 0 < size <= MAX_ALERT_SOUND_BYTES:
        raise ValueError("O som deve ter no máximo 5 MiB.")
    try:
        with wave.open(str(path), "rb") as source:
            rate = source.getframerate()
            frames = source.getnframes()
            channels = source.getnchannels()
            width = source.getsampwidth()
    except (wave.Error, EOFError, OSError) as error:
        raise ValueError("O arquivo WAV não pôde ser validado.") from error
    duration = frames / rate if rate > 0 else 0.0
    if not 0 < duration <= MAX_ALERT_SOUND_SECONDS:
        raise ValueError("O som deve ter entre 0 e 10 segundos.")
    if channels not in {1, 2} or width not in {1, 2, 3, 4}:
        raise ValueError("Use um WAV mono ou estéreo em formato PCM compatível.")
    return {"bytes": size, "duration_seconds": round(duration, 3)}


def install_alert_sound(source: Path, target_directory: Path) -> str:
    source = Path(source)
    validate_alert_sound(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    target_directory = Path(target_directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target = target_directory / f"{digest}.wav"
    if not target.is_file():
        temporary = target.with_suffix(".tmp")
        shutil.copy2(source, temporary)
        temporary.replace(target)
    return target.name


def resolve_alert_sound(target_directory: Path, filename: object) -> Path | None:
    name = str(filename or "").strip().casefold()
    if len(name) != 68 or not name.endswith(".wav"):
        return None
    stem = name[:-4]
    if any(character not in "0123456789abcdef" for character in stem):
        return None
    path = Path(target_directory) / name
    try:
        validate_alert_sound(path)
    except ValueError:
        return None
    return path


def play_alert_sound(path: Path | None, fallback: Callable[[], None]) -> None:
    if path is not None:
        try:
            import winsound

            winsound.PlaySound(
                str(path),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
            return
        except (ImportError, OSError, RuntimeError):
            pass
    fallback()
