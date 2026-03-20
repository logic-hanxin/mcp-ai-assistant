"""王者荣耀战力查询 Skill - 查询英雄最低战力标准"""

from typing import Optional

import httpx
from assistant.skills.base import BaseSkill, ToolDefinition, register

API_BASE = "https://www.sapi.run/hero"

# 平台类型映射
PLATFORM_TYPES = {
    "aqq": "安卓QQ",
    "awx": "安卓微信",
    "iqq": "苹果QQ",
    "iwx": "苹果微信",
}


def _get_hero_list() -> Optional[list]:
    """获取英雄列表"""
    try:
        resp = httpx.get(
            f"{API_BASE}/getHeroList.php",
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 200:
                return data.get("data", [])
    except Exception:
        pass
    return None


def _query_hero_power(hero: str, platform_type: str) -> Optional[dict]:
    """查询指定英雄在指定平台的战力"""
    try:
        resp = httpx.get(
            f"{API_BASE}/select.php",
            params={"hero": hero, "type": platform_type},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 200:
                return data.get("data")
    except Exception:
        pass
    return None


class WzrySkill(BaseSkill):
    name = "wzry"
    description = "王者荣耀英雄战力查询"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="query_hero_power",
                description=(
                    "查询王者荣耀英雄的最低上榜战力标准，包含省标、市标、县标和国标。"
                    "支持查询4个平台：安卓QQ、安卓微信、苹果QQ、苹果微信。"
                    "用户可以指定英雄名称和平台，如不指定平台则查询全部4个平台。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "hero": {
                            "type": "string",
                            "description": "英雄名称，如 赵云、李白、貂蝉、孙尚香",
                        },
                        "platform": {
                            "type": "string",
                            "description": "平台类型：aqq=安卓QQ, awx=安卓微信, iqq=苹果QQ, iwx=苹果微信。不填则查询全部平台",
                            "enum": ["aqq", "awx", "iqq", "iwx"],
                        },
                    },
                    "required": ["hero"],
                },
                handler=self._query_hero_power,
                metadata={
                    "category": "read",
                    "required_all": ["hero"],
                },
                keywords=["王者战力", "英雄战力", "国标省标", "查英雄分数"],
                intents=["query_hero_power"],
            ),
            ToolDefinition(
                name="search_hero",
                description="搜索王者荣耀英雄列表，可以查看所有英雄或按关键词筛选。",
                parameters={
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "搜索关键词（英雄名称），留空则返回全部英雄",
                        },
                    },
                    "required": [],
                },
                handler=self._search_hero,
                metadata={
                    "category": "read",
                },
                keywords=["英雄列表", "搜索英雄", "查王者英雄"],
                intents=["search_hero"],
            ),
        ]

    def _query_hero_power(self, hero: str, platform: str = "") -> str:
        if not hero.strip():
            return "请输入英雄名称，如：赵云、李白、貂蝉"

        types_to_query = [platform] if platform in PLATFORM_TYPES else list(PLATFORM_TYPES.keys())

        results = []
        for pt in types_to_query:
            data = _query_hero_power(hero, pt)
            if data:
                results.append(data)

        if not results:
            return f"未找到英雄「{hero}」的战力数据，请检查英雄名称是否正确（需要输入完整名称）。"

        first = results[0]
        lines = [
            f"🎮 {first.get('alias', hero)} 战力查询",
            "",
        ]

        for data in results:
            lines.append(f"【{data.get('platform', '未知')}】")
            lines.append(f"  🥇 省标 ({data.get('province', '?')}): {data.get('provincePower', '?')} 分")
            lines.append(f"  🥈 市标 ({data.get('city', '?')}): {data.get('cityPower', '?')} 分")
            lines.append(f"  🥉 县标 ({data.get('area', '?')}): {data.get('areaPower', '?')} 分")
            lines.append(f"  🏆 国标: {data.get('guobiao', '?')} 分")
            lines.append("")

        update_time = results[-1].get("updatetime", "")
        if update_time:
            lines.append(f"更新时间: {update_time}")

        return "\n".join(lines)

    def _search_hero(self, keyword: str = "") -> str:
        hero_list = _get_hero_list()
        if not hero_list:
            return "获取英雄列表失败，请稍后再试。"

        type_map = {1: "战士", 2: "法师", 3: "坦克", 4: "刺客", 5: "射手", 6: "辅助"}

        if keyword and keyword.strip():
            hero_list = [h for h in hero_list if keyword in h.get("cname", "")]

        if not hero_list:
            return f"没有找到包含「{keyword}」的英雄。"

        lines = [f"王者荣耀英雄列表 (共 {len(hero_list)} 位)"]
        lines.append("")
        for h in hero_list:
            name = h.get("cname", "?")
            title = h.get("title", "")
            h_type = type_map.get(h.get("hero_type", 0), "未知")
            lines.append(f"  {name} - {title} [{h_type}]")

        return "\n".join(lines)


register(WzrySkill)
