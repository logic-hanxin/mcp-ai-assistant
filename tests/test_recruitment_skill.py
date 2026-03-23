import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch


class RecruitmentSkillTests(unittest.TestCase):
    def test_submit_recruitment_application_posts_form_and_image(self):
        file_response = type(
            "FileResp",
            (),
            {
                "content": b"resume-bytes",
                "headers": {"Content-Type": "image/jpeg"},
                "raise_for_status": lambda self: None,
            },
        )()
        submit_response = type(
            "SubmitResp",
            (),
            {"status_code": 200, "text": '{"ok":true}'},
        )()

        fake_requests = SimpleNamespace(
            get=lambda *args, **kwargs: file_response,
            post=lambda *args, **kwargs: submit_response,
        )
        with patch.dict(sys.modules, {"requests": fake_requests}):
            from assistant.skills.recruitment_skill import RecruitmentSkill

            skill = RecruitmentSkill()

            with patch.object(fake_requests, "post", return_value=submit_response) as mock_post:
                result = skill._submit_recruitment_application(
                    name="韩鑫",
                    qq_number="3409307078",
                    department="组织部",
                    resume_image_url="https://files.example.com/resume.jpg",
                    upload_url="http://example.com/upload_resume/",
                )

        self.assertIn("纳新报名已提交", result)
        self.assertTrue(mock_post.called)
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["files"]["resume_file"][0], "resume.jpg")

    def test_submit_recruitment_application_rejects_unknown_department(self):
        fake_requests = SimpleNamespace()
        with patch.dict(sys.modules, {"requests": fake_requests}):
            from assistant.skills.recruitment_skill import RecruitmentSkill

            skill = RecruitmentSkill()
        result = skill._submit_recruitment_application(
            name="韩鑫",
            qq_number="3409307078",
            department="测试部",
            resume_image_url="https://files.example.com/resume.jpg",
            upload_url="http://example.com/upload_resume/",
        )
        self.assertIn("不支持的部门", result)

    def test_submit_recruitment_application_rejects_non_image_extension(self):
        fake_requests = SimpleNamespace(
            get=lambda *args, **kwargs: type(
                "FileResp",
                (),
                {
                    "content": b"resume-bytes",
                    "headers": {"Content-Type": "application/pdf"},
                    "raise_for_status": lambda self: None,
                },
            )(),
        )
        with patch.dict(sys.modules, {"requests": fake_requests}):
            from assistant.skills.recruitment_skill import RecruitmentSkill

            skill = RecruitmentSkill()
            result = skill._submit_recruitment_application(
                name="韩鑫",
                qq_number="3409307078",
                department="组织部",
                resume_image_url="https://files.example.com/resume.pdf",
                upload_url="http://example.com/upload_resume/",
            )

        self.assertIn("格式不支持", result)

    def test_submit_recruitment_application_rejects_non_http_image_source(self):
        fake_requests = SimpleNamespace()
        with patch.dict(sys.modules, {"requests": fake_requests}):
            from assistant.skills.recruitment_skill import RecruitmentSkill

            skill = RecruitmentSkill()
            result = skill._submit_recruitment_application(
                name="韩鑫",
                qq_number="3409307078",
                department="组织部",
                resume_image_url="/tmp/resume.jpg",
                upload_url="http://example.com/upload_resume/",
            )

        self.assertIn("请先发送一张", result)


if __name__ == "__main__":
    unittest.main()
