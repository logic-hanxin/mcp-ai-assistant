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


async def _send_private_msg(user_id: int, text: str):
    """发送私聊消息"""
    async with httpx.AsyncClient() as client:
        await client.post(f"{NAPCAT_API_URL}/send_private_msg", json={
            "user_id": user_id,
            "message": [{"type": "text", "data": {"text": text}}],
        })


async def _send_group_msg(group_id: int, text: str, at_user: int | None = None):
    """发送群聊消息"""
    message = []
    if at_user:
        message.append({"type": "at", "data": {"qq": str(at_user)}})
        message.append({"type": "text", "data": {"text": " "}})
    message.append({"type": "text", "data": {"text": text}})

    async with httpx.AsyncClient() as client:
        await client.post(f"{NAPCAT_API_URL}/send_group_msg", json={
            "group_id": group_id,
            "message": message,
        })


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

    if not text:
        return {"status": "empty"}

    # ---- 私聊 ----
    if message_type == "private":
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


async def _handle_message(session_id: str, text: str, user_qq: str = "", group_id: str | None = None) -> str:
    """处理消息: 命令或对话"""
    # 命令
    if text == "清空记录":
        agent = await get_agent(session_id)
        agent.clear_history()
        return "对话记录已清空！"

    if text == "帮助":
        return (
            "我是AI助手，你可以:\n"
            "- 直接聊天对话\n"
            "- 让我查时间、天气\n"
            "- 让我记笔记、查笔记\n"
            "- 让我做数学计算\n"
            "- 设定提醒（如: 30分钟后提醒我开会）\n"
            "- 让我给指定QQ号发消息\n"
            "- 发送「清空记录」重置对话"
        )

    # 正常对话
    try:
        agent = await get_agent(session_id)
        # 注入 QQ 上下文，让 Agent 知道当前用户是谁
        agent.session_context = {
            "user_qq": user_qq,
            "group_id": group_id,
        }
        reply = await agent.chat(text)
        return reply
    except Exception as e:
        return f"出错了: {e}"
