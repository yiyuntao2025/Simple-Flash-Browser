from __future__ import annotations

import os
import re
import struct
from dataclasses import dataclass
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FLASH_VERSION = "32.0.0.465"

_MACHINE_X86 = 0x014C
_MACHINE_X64 = 0x8664


@dataclass(frozen=True)
class FlashInstall:
    path: Path | None = None
    version: str = DEFAULT_FLASH_VERSION
    source: str = "未找到"
    hint: str = ""

    @property
    def available(self) -> bool:
        return self.path is not None


def _pe_machine(path: Path) -> int | None:
    try:
        with path.open("rb") as handle:
            if handle.read(2) != b"MZ":
                return None
            handle.seek(0x3C)
            offset = int.from_bytes(handle.read(4), "little")
            handle.seek(offset)
            if handle.read(4) != b"PE\0\0":
                return None
            return int.from_bytes(handle.read(2), "little")
    except OSError:
        return None


def _expected_machine() -> int:
    return _MACHINE_X64 if struct.calcsize("P") == 8 else _MACHINE_X86


def _glob(base: Path | None, pattern: str, source: str):
    if base is None:
        return
    try:
        if not base.exists():
            return
        for path in sorted(base.glob(pattern), key=lambda item: str(item).lower(), reverse=True):
            if path.is_file():
                yield path, source
    except OSError:
        return


def _version_from(path: Path) -> str:
    match = re.search(r"pepflashplayer(?:64)?_(\d+)_(\d+)_(\d+)_(\d+)", path.name, re.IGNORECASE)
    if match:
        return ".".join(match.groups())
    match = re.search(r"(\d+)_(\d+)_(\d+)_(\d+)", str(path))
    if match:
        return ".".join(match.groups())
    return DEFAULT_FLASH_VERSION


def _candidates():
    override = os.environ.get("FLASH_PEPPER_DLL")
    if override:
        yield Path(override), "环境变量 FLASH_PEPPER_DLL"

    yield from _glob(APP_ROOT / "pepperflash", "**/pepflashplayer*.dll", "程序目录 pepperflash")
    yield from _glob(APP_ROOT, "pepflashplayer*.dll", "程序目录")

    local = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("PROGRAMFILES")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)")
    windir = os.environ.get("WINDIR")
    appdata = os.environ.get("APPDATA")

    chrome_roots = [
        Path(local) / "Google/Chrome/Application" if local else None,
        Path(program_files) / "Google/Chrome/Application" if program_files else None,
        Path(program_files_x86) / "Google/Chrome/Application" if program_files_x86 else None,
    ]
    for root in chrome_roots:
        yield from _glob(root, "**/PepperFlash/**/pepflashplayer*.dll", "Google Chrome")
        yield from _glob(root, "**/pepflashplayer*.dll", "Google Chrome")

    chromium_roots = [
        Path(local) / "Chromium/Application" if local else None,
        Path(appdata) / "../Local/Chromium/Application" if appdata else None,
    ]
    for root in chromium_roots:
        yield from _glob(root, "**/pepflashplayer*.dll", "Chromium")

    edge_roots = [
        Path(program_files) / "Microsoft/Edge/Application" if program_files else None,
        Path(program_files_x86) / "Microsoft/Edge/Application" if program_files_x86 else None,
    ]
    for root in edge_roots:
        yield from _glob(root, "**/pepflashplayer*.dll", "Microsoft Edge")

    flash_roots = [
        Path(windir) / "System32/Macromed/Flash" if windir else None,
        Path(windir) / "SysWOW64/Macromed/Flash" if windir else None,
    ]
    for root in flash_roots:
        yield from _glob(root, "pepflashplayer*.dll", "Adobe Flash Player")

    adobe_roots = [
        Path(program_files) / "Adobe/Flash Player" if program_files else None,
        Path(program_files_x86) / "Adobe/Flash Player" if program_files_x86 else None,
    ]
    for root in adobe_roots:
        yield from _glob(root, "**/pepflashplayer*.dll", "Adobe Flash Player")

    broad_roots = [
        (Path(appdata) if appdata else None, "用户程序目录"),
        (Path(local) if local else None, "用户程序目录"),
        (Path(program_files) if program_files else None, "Program Files"),
        (Path(program_files_x86) if program_files_x86 else None, "Program Files (x86)"),
    ]
    for root, label in broad_roots:
        yield from _glob(root, "*/*/pepflashplayer*.dll", label)
        yield from _glob(root, "*/*/*/pepflashplayer*.dll", label)


def find_pepper_flash() -> FlashInstall:
    expected = _expected_machine()
    seen: set[str] = set()
    hint = ""
    for path, source in _candidates():
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            if path.stat().st_size < 500_000:
                continue
        except OSError:
            continue
        machine = _pe_machine(path)
        if machine is None:
            continue
        if machine != expected:
            if not hint:
                bits = "64" if machine == _MACHINE_X64 else "32"
                need = "64" if expected == _MACHINE_X64 else "32"
                hint = f"发现 {bits} 位 Flash（{path.name}），当前程序需要 {need} 位版本。"
            continue
        return FlashInstall(path=path, version=_version_from(path), source=source)
    return FlashInstall(hint=hint)


def _space_free_path(path: Path) -> str:
    text = str(path)
    if " " not in text:
        return text
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetShortPathNameW(text, buffer, 32768)
        if length:
            return buffer.value
    except Exception:
        pass
    return text


def chromium_flags(flash: FlashInstall) -> list[str]:
    if not flash.available:
        return []
    path = _space_free_path(flash.path)
    if " " in path:
        path = f'"{path}"'
    return [
        f"--ppapi-flash-path={path}",
        f"--ppapi-flash-version={flash.version}",
        "--allow-outdated-plugins",
        "--disable-features=FlashDeprecationWarning",
    ]


def configure_environment(flash: FlashInstall) -> None:
    existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    parts = [existing] if existing else []
    parts.extend(chromium_flags(flash))
    if parts:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(parts)
