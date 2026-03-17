"""
后台提醒检查器

每 15 秒检查一次是否有到期提醒。
- 有 QQ 信息: 通过 NapCat API 发送 QQ 消息
- 无 QQ 信息: 在终端打印（终端模式）
"""

import os
import json
import asyncio
import datetime
from pathlib import Path

import httpx

REMINDERS_FILE = Path.home() / ".ai_assistant" / "reminders" / "reminders.json"
NAPCAT_API_URL = os.getenv("NAPCAT_API_URL", "http://127.0.0.1:3000")


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
            await _check_and_notify()
        except Exception:
            pass  # 后台任务不应因异常崩溃
        await asyncio.sleep(15)


async def _check_and_notify():
    """检查到期提醒并发送通知"""
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
            r["triggered"] = True
            changed = True
            await _send_notification(r)

    if changed:
        reminders = [r for r in reminders if not r.get("triggered")]
        _save_reminders(reminders)


async def _send_notification(reminder: dict):
    """根据提醒的通知目标发送消息"""
    message = reminder.get("message", "")
    target_time = reminder.get("target_time", "")
    notify_qq = reminder.get("notify_qq", "")
    notify_group_id = reminder.get("notify_group_id", "")

    try:
        time_str = datetime.datetime.fromisoformat(target_time).strftime("%H:%M")
    except Exception:
        time_str = "?"

    text = f"[定时提醒] {time_str} - {message}"

    # 有 QQ 号: 通过 NapCat 发送
    if notify_qq:
        try:
            if notify_group_id:
                # 群聊 @提醒
                await _send_qq_group_msg(
                    int(notify_group_id), text, at_user=int(notify_qq)
                )
            else:
                # 私聊提醒
                await _send_qq_private_msg(int(notify_qq), text)
            print(f"  [提醒已发送] QQ:{notify_qq} - {message}")
        except Exception as e:
            print(f"  [提醒发送失败] QQ:{notify_qq} - {e}")
            # 降级为终端打印
            _print_notification(message, time_str)
    else:
        # 无 QQ 信息: 终端打印（终端模式下使用）
        _print_notification(message, time_str)


async def _send_qq_private_msg(user_id: int, text: str):
    """通过 NapCat 发送私聊消息"""
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{NAPCAT_API_URL}/send_private_msg", json={
            "user_id": user_id,
            "message": [{"type": "text", "data": {"text": text}}],
        })


async def _send_qq_group_msg(group_id: int, text: str, at_user: int | None = None):
    """通过 NapCat 发送群聊消息"""
    message = []
    if at_user:
        message.append({"type": "at", "data": {"qq": str(at_user)}})
        message.append({"type": "text", "data": {"text": " "}})
    message.append({"type": "text", "data": {"text": text}})

    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{NAPCAT_API_URL}/send_group_msg", json={
            "group_id": group_id,
            "message": message,
        })


def _print_notification(message: str, time_str: str):
    """终端模式下打印提醒"""
    print(f"\n{'=' * 50}")
    print(f"  [提醒] {time_str} - {message}")
    print(f"{'=' * 50}")
    print("你: ", end="", flush=True)
