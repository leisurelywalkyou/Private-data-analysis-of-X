"""内嵌音乐播放器：用 Windows MCI 顺序播放音乐目录下的 mp3 / wav。

不引入第三方运行时依赖，播放为异步，不阻塞桌宠动画。
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

AUDIO_SUFFIXES = (".mp3", ".wav")


class MusicPlayer:
    """播放 assets/music 下的音频；非 Windows 环境自动禁用。"""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.tracks: list[Path] = []
        self.index = 0
        self.playing = False
        self._opened: Path | None = None
        self.alias = f"xmonitor_music_{os.getpid()}"
        self._winmm = None
        if sys.platform == "win32":
            self._winmm = ctypes.WinDLL("winmm")
            self._winmm.mciSendStringW.argtypes = (
                ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint,
                ctypes.c_void_p)
            self._winmm.mciSendStringW.restype = ctypes.c_uint
        self.rescan()

    @property
    def available(self) -> bool:
        return self._winmm is not None

    def rescan(self):
        """重新扫描目录，支持运行中直接放入新音乐。"""
        tracks = []
        if self.folder.is_dir():
            tracks = [path for path in self.folder.iterdir()
                      if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES]
        self.tracks = sorted(tracks, key=lambda path: path.name.lower())
        self.index = min(self.index, len(self.tracks) - 1) if self.tracks else 0

    def current(self) -> Path | None:
        return self.tracks[self.index] if self.tracks else None

    def mode(self) -> str:
        if self._winmm is None:
            return "stopped"
        buf = ctypes.create_unicode_buffer(32)
        if self._winmm.mciSendStringW(f"status {self.alias} mode", buf, 31, None):
            return "stopped"
        return buf.value or "stopped"

    def _send(self, command: str) -> bool:
        if self._winmm is None:
            return False
        return self._winmm.mciSendStringW(command, None, 0, None) == 0

    def _close(self):
        if self._opened is not None:
            self._send(f"close {self.alias}")
            self._opened = None

    def play(self, index: int | None = None) -> bool:
        if not self.available or not self.tracks:
            return False
        if index is not None:
            self.index = index % len(self.tracks)
        path = self.current()
        if path is None:
            return False
        if self._opened != path:
            self._close()
            kind = "mpegvideo" if path.suffix.lower() == ".mp3" else "waveaudio"
            if not self._send(f'open "{path}" type {kind} alias {self.alias}'):
                return False
            self._opened = path
        self._send(f"seek {self.alias} to start")
        if not self._send(f"play {self.alias}"):
            return False
        self.playing = True
        return True

    def toggle(self) -> bool:
        mode = self.mode()
        if mode == "playing":
            self._send(f"pause {self.alias}")
            self.playing = False
        elif mode == "paused":
            self._send(f"resume {self.alias}")
            self.playing = True
        else:
            return self.play()
        return self.playing

    def stop(self):
        if self._opened is not None:
            self._send(f"stop {self.alias}")
            self._send(f"seek {self.alias} to start")
        self.playing = False

    def next(self) -> bool:
        if not self.tracks:
            return False
        self.index = (self.index + 1) % len(self.tracks)
        return self.play()

    def previous(self) -> bool:
        if not self.tracks:
            return False
        self.index = (self.index - 1) % len(self.tracks)
        return self.play()

    def close(self):
        self._close()
        self.playing = False
