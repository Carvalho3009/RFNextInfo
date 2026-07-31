"""Captura nativa Windows com Pktmon, sem driver ou dependência externa."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import uuid
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


def _packet_total(value: object) -> int:
    if isinstance(value, dict):
        total = 0
        for key, item in value.items():
            normalized = str(key).casefold().replace("_", "")
            if normalized in ("packets", "packetcount") and isinstance(
                item, (int, float)
            ):
                total += max(0, int(item))
            else:
                total += _packet_total(item)
        return total
    if isinstance(value, list):
        return sum(_packet_total(item) for item in value)
    return 0


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
        ports: tuple[int, ...] = (12000, 12010, 12020, 12040),
        segment_mb: int = 512,
        stop_free_bytes: int = 2 * GIB,
        poll_seconds: float = 2,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        heartbeat_timeout_seconds: int = 45,
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
        self._run = runner or subprocess.run
        self._watchdog_enabled = runner is None and os.name == "nt"
        self._heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self._active = False
        self._prefix: Path | None = None
        self._watcher: threading.Thread | None = None
        self._lock = threading.Lock()
        self._active_ports: set[int] = set()
        self._heartbeat_path = self.output_dir / ".rfnext-info-heartbeat.json"
        self._heartbeat_token = ""
        self._watchdog: subprocess.Popen[str] | None = None

    @staticmethod
    def _validate_session_id(session_id: str) -> None:
        if not session_id or any(
            char
            not in "-_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
            for char in session_id
        ):
            raise ValueError("session_id contém caractere inválido")

    def _command(self, *args: str) -> subprocess.CompletedProcess[str]:
        try:
            result = self._run(
                ["pktmon", *args],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("PktMon não respondeu em 30 segundos") from error
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip())
        return result

    def system_running(self) -> bool:
        return _pktmon_running(self._command("status").stdout)

    def packet_count(self) -> int | None:
        try:
            payload = json.loads(self._command("counters", "--json").stdout)
        except (RuntimeError, ValueError):
            return None
        return _packet_total(payload)

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
        self._stop_watchdog()
        self._stop_pktmon()
        self._command("filter", "remove")
        self._active = False
        self._active_ports.clear()

    def heartbeat(self) -> None:
        """Confirma que a interface ainda supervisiona esta captura."""
        if not self._active or not self._heartbeat_token:
            return
        temporary = self._heartbeat_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"token": self._heartbeat_token, "pid": os.getpid()}),
            encoding="utf-8",
        )
        os.replace(temporary, self._heartbeat_path)

    def _start_watchdog(self) -> None:
        self._stop_watchdog()
        self._heartbeat_token = uuid.uuid4().hex
        self.heartbeat()
        if not self._watchdog_enabled:
            return
        path = str(self._heartbeat_path).replace("'", "''")
        token = self._heartbeat_token
        timeout = self._heartbeat_timeout_seconds
        script = (
            "param([string]$Path,[string]$Token,[int]$Timeout,[int]$ParentPid) "
            "while($true) { Start-Sleep -Seconds 5; "
            "$file=Get-Item -LiteralPath $Path -ErrorAction SilentlyContinue; "
            "if($null -eq $file) { & pktmon stop 2>$null; & pktmon filter remove 2>$null; exit }; "
            "try { $state=Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { continue }; "
            "if($state.token -ne $Token) { exit }; "
            "$alive=Get-Process -Id $ParentPid -ErrorAction SilentlyContinue; "
            "if($null -eq $alive -or (([DateTime]::UtcNow-$file.LastWriteTimeUtc).TotalSeconds -gt $Timeout)) "
            "{ & pktmon stop 2>$null; & pktmon filter remove 2>$null; exit } "
            "}"
        )
        self._watchdog = subprocess.Popen(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle",
                "Hidden", "-Command", script, path, token, str(timeout), str(os.getpid()),
            ],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _stop_watchdog(self) -> None:
        watchdog, self._watchdog = self._watchdog, None
        self._heartbeat_token = ""
        try:
            self._heartbeat_path.unlink(missing_ok=True)
        except OSError:
            pass
        if watchdog and watchdog.poll() is None:
            watchdog.terminate()

    def attach(
        self, session_id: str, ports: tuple[int, ...] = ()
    ) -> CaptureStatus:
        self._validate_session_id(session_id)
        with self._lock:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._prefix = self.output_dir / f"{session_id}.etl"
            self._active = self.system_running()
            self._active_ports = {
                port for port in ports if 1 <= port <= 65535
            }
            if self._active and (
                self._watcher is None or not self._watcher.is_alive()
            ):
                self._watcher = threading.Thread(
                    target=self._watch_disk, daemon=True
                )
                self._watcher.start()
            if self._active:
                self._start_watchdog()
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
            try:
                self._start_watchdog()
            except OSError:
                self._reset_pktmon()
                raise RuntimeError("Não foi possível iniciar a proteção da captura")
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
        return tuple(
            sorted(
                self.output_dir.glob(f"{self._prefix.stem}*.etl"),
                key=lambda path: (path.stat().st_mtime_ns, path.name),
            )
        )

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
                self._stop_watchdog()
                self._stop_pktmon()
            finally:
                self._active = False
                self._active_ports.clear()
                self._command("filter", "remove")
        return self.status()
