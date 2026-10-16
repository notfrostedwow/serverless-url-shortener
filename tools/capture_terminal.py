"""Try a genuine screenshot of our own hidden Windows console, never the desktop."""

from __future__ import annotations

import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path


def child(root: Path) -> int:
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user = ctypes.WinDLL("user32", use_last_error=True)
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    kernel.GetConsoleWindow.restype = wintypes.HWND
    user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.GetDC.argtypes = [wintypes.HWND]
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.UINT,
    ]
    gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    window = kernel.GetConsoleWindow()
    if not window:
        raise RuntimeError("the dedicated child has no capturable console window handle")
    subprocess.run([sys.executable, "tools/demo.py"], cwd=root, check=True)  # noqa: S603
    sys.stdout.flush()
    # Render ONLY our dedicated console offscreen, without activation. A hidden
    # classic console may not paint at all. Never capture the desktop or another window.
    user.SetWindowPos(window, None, -32000, -32000, 0, 0, 0x0015)
    user.ShowWindow(window, 4)
    rectangle = wintypes.RECT()
    if not user.GetClientRect(window, ctypes.byref(rectangle)):
        raise RuntimeError("cannot inspect our own console's client rectangle")
    width, height = rectangle.right, rectangle.bottom
    if not 100 <= width <= 2400 or not 100 <= height <= 1600:
        raise RuntimeError("console capture dimensions are unavailable or outside bounds")
    user.GetDC.restype = wintypes.HDC
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi.SelectObject.restype = wintypes.HGDIOBJ
    source = user.GetDC(window)
    memory = gdi.CreateCompatibleDC(source)
    bitmap = gdi.CreateCompatibleBitmap(source, width, height)
    previous = gdi.SelectObject(memory, bitmap)
    try:
        if not user.PrintWindow(window, memory, 1):
            raise RuntimeError("PrintWindow cannot render the hidden console")
        # A top-down 32-bit DIB; its pixels are the window capture, not rendered text.
        header = struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        info = ctypes.create_string_buffer(header + b"\0" * 16)
        pixels = ctypes.create_string_buffer(width * height * 4)
        if gdi.GetDIBits(memory, bitmap, 0, height, pixels, info, 0) != height:
            raise RuntimeError("cannot read captured console pixels")
        raw = pixels.raw
        if len(set(raw[0::4])) < 2 and len(set(raw[1::4])) < 2:
            raise RuntimeError("the hidden console capture is blank; no image will be claimed")
        rows = bytearray()
        for y in range(height):
            rows.append(0)
            for x in range(width):
                offset = (y * width + x) * 4
                rows.extend((raw[offset + 2], raw[offset + 1], raw[offset]))

        def chunk(kind: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + kind
                + data
                + struct.pack(">I", zlib.crc32(kind + data))
            )

        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
        (root / "docs/validation/local-session.png").write_bytes(png)
    finally:
        user.ShowWindow(window, 0)
        gdi.SelectObject(memory, previous)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(memory)
        user.ReleaseDC(window, source)
    return 0


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = root / "docs/validation/screenshot-attempt.txt"
    try:
        if os.name != "nt":
            raise RuntimeError("this optional capture uses Windows console APIs")
        if "--child" in sys.argv:
            return child(root)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0  # Hidden, isolated console; never inspect the user's desktop.
        process = subprocess.run(  # noqa: S603 -- our own fixed helper and workspace only
            [sys.executable, str(Path(__file__).resolve()), "--child"],
            cwd=root,
            startupinfo=startup,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            timeout=30,
            check=False,
        )
        if process.returncode:
            print(result.read_text(encoding="utf-8"), end="")
            return process.returncode
        result.write_text(
            "$ python tools/capture_terminal.py\n"
            "Captured only the dedicated console after an actual tools/demo.py run.\n"
            "Image still requires visual inspection; no desktop capture or text rendering used.\n",
            encoding="utf-8",
        )
        print(result.read_text(encoding="utf-8"), end="")
        return 0
    except Exception as exc:
        result.write_text(
            "$ python tools/capture_terminal.py\n"
            f"Screenshot unavailable: {type(exc).__name__}: {exc}\n"
            "No screenshot is claimed; actual HTTP transcript is in local-demo.txt.\n",
            encoding="utf-8",
        )
        print(result.read_text(encoding="utf-8"), end="")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
