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

import os
import httpx
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

# 群聊中是否需要@才回复
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

        # 是否需要 @
        if GROUP_AT_ONLY and not _is_at_me(raw_message, self_id):
            return {"status": "ignored"}

        # 自动记录用户和群信息
        sender = event.get("sender", {})
        nickname = sender.get("nickname") or sender.get("card", "")
        if not nickname:
            nickname = await _fetch_qq_nickname(user_id)
        record_user_interaction(str(user_id), nickname)

        group_name = await _fetch_group_name(group_id)
        record_group_interaction(str(group_id), group_name)

        # 群聊用 "group_群号_QQ号" 作为会话ID, 每个人独立上下文
        session_id = f"group_{group_id}_{user_id}"
        reply = await _handle_message(
            session_id=session_id,
            text=text,
            user_qq=str(user_id),
            group_id=str(group_id),
        )
        await _send_group_msg(group_id, reply, at_user=user_id)
        return {"status": "ok"}

    return {"status": "ignored"}


async def _handle_message(session_id: str, text: str, user_qq: str = "", group_id: str = "") -> str:
    """处理消息: 命令或对话"""
    # 命令
    if text == "清空记录":
        agent = await get_agent(session_id)
        agent.clear_history()
        return "对话记录已清空！"

    if text == "帮助":
        return (
            "我是美萌robot，你可以:\n"
            "- 直接聊天对话\n"
            "- 查天气、翻译、搜索\n"
            "- 记笔记、查笔记\n"
            "- 做数学计算\n"
            "- 设定提醒（如: 30分钟后提醒我开会）\n"
            "- 查快递物流\n"
            "- 搜歌、看热歌榜\n"
            "- 看热点新闻\n"
            "- 发送位置可定位、查IP/手机号归属地\n"
            "- 给指定QQ号发消息\n"
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
