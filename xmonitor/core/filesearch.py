"""本机文件检索：按多个范围顺序扫描，并按名称、后缀与类型筛选。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .config import data_dir

MAX_RESULTS = 3000

CATEGORIES = {
    "文档": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
             ".txt", ".md", ".rtf", ".csv", ".odt", ".ods", ".odp", ".epub"},
    "图片": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff",
             ".svg", ".ico", ".heic"},
    "音频": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".ape"},
    "视频": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
    "压缩包": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"},
    "代码": {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json",
             ".xml", ".yaml", ".yml", ".ini", ".toml", ".sql", ".java", ".c",
             ".h", ".cpp", ".cs", ".go", ".rs", ".php", ".sh", ".bat", ".ps1"},
}
CATEGORY_NAMES = ("全部", *CATEGORIES.keys(), "其他")


def scopes_path(cfg: dict):
    return data_dir(cfg) / "file_scopes.json"


def load_scopes(cfg: dict) -> list[dict]:
    """读取检索范围；兼容旧版纯路径列表（默认包含子文件夹）。"""
    path = scopes_path(cfg)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = raw.get("scopes") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    scopes = []
    for item in items:
        if isinstance(item, dict):
            value = str(item.get("path") or "").strip()
            recursive = bool(item.get("recursive", True))
        else:
            value, recursive = str(item).strip(), True
        if value:
            scopes.append({"path": value, "recursive": recursive})
    return scopes


def save_scopes(cfg: dict, scopes: list) -> None:
    path = scopes_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = []
    for item in scopes:
        if isinstance(item, dict):
            value = str(item.get("path") or "").strip()
            recursive = bool(item.get("recursive", True))
        else:
            value, recursive = str(item).strip(), True
        if value:
            clean.append({"path": value, "recursive": recursive})
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"scopes": clean}, ensure_ascii=False,
                              indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def parse_extensions(text: str) -> set[str]:
    """把逗号/空格分隔的后缀转成 {'.pdf', '.png'}。"""
    out = set()
    for part in re.split(r"[,，;；\s]+", str(text or "")):
        part = part.strip().lower()
        if not part:
            continue
        out.add(part if part.startswith(".") else f".{part}")
    return out


def category_of(ext: str) -> str:
    ext = str(ext or "").lower()
    for name, extensions in CATEGORIES.items():
        if ext in extensions:
            return name
    return "其他"


def _scope_pair(raw) -> tuple[str, bool]:
    if isinstance(raw, dict):
        return str(raw.get("path") or ""), bool(raw.get("recursive", True))
    return str(raw), True


def _walk(root: Path, recursive: bool):
    """返回 (目录, 文件名列表)；仅当前文件夹时不做递归。"""
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            yield dirpath, filenames
        return
    try:
        names = sorted(entry.name for entry in os.scandir(root)
                       if entry.is_file())
    except OSError:
        return
    yield str(root), names


def search(scopes: list, *, name: str = "", extensions: set[str] | None = None,
           category: str = "全部", stop_event=None,
           limit: int = MAX_RESULTS) -> list[dict]:
    """按范围顺序检索文件；同一文件只保留第一次出现的结果。"""
    keyword = str(name or "").strip().lower()
    exts = {str(ext).lower() for ext in (extensions or set())}
    results: list[dict] = []
    seen: set[str] = set()
    for scope_index, raw in enumerate(scopes):
        raw_path, recursive = _scope_pair(raw)
        root = Path(raw_path).expanduser()
        if not root.is_dir():
            continue
        for dirpath, filenames in _walk(root, recursive):
            if stop_event is not None and stop_event.is_set():
                return results
            for filename in sorted(filenames):
                if filename.startswith("."):
                    continue
                if keyword and keyword not in filename.lower():
                    continue
                ext = Path(filename).suffix.lower()
                if exts and ext not in exts:
                    continue
                kind = category_of(ext)
                if category and category != "全部" and kind != category:
                    continue
                path = Path(dirpath) / filename
                try:
                    stat = path.stat()
                    key = str(path.resolve()).lower()
                except OSError:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    "path": str(path),
                    "name": filename,
                    "ext": ext,
                    "category": kind,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "scope": str(root),
                    "scope_index": scope_index,
                    "recursive": recursive,
                })
                if len(results) >= limit:
                    return results
    return results
