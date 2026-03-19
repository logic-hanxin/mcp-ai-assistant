"""
Browser Skill - 浏览器自动化

使用 Playwright 实现浏览器自动化：
1. 网页内容获取 - 像真人一样浏览网页
2. 登录网站获取私有数据
3. 自动填写表单
4. 爬取无API网站

依赖安装: pip install playwright && playwright install chromium
"""

import os
import json
from pathlib import Path

from assistant.skills.base import BaseSkill, ToolDefinition, register


class BrowserSkill(BaseSkill):
    """浏览器自动化技能"""

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return "浏览器自动化：网页浏览、登录、填表、爬取无API网站"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="browse_page",
                description="打开网页并获取页面内容。类似于手动打开浏览器访问网页，适合爬取没有API的网页内容。",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "目标网页URL",
                        },
                        "wait_for": {
                            "type": "string",
                            "description": "等待元素加载的选择器（可选），如 '.content' 或 '#main'",
                            "default": "",
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
                name="login_and_get",
                description="登录网站并获取私有数据。需要提供登录URL、用户名、密码，AI会自动填写表单并登录。",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "登录页面URL",
                        },
                        "username": {
                            "type": "string",
                            "description": "用户名",
                        },
                        "password": {
                            "type": "string",
                            "description": "密码",
                        },
                        "username_selector": {
                            "type": "string",
                            "description": "用户名输入框的选择器，如 '#username' 或 'input[name=email]'",
                        },
                        "password_selector": {
                            "type": "string",
                            "description": "密码输入框的选择器，如 '#password'",
                        },
                        "submit_selector": {
                            "type": "string",
                            "description": "提交按钮的选择器，如 'button[type=submit]' 或 '.login-btn'",
                        },
                        "after_login_url": {
                            "type": "string",
                            "description": "登录成功后要访问的URL（可选）",
                            "default": "",
                        },
                    },
                    "required": ["url", "username", "password", "username_selector", "password_selector", "submit_selector"],
                },
                handler=self._login_and_get,
            ),
            ToolDefinition(
                name="fill_form",
                description="自动填写网页表单并提交。适用于需要提交数据的场景。",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "表单页面URL",
                        },
                        "form_data": {
                            "type": "string",
                            "description": "表单数据，JSON格式，如 {\"输入框1\": \"值1\", \"输入框2\": \"值2\"}",
                        },
                        "submit_selector": {
                            "type": "string",
                            "description": "提交按钮选择器（可选，不提供则不自动提交）",
                            "default": "",
                        },
                    },
                    "required": ["url", "form_data"],
                },
                handler=self._fill_form,
            ),
            ToolDefinition(
                name="click_element",
                description="点击网页上的元素。用于点击按钮、链接等。",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "页面URL",
                        },
                        "selector": {
                            "type": "string",
                            "description": "要点击的元素选择器，如 '.button' 或 '#submit'",
                        },
                        "wait_after": {
                            "type": "integer",
                            "description": "点击后等待秒数，默认2秒",
                            "default": 2,
                        },
                    },
                    "required": ["url", "selector"],
                },
                handler=self._click_element,
            ),
            ToolDefinition(
                name="screenshot",
                description="截取网页截图。用于查看页面视觉效果。",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "页面URL",
                        },
                        "selector": {
                            "type": "string",
                            "description": "要截取的元素选择器（可选，不提供则截取整个页面）",
                            "default": "",
                        },
                    },
                    "required": ["url"],
                },
                handler=self._screenshot,
            ),
        ]

    def _get_browser_context(self):
        """获取浏览器上下文（复用）"""
        try:
            from playwright.sync_api import sync_playwright
            return sync_playwright().start().chromium.launch(headless=True)
        except ImportError:
            return None
        except Exception as e:
            print(f"[Browser] 启动失败: {e}")
            return None

    def _browse_page(self, url: str, wait_for: str = "", max_text_length: int = 5000) -> str:
        """浏览网页并获取内容"""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until="networkidle")

                if wait_for:
                    try:
                        page.wait_for_selector(wait_for, timeout=5000)
                    except Exception:
                        pass  # 等待失败继续

                # 获取页面文本
                content = page.content()
                text = page.evaluate("""() => {
                    const body = document.body;
                    return body ? body.innerText : '';
                }""")

                # 清理文本
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                text = '\n'.join(lines)

                if len(text) > max_text_length:
                    text = text[:max_text_length] + f"\n... (还有 {len(text) - max_text_length} 字符)"

                browser.close()

                return f"【页面标题】{page.title()}\n\n【页面内容】\n{text}"

        except ImportError:
            return "需要安装 playwright: pip install playwright && playwright install chromium"
        except Exception as e:
            return f"浏览失败: {e}"

    def _login_and_get(
        self,
        url: str,
        username: str,
        password: str,
        username_selector: str,
        password_selector: str,
        submit_selector: str,
        after_login_url: str = "",
    ) -> str:
        """登录网站并获取数据"""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()

                # 访问登录页
                page.goto(url, wait_until="networkidle")

                # 填写用户名
                page.fill(username_selector, username)

                # 填写密码
                page.fill(password_selector, password)

                # 点击登录
                page.click(submit_selector)

                # 等待登录完成
                page.wait_for_load_state("networkidle")

                result = f"【登录成功】已登录到: {page.url}\n"

                # 访问指定页面
                if after_login_url:
                    page.goto(after_login_url, wait_until="networkidle")
                    result += f"【目标页面】{page.url}\n"

                # 获取内容
                text = page.evaluate("""() => document.body.innerText""")
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                result += f"\n【页面内容】\n" + '\n'.join(lines[:100])

                browser.close()
                return result

        except ImportError:
            return "需要安装 playwright: pip install playwright && playwright install chromium"
        except Exception as e:
            return f"登录失败: {e}"

    def _fill_form(self, url: str, form_data: str, submit_selector: str = "") -> str:
        """填写表单"""
        try:
            import json
            data = json.loads(form_data)

            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                page.goto(url, wait_until="networkidle")

                # 填写表单
                for selector, value in data.items:
                    try:
                        page.fill(selector, str(value))
                    except Exception as e:
                        return f"填写字段 {selector} 失败: {e}"

                result = f"【表单填写完成】\n"

                # 提交表单
                if submit_selector:
                    page.click(submit_selector)
                    page.wait_for_load_state("networkidle")
                    result += f"【提交成功】当前页面: {page.url}\n"

                # 获取结果
                text = page.evaluate("""() => document.body.innerText""")
                result += f"\n【页面反馈】\n{text[:1000]}"

                browser.close()
                return result

        except json.JSONDecodeError:
            return "form_data 必须是有效的 JSON 格式"
        except ImportError:
            return "需要安装 playwright: pip install playwright && playwright install chromium"
        except Exception as e:
            return f"填写表单失败: {e}"

    def _click_element(self, url: str, selector: str, wait_after: int = 2) -> str:
        """点击元素"""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                page.goto(url, wait_until="networkidle")
                page.click(selector)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(wait_after * 1000)

                text = page.evaluate("""() => document.body.innerText""")
                result = f"【点击完成】已点击: {selector}\n当前页面: {page.url}\n\n【页面内容】\n{text[:2000]}"

                browser.close()
                return result

        except ImportError:
            return "需要安装 playwright: pip install playwright && playwright install chromium"
        except Exception as e:
            return f"点击失败: {e}"

    def _screenshot(self, url: str, selector: str = "") -> str:
        """截取网页截图"""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_viewport_size({"width": 1280, "height": 800})

                page.goto(url, wait_until="networkidle")

                # 保存截图
                screenshot_path = "/tmp/browser_screenshot.png"
                if selector:
                    element = page.query_selector(selector)
                    if element:
                        element.screenshot(path=screenshot_path)
                    else:
                        return f"未找到元素: {selector}"
                else:
                    page.screenshot(path=screenshot_path, full_page=True)

                browser.close()

                # 返回图片路径（需要外部处理如何发送给用户）
                return f"截图已保存到: {screenshot_path}\n可以在后续步骤中发送给用户"

        except ImportError:
            return "需要安装 playwright: pip install playwright && playwright install chromium"
        except Exception as e:
            return f"截图失败: {e}"


register(BrowserSkill)
