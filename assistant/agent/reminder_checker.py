"""
后台提醒检查器

在主进程的 asyncio 事件循环中运行，每 15 秒检查一次是否有到期的提醒。
到期时在终端打印通知。
"""

import json
import asyncio
import datetime
from pathlib import Path

REMINDERS_FILE = Path.home() / ".ai_assistant" / "reminders" / "reminders.json"


def _load_reminders() -> list[dict]:
    if REMINDERS_FILE.exists():
        try:
            return json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return []
    return []


def _save_reminders(reminders: list[dict]):
    REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    REMINDERS_FILE.write_text(
        json.dumps(reminders, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def reminder_loop():
    """后台循环，定期检查到期提醒"""
    while True:
        try:
            _check_and_notify()
        except Exception:
            pass  # 后台任务不应因异常崩溃
        await asyncio.sleep(15)  # 每 15 秒检查一次


def _check_and_notify():
    """检查是否有到期提醒，触发通知"""
    reminders = _load_reminders()
    now = datetime.datetime.now()
    changed = False

    for r in reminders:
        if r.get("triggered"):
            continue
        try:
            target = datetime.datetime.fromisoformat(r["target_time"])
        except (ValueError, KeyError):
            continue

        if now >= target:
            # 到期，打印通知
            r["triggered"] = True
            changed = True
            _print_notification(r["message"], target)

    if changed:
        # 保存状态，清理已触发的提醒
        reminders = [r for r in reminders if not r.get("triggered")]
        _save_reminders(reminders)


def _print_notification(message: str, target_time: datetime.datetime):
    """在终端打印提醒通知"""
    time_str = target_time.strftime("%H:%M")
    print(f"\n{'=' * 50}")
    print(f"  [提醒] {time_str} - {message}")
    print(f"{'=' * 50}")
    print("你: ", end="", flush=True)  # 恢复输入提示符
