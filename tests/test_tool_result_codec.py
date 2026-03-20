import unittest

from assistant.skills.base import decode_tool_result, encode_tool_result


class ToolResultCodecTests(unittest.TestCase):
    def test_encode_decode_plain_text(self):
        decoded = decode_tool_result(encode_tool_result("普通文本"))
        self.assertEqual(decoded.text, "普通文本")
        self.assertIsNone(decoded.structured)

    def test_encode_decode_structured_payload(self):
        decoded = decode_tool_result(
            encode_tool_result(
                "天气查询完成",
                {"city": "上海", "weather": "多云"},
            )
        )
        self.assertEqual(decoded.text, "天气查询完成")
        self.assertEqual(decoded.structured, {"city": "上海", "weather": "多云"})

    def test_decode_invalid_marker_payload_falls_back_to_raw_text(self):
        decoded = decode_tool_result("原始文本\n__ASSISTANT_STRUCTURED_RESULT__:not-base64")
        self.assertEqual(decoded.text, "原始文本\n__ASSISTANT_STRUCTURED_RESULT__:not-base64")
        self.assertIsNone(decoded.structured)


if __name__ == "__main__":
    unittest.main()
