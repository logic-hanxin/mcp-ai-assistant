"""
每日热点新闻推送检查器

每天指定时间（默认 08:00）自动获取热点新闻并通过 QQ 发送。
支持通过环境变量配置：
  NEWS_NOTIFY_QQ   - 接收新闻的QQ号（必填，否则不推送）
  NEWS_SEND_TIME   - 每天发送时间，格式 HH:MM，默认 08:00
"""

import os
import json
import asyncio
import datetime
from pathlib import Path

import httpx

NAPCAT_API_URL = os.getenv("NAPCAT_API_URL", "http://127.0.0.1:3000")
NEWS_NOTIFY_QQ = os.getenv("NEWS_NOTIFY_QQ", "")
NEWS_SEND_TIME = os.getenv("NEWS_SEND_TIME", "08:00")

# 记录上次推送日期，防止同一天重复推送
NEWS_STATE_DIR = Path.home() / ".ai_assistant" / "news"
NEWS_STATE_FILE = NEWS_STATE_DIR / "state.json"


def _load_state() -> dict:
    if NEWS_STATE_FILE.exists():
        try:
            return json.loads(NEWS_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_state(state: dict):
    NEWS_STATE_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def news_check_loop():
    """后台循环，每天定时推送热点新闻"""
    # 首次启动延迟 15 秒
    await asyncio.sleep(15)

    while True:
        try:
            await _check_and_send()
        except Exception:
            pass
        # 每 60 秒检查一次是否到了推送时间
        await asyncio.sleep(60)


async def _check_and_send():
    """检查是否到了推送时间，并且今天还没推送过"""
    if not NEWS_NOTIFY_QQ:
        return

    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    # 解析目标时间
    try:
        parts = NEWS_SEND_TIME.strip().split(":")
        target_hour = int(parts[0])
        target_minute = int(parts[1])
    except (ValueError, IndexError):
        target_hour, target_minute = 8, 0

    # 还没到推送时间
    if now.hour < target_hour or (now.hour == target_hour and now.minute < target_minute):
        return

    # 检查今天是否已推送
    state = _load_state()
    if state.get("last_send_date") == today_str:
        return

    # 获取新闻并推送
    news_text = await _fetch_news()
    if not news_text:
        return

    success = await _send_to_qq(NEWS_NOTIFY_QQ, news_text)

    if success:
        state["last_send_date"] = today_str
        _save_state(state)
        print(f"  [每日新闻] 已推送给 QQ:{NEWS_NOTIFY_QQ}")


async def _fetch_news() -> str:
    """异步获取热点新闻并格式化"""
    from assistant.skills.news_skill import fetch_hot_news, format_news_text

    # fetch_hot_news 是同步的 (httpx 同步调用)，放到线程中执行
    loop = asyncio.get_event_loop()
    news = await loop.run_in_executor(None, fetch_hot_news)

    if not news:
        return ""

    now = datetime.datetime.now()
    date_str = now.strftime("%Y年%m月%d日")
    weekdays = "一二三四五六日"
    weekday = weekdays[now.weekday()]

    lines = [f"早上好！今天是{date_str} 星期{weekday}", ""]

    for source, titles in news.items():
        lines.append(f"【{source}】")
        for i, title in enumerate(titles[:10], 1):
            lines.append(f"  {i}. {title}")
        lines.append("")

    lines.append("祝你今天也元气满满！")
    return "\n".join(lines)


async def _send_to_qq(qq_number: str, text: str) -> bool:
    """通过 NapCat 发送私聊消息"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{NAPCAT_API_URL}/send_private_msg",
                json={
                    "user_id": int(qq_number),
                    "message": [{"type": "text", "data": {"text": text}}],
                },
            )
            data = resp.json()
            return data.get("status") == "ok" or data.get("retcode") == 0
    except Exception as e:
        print(f"  [每日新闻推送失败] {e}")
        return False
