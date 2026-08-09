from __future__ import annotations

import ctypes
import errno
import os
import sys
from pathlib import Path


def rename_directory_no_replace(source: Path, destination: Path) -> None:
    """Atomically publish one directory without replacing an existing path."""
    if os.name == "nt":
        # Windows rename already refuses every existing destination.
        os.rename(source, destination)
        return
    if sys.platform.startswith("linux"):
        _linux_rename_no_replace(source, destination)
        return
    if sys.platform == "darwin":
        _macos_rename_no_replace(source, destination)
        return
    raise OSError(
        errno.ENOTSUP,
        "atomic no-replace directory finalization is unavailable on this platform",
        destination,
    )


def _linux_rename_no_replace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as exc:
        raise OSError(
            errno.ENOTSUP,
            "renameat2 is unavailable for atomic no-replace finalization",
            destination,
        ) from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    at_fdcwd = -100
    rename_noreplace = 1
    result = renameat2(
        at_fdcwd,
        os.fsencode(source),
        at_fdcwd,
        os.fsencode(destination),
        rename_noreplace,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), destination)


def _macos_rename_no_replace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renamex_np = libc.renamex_np
    except AttributeError as exc:
        raise OSError(
            errno.ENOTSUP,
            "renamex_np is unavailable for atomic no-replace finalization",
            destination,
        ) from exc
    renamex_np.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
    renamex_np.restype = ctypes.c_int
    rename_excl = 0x00000004
    result = renamex_np(
        os.fsencode(source),
        os.fsencode(destination),
        rename_excl,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), destination)
