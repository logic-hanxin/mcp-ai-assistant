"""
运行时上下文

使用 contextvars 保存单次请求范围内的上下文信息，
避免使用全局环境变量导致并发请求串号。
"""

from __future__ import annotations

from contextvars import ContextVar, Token


_current_user_qq: ContextVar[str] = ContextVar("current_user_qq", default="")


def set_current_user_qq(user_qq: str) -> Token:
    """设置当前请求用户 QQ，返回 token 供后续重置。"""
    return _current_user_qq.set(user_qq or "")


def get_current_user_qq(default: str = "") -> str:
    """获取当前请求用户 QQ。"""
    value = _current_user_qq.get()
    return value or default


def reset_current_user_qq(token: Token):
    """重置当前请求上下文。"""
    _current_user_qq.reset(token)
