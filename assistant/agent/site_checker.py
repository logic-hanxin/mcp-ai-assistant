"""
网站监控后台检查器

每 60 秒检测监控列表中的网站，连续失败达到阈值后通过 QQ 通知。
恢复后也会发送通知。
"""

from __future__ import annotations

import os
import json
import asyncio
import datetime
from pathlib import Path

import httpx

NAPCAT_API_URL = os.getenv("NAPCAT_API_URL", "http://127.0.0.1:3000")
CHECK_INTERVAL = 60  # 检查间隔(秒)
FAIL_THRESHOLD = 3   # 连续失败几次才报警（避免偶发抖动）

MONITOR_DIR = Path.home() / ".ai_assistant" / "monitor"
MONITOR_FILE = MONITOR_DIR / "sites.json"


def _load_sites() -> list[dict]:
    if MONITOR_FILE.exists():
        try:
            return json.loads(MONITOR_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_sites(data: list[dict]):
    MONITOR_DIR.mkdir(parents=True, exist_ok=True)
    MONITOR_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_site(url: str, name: str = "", notify_qq: str = "") -> dict:
    """添加一个监控站点"""
    sites = _load_sites()
    # 检查是否已存在
    for s in sites:
        if s["url"] == url:
            return s
    site = {
        "url": url,
        "name": name or url,
        "notify_qq": notify_qq,
        "status": "unknown",       # unknown / up / down
        "fail_count": 0,
        "last_check": "",
        "last_status_code": 0,
        "last_error": "",
        "down_since": "",
    }
    sites.append(site)
    _save_sites(sites)
    return site


def remove_site(url: str) -> bool:
    """移除一个监控站点"""
    sites = _load_sites()
    new_sites = [s for s in sites if s["url"] != url]
    if len(new_sites) < len(sites):
        _save_sites(new_sites)
        return True
    return False


def list_sites() -> list[dict]:
    """列出所有监控站点"""
    return _load_sites()


async def site_check_loop():
    """后台循环，定期检查所有监控站点"""
    await asyncio.sleep(15)  # 启动延迟，等服务就绪

    # 如果监控列表为空，添加默认站点
    if not _load_sites():
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
    sites = _load_sites()
    if not sites:
        return

    changed = False
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for site in sites:
            url = site["url"]
            old_status = site["status"]

            try:
                resp = await client.get(url)
                status_code = resp.status_code
                is_ok = 200 <= status_code < 400
            except Exception as e:
                status_code = 0
                is_ok = False
                site["last_error"] = str(e)[:200]

            site["last_check"] = now
            site["last_status_code"] = status_code

            if is_ok:
                # 网站正常
                if old_status == "down":
                    # 从故障恢复
                    duration = ""
                    if site.get("down_since"):
                        duration = f"（故障持续自 {site['down_since']}）"
                    await _notify(
                        site,
                        f"[监控恢复] ✅ {site['name']} 已恢复正常\n"
                        f"地址: {url}\n"
                        f"状态码: {status_code}\n"
                        f"恢复时间: {now}{duration}"
                    )
                site["status"] = "up"
                site["fail_count"] = 0
                site["last_error"] = ""
                site["down_since"] = ""
                changed = True
            else:
                # 网站异常
                site["fail_count"] = site.get("fail_count", 0) + 1

                if site["fail_count"] == FAIL_THRESHOLD:
                    # 达到报警阈值，首次报警
                    site["status"] = "down"
                    site["down_since"] = now
                    error_info = f"状态码: {status_code}" if status_code else f"错误: {site['last_error']}"
                    await _notify(
                        site,
                        f"[监控告警] ❌ {site['name']} 无法访问！\n"
                        f"地址: {url}\n"
                        f"{error_info}\n"
                        f"连续失败: {site['fail_count']} 次\n"
                        f"检测时间: {now}"
                    )
                elif site["fail_count"] > FAIL_THRESHOLD and site["fail_count"] % 30 == 0:
                    # 持续故障，每 30 次检查（约30分钟）提醒一次
                    await _notify(
                        site,
                        f"[持续故障] ❌ {site['name']} 仍然无法访问\n"
                        f"已连续失败 {site['fail_count']} 次\n"
                        f"故障开始: {site.get('down_since', '未知')}"
                    )

                changed = True

    if changed:
        _save_sites(sites)


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
