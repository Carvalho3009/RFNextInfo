"""Descoberta somente leitura das conexões TCP por executável no Windows."""

from __future__ import annotations

import ctypes
import os
import socket
from ctypes import wintypes

AF_INET6 = 23
ERROR_INSUFFICIENT_BUFFER = 122
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TCP_ESTABLISHED = 5
TCP_TABLE_OWNER_PID_CONNECTIONS = 4


class _TcpRow(ctypes.Structure):
    _fields_ = [
        ("state", wintypes.DWORD),
        ("local_address", wintypes.DWORD),
        ("local_port", wintypes.DWORD),
        ("remote_address", wintypes.DWORD),
        ("remote_port", wintypes.DWORD),
        ("pid", wintypes.DWORD),
    ]


class _Tcp6Row(ctypes.Structure):
    _fields_ = [
        ("local_address", ctypes.c_ubyte * 16),
        ("local_scope", wintypes.DWORD),
        ("local_port", wintypes.DWORD),
        ("remote_address", ctypes.c_ubyte * 16),
        ("remote_scope", wintypes.DWORD),
        ("remote_port", wintypes.DWORD),
        ("state", wintypes.DWORD),
        ("pid", wintypes.DWORD),
    ]


def _tcp_rows() -> list[tuple[int, int, int]]:
    if os.name != "nt":
        return []
    get_table = ctypes.windll.iphlpapi.GetExtendedTcpTable
    get_table.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.BOOL,
        wintypes.ULONG,
        ctypes.c_int,
        wintypes.ULONG,
    ]
    rows: list[tuple[int, int, int]] = []
    for family, row_type in ((socket.AF_INET, _TcpRow), (AF_INET6, _Tcp6Row)):
        size = wintypes.DWORD()
        result = get_table(
            None,
            ctypes.byref(size),
            False,
            family,
            TCP_TABLE_OWNER_PID_CONNECTIONS,
            0,
        )
        if result not in (0, ERROR_INSUFFICIENT_BUFFER):
            continue
        buffer = ctypes.create_string_buffer(size.value)
        if get_table(
            buffer,
            ctypes.byref(size),
            False,
            family,
            TCP_TABLE_OWNER_PID_CONNECTIONS,
            0,
        ):
            continue
        count = wintypes.DWORD.from_buffer(buffer).value
        start = ctypes.addressof(buffer) + ctypes.sizeof(wintypes.DWORD)
        for index in range(count):
            row = row_type.from_address(start + index * ctypes.sizeof(row_type))
            if row.state == TCP_ESTABLISHED:
                rows.append(
                    (
                        int(row.pid),
                        socket.ntohs(int(row.local_port) & 0xFFFF),
                        socket.ntohs(int(row.remote_port) & 0xFFFF),
                    )
                )
    return rows


def _process_path(pid: int) -> str | None:
    if os.name != "nt":
        return None
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        path = ctypes.create_unicode_buffer(size.value)
        if not kernel.QueryFullProcessImageNameW(
            handle, 0, path, ctypes.byref(size)
        ):
            return None
        return path.value
    finally:
        kernel.CloseHandle(handle)


def _connected_processes(
    allowed_remote_ports: tuple[int, ...],
    executable_prefixes: tuple[str, ...],
    *,
    include_same_pid_local_ports: bool = False,
) -> dict[str, tuple[set[int], set[int], set[int]]]:
    allowed = set(allowed_remote_ports)
    prefixes = tuple(value.casefold() for value in executable_prefixes)
    result: dict[str, tuple[set[int], set[int], set[int]]] = {}
    paths: dict[int, str | None] = {}
    rows = _tcp_rows()

    def matching_path(pid: int) -> str | None:
        if pid not in paths:
            paths[pid] = _process_path(pid)
        path = paths[pid]
        if path and os.path.basename(path).casefold().startswith(prefixes):
            return path
        return None

    matching_pids = {
        pid for pid, _local_port, _remote_port in rows if matching_path(pid)
    }
    allowed_pids = {
        pid
        for pid, _local_port, remote_port in rows
        if matching_path(pid) and (not allowed or remote_port in allowed)
    }
    eligible_pids = matching_pids if include_same_pid_local_ports else allowed_pids
    for pid, local_port, remote_port in rows:
        path = matching_path(pid)
        if not path or pid not in eligible_pids:
            continue
        if (
            allowed
            and remote_port not in allowed
            and not include_same_pid_local_ports
        ):
            continue
        key = os.path.normcase(os.path.abspath(path))
        pids, local_ports, remote_ports = result.setdefault(
            key, (set(), set(), set())
        )
        pids.add(pid)
        local_ports.add(local_port)
        if not allowed or remote_port in allowed:
            remote_ports.add(remote_port)
    return result


def connected_processes(
    allowed_remote_ports: tuple[int, ...] = (),
) -> dict[str, tuple[set[int], set[int], set[int]]]:
    """Retorna clientes PC ProjectRF por executável, sem expor IPs."""
    return _connected_processes(
        allowed_remote_ports,
        ("projectrf",),
        include_same_pid_local_ports=True,
    )


def agent_processes(
    allowed_remote_ports: tuple[int, ...] = (),
) -> dict[str, tuple[set[int], set[int], set[int]]]:
    """Rotas de jogo do Agent, incluindo o proxy local usado pelo ExitLag.

    Conexoes HTTPS do cliente servem para login/telemetria e mudam com
    frequencia. Elas nao carregam os frames do jogo e, se entrarem no filtro,
    provocam reinicios e trabalho inutil no decoder.
    """
    allowed = set(allowed_remote_ports)
    result: dict[str, tuple[set[int], set[int], set[int]]] = {}
    paths: dict[int, str | None] = {}

    def matching_path(pid: int) -> str | None:
        if pid not in paths:
            paths[pid] = _process_path(pid)
        path = paths[pid]
        if path and os.path.basename(path).casefold().startswith("projectrf"):
            return path
        return None

    for pid, local_port, remote_port in _tcp_rows():
        path = matching_path(pid)
        if not path:
            continue
        is_direct_game = bool(allowed and remote_port in allowed)
        is_relay_candidate = remote_port not in (0, 80, 443)
        if not is_direct_game and not is_relay_candidate:
            continue
        key = os.path.normcase(os.path.abspath(path))
        pids, local_ports, remote_ports = result.setdefault(
            key, (set(), set(), set())
        )
        pids.add(pid)
        local_ports.add(local_port)
        if is_direct_game:
            remote_ports.add(remote_port)
    return result


def emulator_processes(
    allowed_remote_ports: tuple[int, ...] = (),
) -> dict[str, tuple[set[int], set[int], set[int]]]:
    """Retorna instâncias BlueStacks pelo processo proprietário HD-Player."""
    return _connected_processes(allowed_remote_ports, ("hd-player",))


def ports_for_executable(
    executable: str, allowed_remote_ports: tuple[int, ...] = ()
) -> tuple[tuple[int, ...], tuple[int, ...], int]:
    selected = os.path.normcase(os.path.abspath(executable))
    pids, local_ports, remote_ports = connected_processes(
        allowed_remote_ports
    ).get(
        selected, (set(), set(), set())
    )
    return (
        tuple(sorted(local_ports)),
        tuple(sorted(remote_ports)),
        len(pids),
    )


def clients_for_executable(
    executable: str, allowed_remote_ports: tuple[int, ...] = ()
) -> list[dict[str, object]]:
    """Agrupa portas por processo somente para roteamento da captura."""
    selected = os.path.normcase(os.path.abspath(executable))
    allowed = set(allowed_remote_ports)
    clients: dict[int, tuple[set[int], set[int]]] = {}
    paths: dict[int, str | None] = {}
    rows = _tcp_rows()

    def belongs_to_selected(pid: int) -> bool:
        if pid not in paths:
            paths[pid] = _process_path(pid)
        path = paths[pid]
        return bool(path and os.path.normcase(os.path.abspath(path)) == selected)

    matching_pids = {
        pid for pid, _local_port, _remote_port in rows if belongs_to_selected(pid)
    }
    allowed_pids = {
        pid
        for pid, _local_port, remote_port in rows
        if belongs_to_selected(pid) and (not allowed or remote_port in allowed)
    }
    include_same_pid_local_ports = os.path.basename(selected).casefold().startswith(
        "projectrf"
    )
    eligible_pids = matching_pids if include_same_pid_local_ports else allowed_pids
    for pid, local_port, remote_port in rows:
        if pid not in eligible_pids or not belongs_to_selected(pid):
            continue
        local_ports, remote_ports = clients.setdefault(pid, (set(), set()))
        local_ports.add(local_port)
        if not allowed or remote_port in allowed:
            remote_ports.add(remote_port)
    return [
        {
            "pid": pid,
            "local_ports": tuple(sorted(local_ports)),
            "remote_ports": tuple(sorted(remote_ports)),
        }
        for pid, (local_ports, remote_ports) in sorted(clients.items())
    ]
