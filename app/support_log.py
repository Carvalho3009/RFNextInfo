from __future__ import annotations

import logging
import re
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "rfnextinfo"
MAX_UPLOAD_BYTES = 256 * 1024
MAX_UPLOAD_LINES = 2_000

_REDACTIONS = (
    (re.compile(r"KRV(?:-[A-Z2-7]{5}){6}", re.IGNORECASE), "<LICENCA>"),
    (
        re.compile(
            r"(?i)\b(authorization|token|ticket|password|secret)\s*[=:]\s*\S+"
        ),
        r"\1=<REMOVIDO>",
    ),
    (re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\/\s]+"), r"C:\\Users\\<USUARIO>"),
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "<EMAIL>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<IP>"),
    (
        re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
            r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
            re.IGNORECASE,
        ),
        "<UUID>",
    ),
    (re.compile(r"(?<![\w.-])[A-Za-z0-9_-]{64,}(?![\w.-])"), "<TOKEN>"),
)


def redact(value: object) -> str:
    text = str(value)
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class _UtcRedactingFormatter(logging.Formatter):
    converter = time.gmtime

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))

    def formatException(self, exc_info) -> str:
        stack = "\n".join(
            f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}'
            for frame in traceback.extract_tb(exc_info[2])
        )
        return f"{stack}\n{exc_info[0].__name__}"


def configure(path: Path, version: str) -> logging.Logger:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        if getattr(handler, "_rfnext_handler", False):
            logger.removeHandler(handler)
            handler.close()
    handler = RotatingFileHandler(
        path,
        maxBytes=1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler._rfnext_handler = True
    handler.setFormatter(
        _UtcRedactingFormatter(
            "%(asctime)sZ %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    logger.addHandler(handler)
    logger.info("app_started version=%s", version)
    return logger


def recent_lines(path: Path) -> list[str]:
    path = Path(path)
    files = [
        path.with_name(f"{path.name}.{index}")
        for index in range(3, 0, -1)
    ] + [path]
    lines: list[str] = []
    for candidate in files:
        try:
            lines.extend(candidate.read_text(encoding="utf-8").splitlines())
        except OSError:
            pass
    payload = "\n".join(lines).encode("utf-8")[-MAX_UPLOAD_BYTES:]
    return [
        redact(line)[:4096]
        for line in payload.decode("utf-8", errors="replace").splitlines()[
            -MAX_UPLOAD_LINES:
        ]
    ]
