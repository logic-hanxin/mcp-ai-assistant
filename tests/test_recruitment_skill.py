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

    def test_submit_recruitment_application_infers_extension_from_content_type(self):
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
                    resume_image_url="https://multimedia.nt.qq.com.cn/download?appid=1406&fileid=abc",
                    upload_url="http://example.com/upload_resume/",
                )

        self.assertIn("纳新报名已提交", result)
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["files"]["resume_file"][0], "download.jpg")

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

    def test_query_resume_status_formats_successful_response(self):
        query_response = type(
            "QueryResp",
            (),
            {
                "status_code": 200,
                "text": '{"success": true}',
                "json": lambda self: {
                    "success": True,
                    "data": [
                        {
                            "name": "韩鑫",
                            "student_id": "3409307078",
                            "department": "运营部",
                            "status": "pending",
                            "status_display": "待面试",
                            "upload_time": "2026-03-23 20:00:00",
                            "interview_notes_count": 1,
                            "avg_rating": 4.5,
                        }
                    ],
                },
            },
        )()
        fake_requests = SimpleNamespace(get=lambda *args, **kwargs: query_response)
        with patch.dict(sys.modules, {"requests": fake_requests}):
            from assistant.skills.recruitment_skill import RecruitmentSkill

            skill = RecruitmentSkill()
            result = skill._query_resume_status(
                name="韩鑫",
                student_id="3409307078",
                status_url="http://example.com/query_resume_status/",
            )

        self.assertIn("找到 1 条报名记录", result)
        self.assertIn("待面试", result)
        self.assertNotIn("平均评分", result)

    def test_query_resume_status_formats_not_found_response(self):
        query_response = type(
            "QueryResp",
            (),
            {
                "status_code": 404,
                "text": '{"success": false}',
                "json": lambda self: {
                    "success": False,
                    "message": '未找到姓名为"韩鑫"的简历记录',
                },
            },
        )()
        fake_requests = SimpleNamespace(get=lambda *args, **kwargs: query_response)
        with patch.dict(sys.modules, {"requests": fake_requests}):
            from assistant.skills.recruitment_skill import RecruitmentSkill

            skill = RecruitmentSkill()
            result = skill._query_resume_status(
                name="韩鑫",
                status_url="http://example.com/query_resume_status/",
            )

        self.assertIn("报名状态查询失败", result)
        self.assertIn("未找到姓名", result)

    def test_query_resume_status_falls_back_to_post_when_get_is_not_json(self):
        get_response = type(
            "GetResp",
            (),
            {
                "status_code": 200,
                "text": "<html>bad gateway</html>",
                "json": lambda self: (_ for _ in ()).throw(ValueError("bad json")),
            },
        )()
        post_response = type(
            "PostResp",
            (),
            {
                "status_code": 200,
                "text": '{"success": true}',
                "json": lambda self: {
                    "success": True,
                    "data": [
                        {
                            "name": "韩鑫",
                            "student_id": "3409307078",
                            "department": "宣传部",
                            "status": "interviewed",
                            "status_display": "已面试",
                            "upload_time": "2026-03-23 21:00:00",
                        }
                    ],
                },
            },
        )()
        fake_requests = SimpleNamespace(
            get=lambda *args, **kwargs: get_response,
            post=lambda *args, **kwargs: post_response,
        )
        with patch.dict(sys.modules, {"requests": fake_requests}):
            from assistant.skills.recruitment_skill import RecruitmentSkill

            skill = RecruitmentSkill()
            result = skill._query_resume_status(
                name="韩鑫",
                student_id="3409307078",
                status_url="http://example.com/query_resume_status/",
            )

        self.assertIn("找到 1 条报名记录", result)
        self.assertIn("已面试", result)


if __name__ == "__main__":
    unittest.main()
