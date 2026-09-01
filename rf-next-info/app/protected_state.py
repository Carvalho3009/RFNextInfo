"""Proteção local de estado com DPAPI nativa do Windows."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

CRYPTPROTECT_UI_FORBIDDEN = 0x1
CRYPTPROTECT_LOCAL_MACHINE = 0x4


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _libraries():
    if os.name != "nt":
        raise OSError("DPAPI requer Windows")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    for function in (
        crypt32.CryptProtectData,
        crypt32.CryptUnprotectData,
    ):
        function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    return crypt32, kernel32


def _input(value: bytes) -> tuple[_DataBlob, object]:
    buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    return _DataBlob(len(value), buffer), buffer


def _result(blob: _DataBlob, kernel32) -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        if blob.pbData:
            kernel32.LocalFree(blob.pbData)


def _protect(value: bytes, description: str, flags: int) -> bytes:
    crypt32, kernel32 = _libraries()
    source, _buffer = _input(value)
    target = _DataBlob()
    if not crypt32.CryptProtectData(
        ctypes.byref(source),
        description,
        None,
        None,
        None,
        flags | CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(target),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return _result(target, kernel32)


def protect(value: bytes) -> bytes:
    """Mantém o escopo de máquina usado pelo estado legado da licença."""
    return _protect(value, "RF QOL licença", CRYPTPROTECT_LOCAL_MACHINE)


def protect_for_current_user(
    value: bytes, *, description: str = "RF QOL estado privado"
) -> bytes:
    """Protege segredo novo para o usuário Windows atual, sem interface."""
    return _protect(value, description, 0)


def unprotect(value: bytes) -> bytes:
    crypt32, kernel32 = _libraries()
    source, _buffer = _input(value)
    target = _DataBlob()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(target),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return _result(target, kernel32)
