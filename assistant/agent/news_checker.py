"""
每日热点新闻推送检查器

每天指定时间（默认 08:00）自动获取热点新闻，
经 AI 阅读分析后提取重要信息，生成精华摘要推送。

支持通过环境变量配置：
  NEWS_NOTIFY_QQ   - 接收新闻的QQ号（必填，否则不推送）
  NEWS_SEND_TIME   - 每天发送时间，格式 HH:MM，默认 08:00
"""

import os
import asyncio
import datetime

import httpx
from openai import OpenAI

from assistant.agent import db

NAPCAT_API_URL = os.getenv("NAPCAT_API_URL", "http://127.0.0.1:3000")
NEWS_NOTIFY_QQ = os.getenv("NEWS_NOTIFY_QQ", "")
NEWS_SEND_TIME = os.getenv("NEWS_SEND_TIME", "08:00")

_NEWS_DIGEST_PROMPT = """你是一位资深新闻编辑。下面是今天从多个平台获取的热搜标题，请你：

1. 从中筛选出最重要、最有价值的 8-10 条新闻
2. 为每条新闻写一句话简要说明（不是只复述标题，而是补充背景或意义）
3. 在最后用 2-3 句话总结今天的新闻整体趋势/氛围
4. 语气轻松自然，像朋友给你讲今天发生了什么

格式要求：
- 每条新闻一行，带序号
- 最后的总结用"---"分隔
- 不要加多余的标题或装饰"""


async def news_check_loop():
    """后台循环，每天定时推送热点新闻"""
    await asyncio.sleep(15)

    while True:
        try:
            await _check_and_send()
        except Exception:
            pass
        await asyncio.sleep(60)


async def _check_and_send():
    """检查是否到了推送时间，并且今天还没推送过"""
    if not NEWS_NOTIFY_QQ:
        return

    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    try:
        parts = NEWS_SEND_TIME.strip().split(":")
        target_hour = int(parts[0])
        target_minute = int(parts[1])
    except (ValueError, IndexError):
        target_hour, target_minute = 8, 0

    if now.hour < target_hour or (now.hour == target_hour and now.minute < target_minute):
        return

    try:
        last_date = db.news_state_get("last_send_date")
    except Exception:
        last_date = ""
    if last_date == today_str:
        return

    # 获取原始新闻
    raw_news = await _fetch_raw_news()
    if not raw_news:
        return

    # AI 分析生成摘要
    digest = await _generate_digest(raw_news, now)
    if not digest:
        return

    success = await _send_to_qq(NEWS_NOTIFY_QQ, digest)

    if success:
        try:
            db.news_state_set("last_send_date", today_str)
        except Exception:
            pass
        print(f"  [每日新闻] AI摘要已推送给 QQ:{NEWS_NOTIFY_QQ}")


async def _fetch_raw_news() -> str:
    """获取原始新闻标题，合并为文本"""
    from assistant.skills.news_skill import fetch_hot_news

    loop = asyncio.get_event_loop()
    news = await loop.run_in_executor(None, fetch_hot_news)

    if not news:
        return ""

    lines = []
    for source, titles in news.items():
        lines.append(f"【{source}】")
        for i, title in enumerate(titles, 1):
            lines.append(f"  {i}. {title}")
        lines.append("")

    return "\n".join(lines)


async def _generate_digest(raw_news: str, now: datetime.datetime) -> str:
    """用 LLM 分析原始新闻，生成精华摘要"""
    date_str = now.strftime("%Y年%m月%d日")
    weekdays = "一二三四五六日"
    weekday = weekdays[now.weekday()]

    try:
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

        if not api_key:
            print("[每日新闻] 未配置 DEEPSEEK_API_KEY，跳过AI摘要")
            return ""

        client = OpenAI(api_key=api_key, base_url=base_url)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _NEWS_DIGEST_PROMPT},
                    {"role": "user", "content": f"今天是{date_str} 星期{weekday}\n\n{raw_news}"},
                ],
                temperature=0.7,
                max_tokens=1000,
            ),
        )

        digest = response.choices[0].message.content or ""
        if not digest:
            return ""

        return f"早上好！今天是{date_str} 星期{weekday}\n\n{digest}"

    except Exception as e:
        print(f"[每日新闻] AI摘要生成失败: {e}")
        return ""


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
