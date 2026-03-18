"""
网站监控后台检查器

每 60 秒检测监控列表中的网站，连续失败达到阈值后通过 QQ 通知。
恢复后也会发送通知。
"""

from __future__ import annotations

import os
import asyncio
import datetime

import httpx

from assistant.agent import db

NAPCAT_API_URL = os.getenv("NAPCAT_API_URL", "http://127.0.0.1:3000")
CHECK_INTERVAL = 60  # 检查间隔(秒)
FAIL_THRESHOLD = 3   # 连续失败几次才报警（避免偶发抖动）


def add_site(url: str, name: str = "", notify_qq: str = "") -> dict:
    """添加一个监控站点"""
    try:
        return db.monitor_add_site(url, name=name or url, notify_qq=notify_qq)
    except Exception as e:
        print(f"[监控] 添加站点失败: {e}")
        return {"url": url, "name": name or url, "notify_qq": notify_qq, "status": "unknown"}


def remove_site(url: str) -> bool:
    """移除一个监控站点"""
    try:
        return db.monitor_remove_site(url)
    except Exception as e:
        print(f"[监控] 移除站点失败: {e}")
        return False


def list_sites() -> list[dict]:
    """列出所有监控站点"""
    try:
        return db.monitor_get_sites()
    except Exception as e:
        print(f"[监控] 查询站点失败: {e}")
        return []


async def site_check_loop():
    """后台循环，定期检查所有监控站点"""
    await asyncio.sleep(15)  # 启动延迟，等服务就绪

    # 如果监控列表为空，添加默认站点
    if not list_sites():
        admin_qq = os.getenv("QQ_ADMIN", "")
        add_site("http://120.48.176.249/login/", name="协会官网", notify_qq=admin_qq)
        print("[监控] 已添加默认监控: 协会官网")

    print(f"[监控] 网站监控已启动，间隔 {CHECK_INTERVAL}s")

    while True:
        try:
            await _check_all_sites()
        except Exception as e:
            print(f"[监控] 检查异常: {e}")
        await asyncio.sleep(CHECK_INTERVAL)


async def _check_all_sites():
    """检查所有监控站点"""
    sites = list_sites()
    if not sites:
        return

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for site in sites:
            url = site["url"]
            old_status = site.get("status", "unknown")

            try:
                resp = await client.get(url)
                status_code = resp.status_code
                is_ok = 200 <= status_code < 400
                last_error = ""
            except Exception as e:
                status_code = 0
                is_ok = False
                last_error = str(e)[:200]

            update_fields = {
                "last_check": now,
                "last_status_code": status_code,
            }
            if last_error:
                update_fields["last_error"] = last_error

            if is_ok:
                # 网站正常
                if old_status == "down":
                    # 从故障恢复
                    down_since = site.get("down_since", "")
                    duration = f"（故障持续自 {down_since}）" if down_since else ""
                    await _notify(
                        site,
                        f"[监控恢复] ✅ {site.get('name', url)} 已恢复正常\n"
                        f"地址: {url}\n"
                        f"状态码: {status_code}\n"
                        f"恢复时间: {now}{duration}"
                    )
                update_fields["status"] = "up"
                update_fields["fail_count"] = 0
                update_fields["last_error"] = ""
                update_fields["down_since"] = None
            else:
                # 网站异常
                fail_count = site.get("fail_count", 0) + 1
                update_fields["fail_count"] = fail_count

                if fail_count == FAIL_THRESHOLD:
                    update_fields["status"] = "down"
                    update_fields["down_since"] = now
                    error_info = f"状态码: {status_code}" if status_code else f"错误: {last_error}"
                    await _notify(
                        site,
                        f"[监控告警] ❌ {site.get('name', url)} 无法访问！\n"
                        f"地址: {url}\n"
                        f"{error_info}\n"
                        f"连续失败: {fail_count} 次\n"
                        f"检测时间: {now}"
                    )
                elif fail_count > FAIL_THRESHOLD and fail_count % 30 == 0:
                    await _notify(
                        site,
                        f"[持续故障] ❌ {site.get('name', url)} 仍然无法访问\n"
                        f"已连续失败 {fail_count} 次\n"
                        f"故障开始: {site.get('down_since', '未知')}"
                    )

            try:
                db.monitor_update_site(url, **update_fields)
            except Exception as e:
                print(f"[监控] 更新站点状态失败: {e}")


async def _notify(site: dict, text: str):
    """通过 QQ 发送通知"""
    notify_qq = site.get("notify_qq", "")
    if not notify_qq:
        notify_qq = os.getenv("QQ_ADMIN", "")
    if not notify_qq:
        print(f"  [监控] 无通知目标: {text}")
        return

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{NAPCAT_API_URL}/send_private_msg", json={
                "user_id": int(notify_qq),
                "message": [{"type": "text", "data": {"text": text}}],
            })
        print(f"  [监控通知] -> QQ:{notify_qq}")
    except Exception as e:
        print(f"  [监控通知失败] {e}")
