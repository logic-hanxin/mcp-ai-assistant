"""定位 Skill - IP定位、手机号归属地查询"""

import httpx
from assistant.skills.base import BaseSkill, ToolDefinition, register


class LocationSkill(BaseSkill):
    name = "location"
    description = "IP地理定位、手机号归属地查询"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="ip_location",
                description=(
                    "查询IP地址的地理位置信息，返回国家、省份、城市、运营商、经纬度。"
                    "如果不传IP则查询服务器自身的公网IP位置。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "ip": {
                            "type": "string",
                            "description": "要查询的IP地址，留空则查询当前服务器IP",
                            "default": "",
                        },
                    },
                },
                handler=self._ip_location,
            ),
            ToolDefinition(
                name="phone_area",
                description="查询手机号码的归属地（省份、城市、运营商）。",
                parameters={
                    "type": "object",
                    "properties": {
                        "phone": {
                            "type": "string",
                            "description": "手机号码（11位）",
                        },
                    },
                    "required": ["phone"],
                },
                handler=self._phone_area,
            ),
        ]

    def _ip_location(self, ip: str = "") -> str:
        url = f"http://ip-api.com/json/{ip}?lang=zh-CN" if ip else "http://ip-api.com/json/?lang=zh-CN"
        try:
            resp = httpx.get(url, timeout=10)
            data = resp.json()
        except Exception as e:
            return f"查询失败: {e}"

        if data.get("status") != "success":
            return f"查询失败: {data.get('message', '无效IP')}"

        lines = [
            f"IP: {data.get('query', ip)}",
            f"位置: {data.get('country', '')} {data.get('regionName', '')} {data.get('city', '')}",
            f"运营商: {data.get('isp', '未知')}",
            f"经纬度: {data.get('lat', '?')}, {data.get('lon', '?')}",
        ]
        return "\n".join(lines)

    def _phone_area(self, phone: str) -> str:
        phone = phone.strip()
        if len(phone) != 11 or not phone.isdigit():
            return "请输入正确的11位手机号码。"

        try:
            resp = httpx.get(
                "https://cx.shouji.360.cn/phonearea.php",
                params={"number": phone},
                timeout=10,
            )
            data = resp.json()
        except Exception as e:
            return f"查询失败: {e}"

        if data.get("code") != 0:
            return f"未查到号码 {phone} 的归属地信息。"

        info = data.get("data", {})
        province = info.get("province", "未知")
        city = info.get("city", "")
        sp = info.get("sp", "未知")

        location = f"{province} {city}".strip() if city else province
        return f"手机号: {phone}\n归属地: {location}\n运营商: {sp}"


register(LocationSkill)
