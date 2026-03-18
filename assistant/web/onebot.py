"""
NapCat / OneBot 11 协议对接

NapCat 使用 OneBot 11 (原 CQHTTP) 协议，对接方式:

1. NapCat 配置 HTTP POST 上报:
   - 将接收到的 QQ 消息 POST 到本服务的 /onebot 端点

2. 本服务处理消息后，调用 NapCat 的 HTTP API 发送回复:
   - 私聊: POST /send_private_msg
   - 群聊: POST /send_group_msg

NapCat 配置示例 (config/onebot11_<QQ号>.json):
{
    "httpPostUrls": ["http://127.0.0.1:8000/onebot"],
    "httpPort": 3000
}
"""

from __future__ import annotations

import os
import json
import httpx
from openai import OpenAI
from fastapi import Request

from assistant.web.api import app, get_agent
from assistant.agent.contacts_db import (
    record_user_interaction, record_group_interaction, get_user_display_name,
)

# NapCat HTTP API 地址 (NapCat 监听的端口)
NAPCAT_API_URL = os.getenv("NAPCAT_API_URL", "http://127.0.0.1:3000")

# 可选: 只响应特定群聊 (为空则响应所有)
# 格式: 逗号分隔的群号, 如 "123456,789012"
ALLOWED_GROUPS = os.getenv("QQ_ALLOWED_GROUPS", "")

# 群聊中是否需要@才回复 (小彩云模式下建议设为 false)
GROUP_AT_ONLY = os.getenv("QQ_GROUP_AT_ONLY", "true").lower() == "true"

# 管理员QQ号 (可选, 逗号分隔, 拥有额外命令权限)
ADMIN_QQ = os.getenv("QQ_ADMIN", "")


def _is_allowed_group(group_id: int) -> bool:
    if not ALLOWED_GROUPS:
        return True
    allowed = [g.strip() for g in ALLOWED_GROUPS.split(",") if g.strip()]
    return str(group_id) in allowed


def _is_admin(user_id: int) -> bool:
    if not ADMIN_QQ:
        return False
    admins = [a.strip() for a in ADMIN_QQ.split(",") if a.strip()]
    return str(user_id) in admins


async def _fetch_qq_nickname(user_id: int) -> str:
    """通过 NapCat API 获取 QQ 用户昵称"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{NAPCAT_API_URL}/get_stranger_info",
                json={"user_id": user_id},
            )
            data = resp.json()
            if data.get("status") == "ok" or data.get("retcode") == 0:
                return data.get("data", {}).get("nickname", "")
    except Exception:
        pass
    return ""


async def _fetch_group_name(group_id: int) -> str:
    """通过 NapCat API 获取群名称"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{NAPCAT_API_URL}/get_group_info",
                json={"group_id": group_id},
            )
            data = resp.json()
            if data.get("status") == "ok" or data.get("retcode") == 0:
                return data.get("data", {}).get("group_name", "")
    except Exception:
        pass
    return ""


async def _send_private_msg(user_id: int, text: str):
    """发送私聊消息"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(f"{NAPCAT_API_URL}/send_private_msg", json={
                "user_id": user_id,
                "message": [{"type": "text", "data": {"text": text}}],
            })
    except Exception as e:
        print(f"[发送私聊消息失败] user={user_id}: {e}")


async def _send_group_msg(group_id: int, text: str, at_user: int | None = None):
    """发送群聊消息"""
    message = []
    if at_user:
        message.append({"type": "at", "data": {"qq": str(at_user)}})
        message.append({"type": "text", "data": {"text": " "}})
    message.append({"type": "text", "data": {"text": text}})

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(f"{NAPCAT_API_URL}/send_group_msg", json={
                "group_id": group_id,
                "message": message,
            })
    except Exception as e:
        print(f"[发送群消息失败] group={group_id}: {e}")


def _extract_text(message) -> str:
    """从 OneBot 消息段中提取纯文本"""
    if isinstance(message, str):
        return message.strip()
    if isinstance(message, list):
        parts = []
        for seg in message:
            if seg.get("type") == "text":
                parts.append(seg.get("data", {}).get("text", ""))
        return "".join(parts).strip()
    return ""


def _extract_location(message) -> dict:
    """
    从 OneBot 消息段中提取位置信息。
    QQ 位置分享的消息段格式:
      {"type": "location", "data": {"lat": "39.90", "lon": "116.40", "title": "天安门", "content": "北京市..."}}
    也可能是 JSON 类型:
      {"type": "json", "data": {"data": "..."}}  (包含 location 信息)
    返回 {"lat": str, "lon": str, "title": str, "content": str} 或空 dict
    """
    if not isinstance(message, list):
        return {}
    for seg in message:
        if seg.get("type") == "location":
            data = seg.get("data", {})
            return {
                "lat": str(data.get("lat", "")),
                "lon": str(data.get("lon", "")),
                "title": data.get("title", ""),
                "content": data.get("content", ""),
            }
    return {}


def _is_at_me(message, self_id: int) -> bool:
    """检查消息中是否 @了机器人"""
    if isinstance(message, list):
        for seg in message:
            if seg.get("type") == "at" and str(seg.get("data", {}).get("qq")) == str(self_id):
                return True
    return False


# ============================================================
# 群聊智能回复决策
# ============================================================

# 决策用的轻量 LLM 客户端 (延迟初始化)
_decision_client: OpenAI | None = None


def _get_decision_client() -> OpenAI:
    """获取决策用的 LLM 客户端"""
    global _decision_client
    if _decision_client is None:
        from assistant.config import load_config
        cfg = load_config()
        _decision_client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
    return _decision_client


async def _should_reply_in_group(text: str, sender_name: str, recent_context: str,
                                  is_at_me: bool) -> bool:
    """
    让 LLM 判断小彩云是否应该回复这条群消息。
    被 @ 时必定回复；否则由 LLM 根据消息内容和上下文判断。
    """
    # 被 @ 了一定回复
    if is_at_me:
        return True

    # 明确提到小彩云的名字
    if "小彩云" in text or "彩云" in text:
        return True

    prompt = f"""你是QQ群里的群友「小彩云」。请判断你是否应该回复下面这条群消息。

判断标准（满足任一即回复）:
- 有人在问问题、求助、询问信息
- 在讨论你能帮上忙的话题（天气、活动、协会事务等）
- 有人在和你打招呼或找你聊天
- 话题有趣，你作为群友自然会想插嘴
- 涉及彩云协会相关的事务

不回复的情况:
- 纯粹的闲聊/灌水/表情包大战，你没什么可补充的
- 两个人的私密对话，你插嘴不合适
- 单纯的"嗯""哦""好的"等无实质内容
- 分享链接但没有讨论

最近的群聊上下文:
{recent_context}

当前消息:
{sender_name}: {text}

请只回复一个字: "是" 或 "否"。"""

    try:
        client = _get_decision_client()
        response = client.chat.completions.create(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0.3,
        )
        answer = (response.choices[0].message.content or "").strip()
        should = answer.startswith("是")
        print(f"  [决策] {sender_name}: {text[:30]}... → {'回复' if should else '静默'}")
        return should
    except Exception as e:
        print(f"  [决策异常] {e}，默认不回复")
        return False


@app.post("/onebot")
async def onebot_event(request: Request):
    """
    接收 NapCat HTTP POST 上报的事件

    OneBot 11 事件格式:
    - post_type: message / notice / request / meta_event
    - message_type: private / group
    """
    event = await request.json()
    post_type = event.get("post_type")

    # 只处理消息事件
    if post_type != "message":
        return {"status": "ignored"}

    message_type = event.get("message_type")  # private / group
    user_id = event.get("user_id")            # 发送者 QQ 号
    raw_message = event.get("message", "")     # 消息内容 (CQ码 或 消息段数组)
    self_id = event.get("self_id")            # 机器人 QQ 号

    text = _extract_text(raw_message)

    # 检查是否是位置分享消息
    location = _extract_location(raw_message)
    if location and location.get("lat"):
        loc_parts = []
        if location.get("title"):
            loc_parts.append(location["title"])
        if location.get("content"):
            loc_parts.append(location["content"])
        loc_desc = "，".join(loc_parts) if loc_parts else f"经纬度({location['lat']}, {location['lon']})"
        text = f"[用户发送了位置] {loc_desc} (坐标: {location['lat']}, {location['lon']})"

    if not text:
        return {"status": "empty"}

    # ---- 私聊 ----
    if message_type == "private":
        # 自动记录用户信息
        sender = event.get("sender", {})
        nickname = sender.get("nickname", "")
        if not nickname:
            nickname = await _fetch_qq_nickname(user_id)
        record_user_interaction(str(user_id), nickname)

        reply = await _handle_message(
            session_id=str(user_id),
            text=text,
            user_qq=str(user_id),
            group_id=None,
        )
        await _send_private_msg(user_id, reply)
        return {"status": "ok"}

    # ---- 群聊 ----
    if message_type == "group":
        group_id = event.get("group_id")

        # 群白名单检查
        if not _is_allowed_group(group_id):
            return {"status": "ignored"}

        # 获取发送者昵称
        sender = event.get("sender", {})
        nickname = sender.get("card") or sender.get("nickname") or ""
        if not nickname:
            nickname = await _fetch_qq_nickname(user_id)
        record_user_interaction(str(user_id), nickname)

        group_name = await _fetch_group_name(group_id)
        record_group_interaction(str(group_id), group_name)

        # 群聊使用整群共享的 session_id，小彩云看到所有人的消息
        session_id = f"group_{group_id}"
        at_me = _is_at_me(raw_message, self_id)

        # 将消息以 "昵称: 内容" 的格式存入群上下文，让小彩云知道谁在说话
        display_name = get_user_display_name(str(user_id)) or nickname or str(user_id)
        group_text = f"{display_name}: {text}"

        # 先把消息记录到群上下文（无论是否回复）
        agent = await get_agent(session_id)
        agent.session_context = {
            "user_qq": str(user_id),
            "group_id": str(group_id),
            "user_display_name": display_name,
        }

        # 智能决策: 判断是否需要回复
        if GROUP_AT_ONLY and not at_me:
            # AT_ONLY 模式: 必须@才回复（传统模式）
            # 但仍然把消息记录到上下文中
            agent.memory.add_message("user", group_text)
            return {"status": "ignored"}

        if not GROUP_AT_ONLY:
            # 自由模式: LLM 自主决策是否回复
            # 先获取最近的群聊上下文供决策参考
            recent_msgs = agent.memory.get_messages()[-8:]
            recent_context = "\n".join(
                f"{m.get('content', '')[:80]}" for m in recent_msgs
                if m.get("role") == "user"
            )

            should_reply = await _should_reply_in_group(
                text=text,
                sender_name=display_name,
                recent_context=recent_context,
                is_at_me=at_me,
            )

            if not should_reply:
                # 不回复，但把消息记到上下文（小彩云"看到了"但选择不说话）
                agent.memory.add_message("user", group_text)
                return {"status": "silent"}

        # 需要回复: 走完整的 Agent 对话流程
        reply = await _handle_message(
            session_id=session_id,
            text=group_text,
            user_qq=str(user_id),
            group_id=str(group_id),
        )

        # 群聊回复不 @ 用户，像普通群友一样说话
        await _send_group_msg(group_id, reply)
        return {"status": "ok"}

    return {"status": "ignored"}


async def _handle_message(session_id: str, text: str, user_qq: str = "", group_id: str = "") -> str:
    """处理消息: 命令或对话"""
    # 命令
    if text == "清空记录" or text.endswith(": 清空记录"):
        agent = await get_agent(session_id)
        agent.clear_history()
        return "对话记录已清空！"

    if text == "帮助" or text.endswith(": 帮助"):
        return (
            "我是小彩云，彩云协会的AI助手～有什么可以帮你的：\n"
            "- 直接在群里聊天，我会自己判断要不要回复\n"
            "- 查天气、翻译、搜索\n"
            "- 记笔记、查笔记\n"
            "- 做数学计算\n"
            "- 设定提醒（如: 30分钟后提醒我开会）\n"
            "- 查快递物流\n"
            "- 搜歌、看热歌榜\n"
            "- 看热点新闻\n"
            "- 查询协会数据库\n"
            "- 发送「清空记录」重置对话"
        )

    # 正常对话
    try:
        agent = await get_agent(session_id)
        # 注入 QQ 上下文，让 Agent 知道当前用户是谁
        display_name = get_user_display_name(user_qq) if user_qq else ""
        agent.session_context = {
            "user_qq": user_qq,
            "group_id": group_id,
            "user_display_name": display_name,
        }
        reply = await agent.chat(text)
        return reply
    except Exception as e:
        return f"出错了: {e}"
