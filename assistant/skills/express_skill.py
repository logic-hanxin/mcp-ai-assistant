"""快递查询 Skill - 基于快递100移动版接口"""

import httpx
from assistant.skills.base import BaseSkill, ToolDefinition, register

KUAIDI100_URL = "https://m.kuaidi100.com/query"

# 常见快递公司代码映射
EXPRESS_COMPANIES = {
    "顺丰": "shunfeng", "sf": "shunfeng",
    "中通": "zhongtong", "zto": "zhongtong",
    "圆通": "yuantong", "yto": "yuantong",
    "韵达": "yunda", "yd": "yunda",
    "申通": "shentong", "sto": "shentong",
    "极兔": "jtexpress", "jt": "jtexpress",
    "邮政": "youzhengguonei", "ems": "ems",
    "京东": "jd", "jdl": "jd",
    "百世": "huitongkuaidi", "bs": "huitongkuaidi",
    "德邦": "debangkuaidi", "db": "debangkuaidi",
    "天天": "tiantian",
    "丰网": "fengwang",
    "菜鸟": "cainiao",
}

# 快递单号前缀自动识别
PREFIX_RULES = [
    ("SF", "shunfeng"),
    ("JT", "jtexpress"),
    ("YT", "yuantong"),
    ("ZT", "zhongtong"),
    ("YD", "yunda"),
    ("46", "yunda"),
    ("JD", "jd"),
    ("DP", "debangkuaidi"),
]


def _guess_company(tracking_no: str) -> str:
    """根据单号前缀猜测快递公司"""
    upper = tracking_no.upper()
    for prefix, code in PREFIX_RULES:
        if upper.startswith(prefix):
            return code
    return ""


def _normalize_company(company: str) -> str:
    """将用户输入的快递公司名转为代码"""
    company = company.strip().lower()
    return EXPRESS_COMPANIES.get(company, company)


class ExpressSkill(BaseSkill):
    name = "express"
    description = "快递物流查询，支持顺丰、中通、圆通、韵达等主流快递"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="query_express",
                description=(
                    "查询快递物流信息。支持顺丰、中通、圆通、韵达、申通、极兔、"
                    "邮政、京东、德邦等主流快递。可自动根据单号前缀识别快递公司，"
                    "也可手动指定。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "tracking_no": {
                            "type": "string",
                            "description": "快递单号",
                        },
                        "company": {
                            "type": "string",
                            "description": (
                                "快递公司名称，如 顺丰、中通、圆通、韵达、申通、极兔、京东、邮政。"
                                "留空则自动根据单号前缀识别。"
                            ),
                            "default": "",
                        },
                    },
                    "required": ["tracking_no"],
                },
                handler=self._query_express,
            ),
        ]

    def _query_express(self, tracking_no: str, company: str = "") -> str:
        tracking_no = tracking_no.strip()
        if not tracking_no:
            return "请提供快递单号。"

        # 确定快递公司
        if company:
            com_code = _normalize_company(company)
        else:
            com_code = _guess_company(tracking_no)

        if not com_code:
            return (
                f"无法自动识别单号 {tracking_no} 的快递公司，请手动指定。\n"
                f"支持: 顺丰、中通、圆通、韵达、申通、极兔、京东、邮政、德邦等"
            )

        try:
            resp = httpx.post(
                KUAIDI100_URL,
                data={"type": com_code, "postid": tracking_no, "temp": "0.5"},
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://m.kuaidi100.com/",
                    "Origin": "https://m.kuaidi100.com",
                },
            )
            data = resp.json()
        except Exception as e:
            return f"查询失败: {e}"

        if data.get("status") != "200" and data.get("status") != 200:
            msg = data.get("message", "未知错误")
            return f"查询失败: {msg}\n(快递公司: {com_code}, 单号: {tracking_no})"

        records = data.get("data", [])
        if not records:
            return f"暂无物流信息。(单号: {tracking_no})"

        # 状态映射
        state_map = {
            "0": "运输中", "1": "揽收", "2": "疑难",
            "3": "已签收", "4": "退签", "5": "派件中", "6": "退回",
        }
        state = state_map.get(str(data.get("state", "")), "未知")
        com_name = data.get("com", com_code)

        lines = [f"快递: {com_name}  单号: {tracking_no}  状态: {state}"]
        lines.append("")
        for item in records[:8]:
            time_str = item.get("time", "")
            context = item.get("context", "")
            lines.append(f"  {time_str}  {context}")

        if len(records) > 8:
            lines.append(f"  ... 还有 {len(records) - 8} 条记录")

        return "\n".join(lines)


register(ExpressSkill)
