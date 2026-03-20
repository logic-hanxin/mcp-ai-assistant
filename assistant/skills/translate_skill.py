"""翻译 Skill - 基于 MyMemory 免费翻译 API"""

import httpx
from assistant.skills.base import BaseSkill, ToolDefinition, register

MYMEMORY_URL = "https://api.mymemory.translated.net/get"

# 常用语言代码映射
LANG_MAP = {
    "中文": "zh", "英文": "en", "英语": "en", "日文": "ja", "日语": "ja",
    "韩文": "ko", "韩语": "ko", "法文": "fr", "法语": "fr", "德文": "de",
    "德语": "de", "西班牙语": "es", "俄语": "ru", "葡萄牙语": "pt",
    "意大利语": "it", "阿拉伯语": "ar", "泰语": "th", "越南语": "vi",
    "chinese": "zh", "english": "en", "japanese": "ja", "korean": "ko",
    "french": "fr", "german": "de", "spanish": "es", "russian": "ru",
}


def _normalize_lang(lang: str) -> str:
    """将用户输入的语言名称转换为语言代码"""
    lang = lang.strip().lower()
    return LANG_MAP.get(lang, lang)


def _detect_and_translate(text: str, target_lang: str) -> tuple[str, str, str]:
    """翻译文本，返回 (译文, 源语言, 目标语言)"""
    target = _normalize_lang(target_lang)

    # 简单的语言检测：如果全是 ASCII 字符，大概率是英文，目标默认中文
    # 如果包含中文字符，源语言设为中文
    has_cjk = any("\u4e00" <= c <= "\u9fff" for c in text)

    if target == "auto" or not target:
        target = "zh" if not has_cjk else "en"

    source = "zh" if has_cjk else "en"
    # 如果源语言和目标相同，翻转
    if source == target:
        source = "en" if target == "zh" else "zh"

    try:
        resp = httpx.get(
            MYMEMORY_URL,
            params={"q": text, "langpair": f"{source}|{target}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            translated = data.get("responseData", {}).get("translatedText", "")
            if translated:
                return translated, source, target
    except Exception:
        pass

    return "", source, target


class TranslateSkill(BaseSkill):
    name = "translate"
    description = "文本翻译，支持中英日韩法德等多语言互译"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="translate_text",
                description=(
                    "将文本翻译为指定语言。支持中文、英文、日语、韩语、"
                    "法语、德语、西班牙语、俄语等多种语言互译。"
                    "会自动检测源语言。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "要翻译的文本",
                        },
                        "target_lang": {
                            "type": "string",
                            "description": (
                                "目标语言，支持: 中文/英文/日语/韩语/法语/德语等，"
                                "也可用语言代码如 zh/en/ja/ko/fr/de。"
                                "留空则自动选择（中文↔英文互译）。"
                            ),
                            "default": "auto",
                        },
                    },
                    "required": ["text"],
                },
                handler=self._translate,
                metadata={
                    "category": "read",
                    "required_all": ["text"],
                },
                keywords=["翻译", "中译英", "英译中", "多语言翻译"],
                intents=["translate_text"],
            ),
        ]

    def _translate(self, text: str, target_lang: str = "auto") -> str:
        if not text.strip():
            return "请提供要翻译的文本。"

        translated, source, target = _detect_and_translate(text, target_lang)

        if not translated:
            return f"翻译失败，请稍后再试。"

        return (
            f"原文 ({source}): {text}\n"
            f"译文 ({target}): {translated}"
        )


register(TranslateSkill)
