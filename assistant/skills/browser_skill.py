"""
Browser Skill - 浏览器自动化

使用 requests + BeautifulSoup 爬取网页：
1. 网页内容获取 - 爬取没有 API 的网页
2. 简单登录（支持 Cookie）

依赖: requests beautifulsoup4 (已安装)
"""

import os
import json
import re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

from assistant.skills.base import BaseSkill, ToolDefinition, register


class BrowserSkill(BaseSkill):
    """浏览器自动化技能"""

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return "浏览器自动化：网页爬取、登录、获取无API网站内容"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="browse_page",
                description="爬取网页内容。类似于手动打开浏览器访问网页，适合爬取没有API的网页内容。",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "目标网页URL",
                        },
                        "max_text_length": {
                            "type": "integer",
                            "description": "最大返回文本长度，默认5000字符",
                            "default": 5000,
                        },
                    },
                    "required": ["url"],
                },
                handler=self._browse_page,
            ),
            ToolDefinition(
                name="browse_with_headers",
                description="带 Headers 爬取网页（可模拟浏览器）。适用于需要特殊请求头的网站。",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "目标网页URL",
                        },
                        "headers": {
                            "type": "string",
                            "description": "自定义请求头，JSON格式，如 {\"User-Agent\": \"Mozilla/5.0\"}",
                            "default": "{}",
                        },
                        "max_text_length": {
                            "type": "integer",
                            "description": "最大返回文本长度，默认5000字符",
                            "default": 5000,
                        },
                    },
                    "required": ["url"],
                },
                handler=self._browse_with_headers,
            ),
            ToolDefinition(
                name="post_form",
                description="POST 提交表单数据。适用于登录或提交数据到服务器。",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "表单提交URL",
                        },
                        "data": {
                            "type": "string",
                            "description": "表单数据，JSON格式，如 {\"username\": \"xxx\", \"password\": \"xxx\"}",
                        },
                    },
                    "required": ["url", "data"],
                },
                handler=self._post_form,
            ),
            ToolDefinition(
                name="get_json",
                description="获取 API 返回的 JSON 数据。",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "API URL",
                        },
                        "headers": {
                            "type": "string",
                            "description": "请求头（可选），JSON格式",
                            "default": "{}",
                        },
                    },
                    "required": ["url"],
                },
                handler=self._get_json,
            ),
        ]

    def _clean_text(self, text: str) -> str:
        """清理文本"""
        # 移除多余空白
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        return '\n'.join(lines)

    def _browse_page(self, url: str, max_text_length: int = 5000) -> str:
        """爬取网页内容"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.encoding = response.apparent_encoding or 'utf-8'

            soup = BeautifulSoup(response.text, 'html.parser')

            # 移除脚本和样式
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()

            # 获取标题
            title = soup.title.string if soup.title else url

            # 获取文本
            text = soup.get_text(separator='\n')
            text = self._clean_text(text)

            if len(text) > max_text_length:
                text = text[:max_text_length] + f"\n... (还有 {len(text) - max_text_length} 字符)"

            return f"【页面标题】{title}\n【URL】{url}\n\n【页面内容】\n{text}"

        except Exception as e:
            return f"爬取失败: {e}"

    def _browse_with_headers(self, url: str, headers: str = "{}", max_text_length: int = 5000) -> str:
        """带 Headers 爬取"""
        try:
            import json
            headers_dict = json.loads(headers) if headers else {}
            if 'User-Agent' not in headers_dict:
                headers_dict['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

            response = requests.get(url, headers=headers_dict, timeout=15)
            response.encoding = response.apparent_encoding or 'utf-8'

            soup = BeautifulSoup(response.text, 'html.parser')
            for tag in soup(['script', 'style']):
                tag.decompose()

            title = soup.title.string if soup.title else url
            text = soup.get_text(separator='\n')
            text = self._clean_text(text)

            if len(text) > max_text_length:
                text = text[:max_text_length] + f"\n... (还有 {len(text) - max_text_length} 字符)"

            return f"【页面标题】{title}\n【URL】{url}\n\n【页面内容】\n{text}"

        except json.JSONDecodeError:
            return "headers 必须是有效的 JSON 格式"
        except Exception as e:
            return f"爬取失败: {e}"

    def _post_form(self, url: str, data: str) -> str:
        """POST 提交表单"""
        try:
            import json
            data_dict = json.loads(data)

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = requests.post(url, data=data_dict, headers=headers, timeout=15)
            response.encoding = response.apparent_encoding or 'utf-8'

            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text(separator='\n')
            text = self._clean_text(text)

            return f"【提交成功】{url}\n【状态码】{response.status_code}\n\n【响应内容】\n{text[:3000]}"

        except json.JSONDecodeError:
            return "data 必须是有效的 JSON 格式"
        except Exception as e:
            return f"提交失败: {e}"

    def _get_json(self, url: str, headers: str = "{}") -> str:
        """获取 JSON 数据"""
        try:
            import json
            headers_dict = json.loads(headers) if headers else {}
            if 'User-Agent' not in headers_dict:
                headers_dict['User-Agent'] = 'Mozilla/5.0'

            response = requests.get(url, headers=headers_dict, timeout=15)
            response.raise_for_status()

            try:
                data = response.json()
                return f"【API 响应】{url}\n\n{json.dumps(data, ensure_ascii=False, indent=2)[:3000]}"
            except json.JSONDecodeError:
                return f"【响应不是 JSON】\n{response.text[:2000]}"

        except json.JSONDecodeError:
            return "headers 必须是有效的 JSON 格式"
        except Exception as e:
            return f"请求失败: {e}"


register(BrowserSkill)
