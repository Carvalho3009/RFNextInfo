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


def connected_processes() -> dict[str, tuple[set[int], set[int]]]:
    """Retorna caminho -> (PIDs, portas locais), sem IPs ou payloads."""
    result: dict[str, tuple[set[int], set[int]]] = {}
    paths: dict[int, str | None] = {}
    for pid, local_port, _remote_port in _tcp_rows():
        if pid not in paths:
            paths[pid] = _process_path(pid)
        path = paths[pid]
        if not path:
            continue
        key = os.path.normcase(os.path.abspath(path))
        pids, ports = result.setdefault(key, (set(), set()))
        pids.add(pid)
        ports.add(local_port)
    return result


def ports_for_executable(executable: str) -> tuple[tuple[int, ...], int]:
    selected = os.path.normcase(os.path.abspath(executable))
    pids, ports = connected_processes().get(selected, (set(), set()))
    return tuple(sorted(ports)), len(pids)
