"""
Vision Skill - 图片识别能力

支持:
1. OCR 文字识别 - 从图片中提取文字
2. 图片理解 - 使用 AI 分析图片内容
3. 二维码识别
"""

import os
import base64
import json
import requests
from pathlib import Path

from assistant.skills.base import BaseSkill, ToolDefinition, register


class VisionSkill(BaseSkill):
    """图片识别技能"""

    @property
    def name(self) -> str:
        return "vision"

    @property
    def description(self) -> str:
        return "图片识别：OCR文字识别、AI图片理解、二维码识别"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="ocr_image",
                description="从图片中识别提取文字（OCR）。适用于截图、文档照片、发票等。",
                parameters={
                    "type": "object",
                    "properties": {
                        "image_url": {
                            "type": "string",
                            "description": "图片URL或本地文件路径",
                        },
                    },
                    "required": ["image_url"],
                },
                handler=self._ocr_image,
            ),
            ToolDefinition(
                name="understand_image",
                description="使用AI理解图片内容。描述图片中的场景、人物、物品等。",
                parameters={
                    "type": "object",
                    "properties": {
                        "image_url": {
                            "type": "string",
                            "description": "图片URL或本地文件路径",
                        },
                        "question": {
                            "type": "string",
                            "description": "想了解图片的什么问题？默认描述图片内容",
                            "default": "描述这张图片的内容",
                        },
                    },
                    "required": ["image_url"],
                },
                handler=self._understand_image,
            ),
            ToolDefinition(
                name="scan_qrcode",
                description="识别图片中的二维码或条形码，获取其中包含的信息。",
                parameters={
                    "type": "object",
                    "properties": {
                        "image_url": {
                            "type": "string",
                            "description": "图片URL或本地文件路径",
                        },
                    },
                    "required": ["image_url"],
                },
                handler=self._scan_qrcode,
            ),
        ]

    def _ocr_image(self, image_url: str) -> str:
        """OCR 文字识别"""
        try:
            # 优先使用百度 OCR API（如果配置了）
            baidu_token = os.getenv("BAIDU_OCR_TOKEN")
            if baidu_token:
                return self._baidu_ocr(image_url, baidu_token)

            # 使用免费的 OCR.space API
            return self._ocr_space(image_url)
        except Exception as e:
            return f"OCR识别失败: {e}"

    def _ocr_space(self, image_url: str) -> str:
        """使用 OCR.space 免费 API"""
        api_url = "https://api.ocr.space/parse/image"

        # 判断是 URL 还是本地文件
        if image_url.startswith("http"):
            payload = {"url": image_url, "language": "chs"}
            headers = {"apikey": os.getenv("OCR_SPACE_KEY", "helloworld")}
        else:
            # 本地文件需要上传
            with open(image_url, "rb") as f:
                files = {"file": f}
                data = {"language": "chs"}
                headers = {"apikey": os.getenv("OCR_SPACE_KEY", "helloworld")}
                response = requests.post(api_url, data=data, files=files, headers=headers)
                result = response.json()
                if result.get("ParsedResults"):
                    return result["ParsedResults"][0]["ParsedText"]
                return "未能识别出文字"

        response = requests.post(api_url, data=payload, headers=headers)
        result = response.json()

        if result.get("ParsedResults"):
            texts = [r["ParsedText"] for r in result["ParsedResults"]]
            return "\n".join(texts)
        elif result.get("ErrorMessage"):
            return f"OCR失败: {result['ErrorMessage']}"
        return "未能识别出文字"

    def _baidu_ocr(self, image_url: str, token: str) -> str:
        """百度 OCR API"""
        api_url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token={token}"

        # 获取图片数据
        if image_url.startswith("http"):
            response = requests.get(image_url)
            image_data = response.content
        else:
            with open(image_url, "rb") as f:
                image_data = f.read()

        # base64 编码
        import base64
        img_base64 = base64.b64encode(image_data).decode()

        payload = {"image": img_base64}
        response = requests.post(api_url, data=payload)
        result = response.json()

        if result.get("words_result"):
            texts = [w["words"] for w in result["words_result"]]
            return "\n".join(texts)
        return "未能识别出文字"

    def _understand_image(self, image_url: str, question: str = "描述这张图片的内容") -> str:
        """使用 AI 理解图片"""
        try:
            # 使用 OpenAI Vision API
            from openai import OpenAI

            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

            if not api_key:
                return "未配置 OpenAI API Key，无法使用图片理解功能"

            client = OpenAI(api_key=api_key, base_url=base_url)

            # 构建消息
            content = [{"type": "text", "text": question}]

            # 判断图片来源
            if image_url.startswith("http"):
                content.append({"type": "image_url", "image_url": {"url": image_url}})
            else:
                # 本地文件需要转为 base64
                with open(image_url, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode()
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}
                })

            response = client.chat.completions.create(
                model=os.getenv("VISION_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": content}],
                max_tokens=1000,
            )

            return response.choices[0].message.content

        except ImportError:
            return "需要安装 openai 库才能使用图片理解功能"
        except Exception as e:
            return f"图片理解失败: {e}"

    def _scan_qrcode(self, image_url: str) -> str:
        """识别二维码"""
        try:
            import qrcode
            from PIL import Image

            # 下载或读取图片
            if image_url.startswith("http"):
                response = requests.get(image_url)
                img = Image.open(response.raw)
            else:
                img = Image.open(image_url)

            # 使用 pillow-qrcode 解析
            qr = qrcode.QRCode()
            qr.decode(img)

            if qr.data:
                return f"识别结果: {qr.data}"
            return "未检测到二维码或条形码"

        except ImportError:
            # 备选方案：使用 opencv
            try:
                import cv2
                return self._scan_qrcode_opencv(image_url)
            except ImportError:
                return "需要安装 qrcode 或 opencv 库才能识别二维码"
        except Exception as e:
            return f"二维码识别失败: {e}"

    def _scan_qrcode_opencv(self, image_url: str) -> str:
        """使用 OpenCV 识别二维码"""
        import cv2

        if image_url.startswith("http"):
            response = requests.get(image_url)
            nparr = np.frombuffer(response.content, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        else:
            img = cv2.imread(image_url)

        detector = cv2.QRCodeDetector()
        result, points, straight_qrcode = detector.detectAndDecode(img)

        if result:
            return f"识别结果: {result}"
        return "未检测到二维码"


register(VisionSkill)
