"""本周计划：固定 6 个时段，每个时段可放多个带标题与自定义时间的任务。"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta

from .config import data_dir

WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
SLOTS = (
    {"label": "凌晨", "start": 0, "end": 360},
    {"label": "早晨", "start": 360, "end": 540},
    {"label": "上午", "start": 540, "end": 720},
    {"label": "午间", "start": 720, "end": 840},
    {"label": "下午", "start": 840, "end": 1080},
    {"label": "晚间", "start": 1080, "end": 1440},
)
LEAD_MINUTES = 10


def schedule_path(cfg: dict):
    return data_dir(cfg) / "schedule.json"


def parse_clock(text) -> int | None:
    """把 HH:MM 转成一天内的分钟数；非法格式返回 None。"""
    text = str(text or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def format_clock(minutes: int) -> str:
    minutes = int(minutes)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def slot_bounds(slot: int) -> tuple[int, int]:
    spec = SLOTS[slot]
    return spec["start"], spec["end"]


def slot_summary(slot: int) -> str:
    start, end = slot_bounds(slot)
    return f"{SLOTS[slot]['label']} {format_clock(start)}-{format_clock(end)}"


def _slot_for_hour(hour: int) -> int:
    minutes = max(0, min(1439, int(hour) * 60))
    for index, spec in enumerate(SLOTS):
        if spec["start"] <= minutes < spec["end"]:
            return index
    return len(SLOTS) - 1


def _parse_key(key) -> tuple[int, int] | None:
    """兼容新键 day:slot 与旧版 day-hour（按小时归入对应时段）。"""
    text = str(key or "")
    if ":" in text:
        try:
            day, slot = text.split(":", 1)
            day, slot = int(day), int(slot)
        except ValueError:
            return None
        if 0 <= day <= 6 and 0 <= slot < len(SLOTS):
            return day, slot
        return None
    if "-" in text:
        try:
            day, hour = text.split("-", 1)
            day, hour = int(day), int(hour)
        except ValueError:
            return None
        if 0 <= day <= 6 and 0 <= hour <= 23:
            return day, _slot_for_hour(hour)
    return None


def _fallback_id(day: int, slot: int, index: int, raw) -> str:
    payload = json.dumps(raw, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha1(
        f"{day}:{slot}:{index}:{payload}".encode("utf-8")).hexdigest()
    return f"t{digest[:10]}"


def _normalize_task(value, slot: int, fallback_id: str) -> dict | None:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return {"id": fallback_id, "title": text[:12], "text": text,
                "start": "", "end": ""}
    if not isinstance(value, dict):
        return None
    title = str(value.get("title") or "").strip()
    text = str(value.get("text") or "").strip()
    if not title and text:
        title = text[:12]
    if not title:
        return None
    start = str(value.get("start") or "").strip()
    end = str(value.get("end") or "").strip()
    start_min, end_min = parse_clock(start), parse_clock(end)
    lower, upper = slot_bounds(slot)
    if (start_min is None or end_min is None
            or not (lower <= start_min < end_min <= upper)):
        start, end = "", ""
    else:
        start, end = format_clock(start_min), format_clock(end_min)
    return {"id": str(value.get("id") or fallback_id), "title": title,
            "text": text, "start": start, "end": end}


def _normalize_list(value, day: int, slot: int) -> list[dict]:
    values = value if isinstance(value, list) else [value]
    tasks = []
    for index, raw in enumerate(values):
        task = _normalize_task(raw, slot,
                               _fallback_id(day, slot, index, raw))
        if task:
            tasks.append(task)
    return tasks


def load(cfg: dict) -> dict[str, list[dict]]:
    """读取任务表；兼容旧版单任务与纯文本格式。"""
    path = schedule_path(cfg)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = raw.get("tasks") if isinstance(raw, dict) else None
    if not isinstance(items, dict):
        return {}
    tasks: dict[str, list[dict]] = {}
    for key, value in items.items():
        parsed = _parse_key(key)
        if parsed is None:
            continue
        day, slot = parsed
        normalized = _normalize_list(value, day, slot)
        if normalized:
            target = f"{day}:{slot}"
            tasks.setdefault(target, []).extend(normalized)
    return tasks


def save(cfg: dict, tasks: dict[str, list[dict]]) -> None:
    path = schedule_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {}
    for key, value in tasks.items():
        parsed = _parse_key(key)
        if parsed is None:
            continue
        day, slot = parsed
        normalized = _normalize_list(value, day, slot)
        if normalized:
            clean[f"{day}:{slot}"] = normalized
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"version": 3, "tasks": clean},
                              ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def validate_times(slot: int, start: str, end: str) -> tuple[str, str]:
    start = str(start or "").strip()
    end = str(end or "").strip()
    if not start and not end:
        return "", ""
    if bool(start) != bool(end):
        raise ValueError("开始和结束时间需要同时填写")
    start_min, end_min = parse_clock(start), parse_clock(end)
    if start_min is None or end_min is None:
        raise ValueError("时间格式应为 HH:MM")
    lower, upper = slot_bounds(slot)
    if not (lower <= start_min < end_min <= upper):
        raise ValueError(
            f"自定义时间需在 {format_clock(lower)}-{format_clock(upper)} 内，"
            "且开始早于结束")
    return format_clock(start_min), format_clock(end_min)


def _check_slot(weekday: int, slot: int) -> None:
    if not (0 <= weekday <= 6 and 0 <= slot < len(SLOTS)):
        raise ValueError("时段参数不合法")


def add_task(cfg: dict, weekday: int, slot: int, title: str, text: str,
             start: str = "", end: str = "") -> dict:
    _check_slot(weekday, slot)
    title = str(title or "").strip()
    if not title:
        raise ValueError("请填写任务标题")
    text = str(text or "").strip()
    start, end = validate_times(slot, start, end)
    task = {"id": uuid.uuid4().hex[:10], "title": title, "text": text,
            "start": start, "end": end}
    tasks = load(cfg)
    tasks.setdefault(f"{weekday}:{slot}", []).append(task)
    save(cfg, tasks)
    return task


def update_task(cfg: dict, weekday: int, slot: int, task_id: str, title: str,
                text: str, start: str = "", end: str = "") -> dict:
    _check_slot(weekday, slot)
    title = str(title or "").strip()
    if not title:
        raise ValueError("请填写任务标题")
    text = str(text or "").strip()
    start, end = validate_times(slot, start, end)
    tasks = load(cfg)
    key = f"{weekday}:{slot}"
    for index, task in enumerate(tasks.get(key, [])):
        if task["id"] == task_id:
            updated = {"id": task_id, "title": title, "text": text,
                       "start": start, "end": end}
            tasks[key][index] = updated
            save(cfg, tasks)
            return updated
    raise ValueError("任务不存在，可能已被删除")


def delete_task(cfg: dict, weekday: int, slot: int, task_id: str) -> bool:
    _check_slot(weekday, slot)
    tasks = load(cfg)
    key = f"{weekday}:{slot}"
    items = tasks.get(key, [])
    remaining = [task for task in items if task["id"] != task_id]
    if len(remaining) == len(items):
        return False
    if remaining:
        tasks[key] = remaining
    else:
        tasks.pop(key, None)
    save(cfg, tasks)
    return True


def slot_tasks(cfg: dict, weekday: int, slot: int) -> list[dict]:
    return list(load(cfg).get(f"{weekday}:{slot}", []))


def day_entries(cfg: dict, weekday: int) -> list[dict]:
    """返回某天的全部任务，包含实际生效的起止时间（分钟）。"""
    tasks = load(cfg)
    entries = []
    for slot, spec in enumerate(SLOTS):
        for task in tasks.get(f"{weekday}:{slot}", []):
            start = parse_clock(task["start"])
            end = parse_clock(task["end"])
            if start is None:
                start = spec["start"]
            if end is None:
                end = spec["end"]
            entries.append({
                "key": f"{weekday}:{slot}:{task['id']}",
                "task_id": task["id"],
                "slot": slot,
                "label": spec["label"],
                "title": task["title"],
                "text": task["text"],
                "start": start,
                "end": end,
                "start_text": format_clock(start),
                "end_text": format_clock(end),
                "custom": bool(task["start"]),
            })
    entries.sort(key=lambda item: (item["start"], item["title"]))
    return entries


def current_slot(when: datetime) -> int:
    return _slot_for_hour(when.hour)


def week_range(when: datetime) -> tuple[datetime, datetime]:
    start = (when - timedelta(days=when.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=6)


def week_dates(when: datetime) -> list[datetime]:
    start, _ = week_range(when)
    return [start + timedelta(days=index) for index in range(7)]
