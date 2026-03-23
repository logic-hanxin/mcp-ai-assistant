"""纳新报名 Skill（图片简历版）"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse
from typing import Any

from assistant.skills.base import BaseSkill, ToolDefinition, register


DEFAULT_UPLOAD_URL = os.getenv("RECRUITMENT_UPLOAD_URL", "http://120.48.176.249/upload_resume/")
DEPARTMENTS = {
    "组织部",
    "宣传部",
    "财政部",
    "秘书处",
    "外联部",
    "运营部",
}


def _guess_filename(file_url: str, response: Any = None) -> str:
    disposition = (response.headers.get("Content-Disposition", "") if response else "") or ""
    if "filename=" in disposition:
        filename = disposition.split("filename=", 1)[1].strip().strip('"')
        if filename:
            return filename

    parsed = urlparse(file_url)
    path_name = Path(unquote(parsed.path)).name
    if path_name:
        return path_name
    return "resume.jpg"


class RecruitmentSkill(BaseSkill):
    name = "recruitment"
    description = "纳新报名：提交姓名、QQ、部门和简历图片到报名系统"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="submit_recruitment_application",
                description="提交纳新报名表，自动上传简历图片并填写姓名、QQ号和目标部门。",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "报名人姓名"},
                        "qq_number": {"type": "string", "description": "报名人QQ号"},
                        "department": {"type": "string", "description": "部门名称，如 组织部/宣传部/财政部/秘书处/外联部/运营部"},
                        "resume_image_url": {"type": "string", "description": "简历图片 URL（jpg/jpeg/png）"},
                        "upload_url": {"type": "string", "description": "报名接口地址，默认使用系统配置", "default": ""},
                    },
                    "required": ["name", "qq_number", "department", "resume_image_url"],
                },
                handler=self._submit_recruitment_application,
                metadata={
                    "category": "write",
                    "side_effect": "external_trigger",
                    "required_all": ["name", "qq_number", "department", "resume_image_url"],
                    "store_args": {
                        "qq_number": "last_target_qq",
                        "resume_image_url": "last_image_url",
                    },
                    "store_result": ["last_recruitment_result"],
                },
                result_parser=self._parse_submit_result,
                keywords=["纳新报名", "提交简历", "加入部门", "报名协会"],
                intents=["submit_recruitment_application", "recruitment_signup"],
            )
        ]

    def _submit_recruitment_application(
        self,
        name: str,
        qq_number: str,
        department: str,
        resume_image_url: str,
        upload_url: str = "",
    ) -> str:
        applicant_name = (name or "").strip()
        applicant_qq = str(qq_number or "").strip()
        department_name = (department or "").strip()
        image_url = (resume_image_url or "").strip()
        target_url = (upload_url or "").strip() or DEFAULT_UPLOAD_URL

        if not applicant_name or not applicant_qq or not department_name or not image_url:
            return "报名信息不完整，需要姓名、QQ号、部门和简历图片。"
        if department_name not in DEPARTMENTS:
            return f"不支持的部门：{department_name}。可选部门：{'、'.join(sorted(DEPARTMENTS))}"
        if not target_url:
            return "未配置报名接口地址，请设置 RECRUITMENT_UPLOAD_URL。"
        if not image_url.startswith(("http://", "https://")):
            return "请先发送一张 jpg、jpeg 或 png 简历图片，我会用图片链接帮你报名。"

        try:
            import requests

            file_resp = requests.get(image_url, timeout=30)
            file_resp.raise_for_status()
            file_bytes = file_resp.content
            filename = _guess_filename(image_url, file_resp)
            content_type = file_resp.headers.get("Content-Type", "application/octet-stream")

            lower_name = filename.lower()
            if not (lower_name.endswith(".jpg") or lower_name.endswith(".jpeg") or lower_name.endswith(".png")):
                return "简历图片格式不支持，请上传 jpg、jpeg 或 png。"

            files = {
                "resume_file": (filename, file_bytes, content_type),
            }
            data = {
                "name": applicant_name,
                "student_id": applicant_qq,
                "department": department_name,
            }
            resp = requests.post(target_url, data=data, files=files, timeout=60)
            response_text = resp.text[:500]

            if resp.status_code >= 400:
                return (
                    f"报名提交失败：HTTP {resp.status_code}\n"
                    f"接口：{target_url}\n"
                    f"响应：{response_text}"
                )

            return (
                f"纳新报名已提交！\n"
                f"  姓名: {applicant_name}\n"
                f"  QQ号: {applicant_qq}\n"
                f"  部门: {department_name}\n"
                f"  图片: {filename}\n"
                f"  接口: {target_url}\n"
                f"  状态码: {resp.status_code}"
            )
        except Exception as e:
            return f"报名提交失败: {e}"

    def _parse_submit_result(self, args: dict, result: str) -> dict | None:
        return {
            "action": "submit_recruitment_application",
            "name": str(args.get("name", "")).strip(),
            "qq_number": str(args.get("qq_number", "")).strip(),
            "department": str(args.get("department", "")).strip(),
            "resume_image_url": str(args.get("resume_image_url", "")).strip(),
            "submitted": "报名已提交" in result,
            "result": result[:500],
        }


register(RecruitmentSkill)
