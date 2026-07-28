"""Captura nativa Windows com Pktmon, sem driver ou dependência externa."""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

GIB = 1024**3


def _pktmon_running(status: str) -> bool:
    status = " ".join(status.lower().split())
    stopped = ("not running", "não está em execução", "nao esta em execucao")
    return not any(marker in status for marker in stopped) and (
        "running" in status
        or "em execução" in status
        or "em execucao" in status
        or "already started" in status
        or "já foi iniciado" in status
    )


@dataclass(frozen=True)
class CaptureStatus:
    active: bool
    bytes_written: int
    free_bytes: int
    safe_stop: bool
    files: tuple[Path, ...]


class PktmonCapture:
    """Controla a única captura global do Pktmon e vigia espaço livre."""

    def __init__(
        self,
        output_dir: Path,
        *,
        ports: tuple[int, ...] = (12000, 12020, 12040),
        segment_mb: int = 512,
        stop_free_bytes: int = 2 * GIB,
        poll_seconds: float = 2,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        if not ports or any(not 1 <= port <= 65535 for port in ports):
            raise ValueError("porta inválida")
        if not 16 <= segment_mb <= 4096:
            raise ValueError("segment_mb deve estar entre 16 e 4096")
        self.output_dir = Path(output_dir)
        self.ports = tuple(dict.fromkeys(ports))
        self.segment_mb = segment_mb
        self.stop_free_bytes = stop_free_bytes
        self.poll_seconds = poll_seconds
        self._run = runner
        self._active = False
        self._prefix: Path | None = None
        self._watcher: threading.Thread | None = None
        self._lock = threading.Lock()
        self._active_ports: set[int] = set()

    @staticmethod
    def _validate_session_id(session_id: str) -> None:
        if not session_id or any(
            char
            not in "-_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
            for char in session_id
        ):
            raise ValueError("session_id contém caractere inválido")

    def _command(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = self._run(
            ["pktmon", *args],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip())
        return result

    def system_running(self) -> bool:
        return _pktmon_running(self._command("status").stdout)

    def _stop_pktmon(self) -> None:
        try:
            self._command("stop")
        except RuntimeError as error:
            stopped = (
                "not running",
                "não está em execução",
                "nao esta em execucao",
            )
            if not any(marker in str(error).casefold() for marker in stopped):
                raise

    def _reset_pktmon(self) -> None:
        self._stop_pktmon()
        self._command("filter", "remove")
        self._active = False
        self._active_ports.clear()

    def attach(
        self, session_id: str, ports: tuple[int, ...] = ()
    ) -> CaptureStatus:
        self._validate_session_id(session_id)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._prefix = self.output_dir / f"{session_id}.etl"
        self._active = self.system_running()
        self._active_ports = {
            port for port in ports if 1 <= port <= 65535
        }
        if self._active and (
            self._watcher is None or not self._watcher.is_alive()
        ):
            self._watcher = threading.Thread(target=self._watch_disk, daemon=True)
            self._watcher.start()
        return self.status()

    def start(self, session_id: str) -> Path:
        return self.start_for_ports(session_id, self.ports)

    def start_for_ports(self, session_id: str, ports: tuple[int, ...]) -> Path:
        self._validate_session_id(session_id)
        ports = tuple(dict.fromkeys((*self.ports, *ports)))
        if not ports or any(not 1 <= port <= 65535 for port in ports):
            raise ValueError("porta inválida")
        if len(ports) > 32:
            raise ValueError("limite de 32 conexões simultâneas excedido")
        if shutil.which("pktmon") is None:
            raise RuntimeError("Pktmon não está disponível neste Windows")
        with self._lock:
            if self._active:
                raise RuntimeError("captura já está ativa")
            if shutil.disk_usage(self.output_dir.parent if not self.output_dir.exists() else self.output_dir).free < self.stop_free_bytes:
                raise RuntimeError("espaço livre abaixo do limite de segurança")
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._prefix = self.output_dir / f"{session_id}.etl"
            self._reset_pktmon()

            def begin() -> None:
                for index, port in enumerate(ports, 1):
                    self._command(
                        "filter",
                        "add",
                        f"RFNextInfo{index}",
                        "-t",
                        "TCP",
                        "-p",
                        str(port),
                    )
                self._command(
                    "start",
                    "--capture",
                    "--comp",
                    "nics",
                    "--pkt-size",
                    "0",
                    "--file-name",
                    str(self._prefix),
                    "--file-size",
                    str(self.segment_mb),
                    "--log-mode",
                    "multi-file",
                )

            try:
                begin()
            except RuntimeError as error:
                already_started = (
                    "already started",
                    "já foi iniciado",
                    "ja foi iniciado",
                )
                if not any(
                    marker in str(error).casefold()
                    for marker in already_started
                ):
                    self._command("filter", "remove")
                    raise
                self._reset_pktmon()
                time.sleep(0.25)
                try:
                    begin()
                except Exception:
                    self._command("filter", "remove")
                    raise
            except Exception:
                self._command("filter", "remove")
                raise
            self._active_ports = set(ports)
            self._active = True
            self._watcher = threading.Thread(target=self._watch_disk, daemon=True)
            self._watcher.start()
            return self._prefix

    def add_ports(self, ports: tuple[int, ...]) -> int:
        """Inclui portas descobertas em reconexões sem reiniciar a sessão."""
        with self._lock:
            if not self._active:
                return 0
            ports = tuple(
                port
                for port in dict.fromkeys(ports)
                if 1 <= port <= 65535 and port not in self._active_ports
            )
            if not ports:
                return 0
            if len(self._active_ports) + len(ports) > 32:
                raise RuntimeError(
                    "limite de conexões atingido; pare e inicie uma nova captura"
                )
            for port in ports:
                index = len(self._active_ports) + 1
                self._command(
                    "filter",
                    "add",
                    f"RFNextInfo{index}",
                    "-t",
                    "TCP",
                    "-p",
                    str(port),
                )
                self._active_ports.add(port)
            return len(ports)

    def _watch_disk(self) -> None:
        while self._active:
            status = self.status()
            if not status.active:
                self._active = False
                return
            if status.safe_stop:
                self.stop()
                return
            time.sleep(self.poll_seconds)

    def segment_files(self) -> tuple[Path, ...]:
        if self._prefix is None:
            return ()
        return tuple(sorted(self.output_dir.glob(f"{self._prefix.stem}*.etl")))

    @property
    def attached(self) -> bool:
        return self._prefix is not None

    def status(self) -> CaptureStatus:
        files = self.segment_files()
        size = sum(path.stat().st_size for path in files if path.exists())
        free = shutil.disk_usage(self.output_dir).free if self.output_dir.exists() else 0
        return CaptureStatus(
            self.system_running(),
            size,
            free,
            free < self.stop_free_bytes,
            files,
        )

    def stop(self) -> CaptureStatus:
        with self._lock:
            try:
                self._stop_pktmon()
            finally:
                self._active = False
                self._active_ports.clear()
                self._command("filter", "remove")
        return self.status()
