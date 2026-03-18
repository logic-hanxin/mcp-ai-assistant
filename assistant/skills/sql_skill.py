"""数据库查询 Skill - 查询 MySQL 数据库"""

from __future__ import annotations

import os

import pymysql
from assistant.skills.base import BaseSkill, ToolDefinition, register

# 数据库表结构摘要，供 LLM 生成 SQL 时参考
DB_SCHEMA = """
数据库: useinfo (Django 应用 - 社团/协会管理系统)

核心业务表:
- profiles_profile: 用户档案(id, name, student_id, phone, major, college, gender, age, department, position, service_hours, cloud_coins, activity_count, bio, birthday, avatar, user_id→auth_user)
- auth_user: 系统用户(id, username, email, is_superuser, is_staff, is_active, date_joined, last_login)
- department_department: 部门(id, name, description) — name值: organization/propaganda/finance/operation/secretariat/external
- department_member: 部门成员(id, name, student_id, phone, position_id→department_position, is_active, join_date)
- department_position: 职位(id, name, description, order, department_id→department_department) — name值: minister/vice_minister/member
- department_executivecommittee: 主席团(id, name, description)
- department_executivemember: 主席团成员(id, name, student_id, phone, position, is_active)

活动相关:
- activity_activity: 活动(id, title, description, start_time, end_time, credit_hours)
- events_activity: 活动扩展(id, title, description, start_time, end_time, location, max_participants, status, category, created_by_id→auth_user)
- events_activityregistration: 活动报名(id, activity_id→events_activity, user_id→auth_user, status, registered_at)
- profiles_servicehourapplication: 服务时长申请

财务:
- finance_financerecord: 财务记录(id, title, amount, category, record_type, date, description)
- finance_reimbursement: 报销申请(id, title, amount, status, applicant_id→auth_user)

聊天:
- chat_chatroom: 聊天室(id, name, room_type, created_at)
- chat_privatemessage: 私信(id, content, sender_id, receiver_id, timestamp)
- chat_roommessage: 群消息(id, content, sender_id, room_id, timestamp)

评审/比赛:
- judging_contest: 比赛(id, name, description, status, start_time, end_time)
- judging_contestant: 参赛者
- judging_score: 评分
- video_contest_videocontestsubmission: 视频比赛投稿

OKR:
- okr_okrperiod: OKR周期(id, name, start_date, end_date)
- okr_objective: 目标(id, title, description, progress, period_id, owner_id)
- okr_keyresult: 关键结果(id, title, progress, objective_id)
- okr_task: 任务(id, title, status, key_result_id)

其他:
- book_bookcategory / book_bookupload: 图书
- shop_product / shop_exchangerecord: 积分商城
- streaming_livestream: 直播
- video_coursevideo: 课程视频
- resume: 简历
- interview_interviewevaluation / interview_note: 面试
- qq_bot_qquserbinding / qq_bot_qqchatlog: QQ机器人
- volunteer_teaching_volunteerlocation / volunteer_teaching_volunteerreview: 志愿支教
""".strip()


def _get_connection() -> pymysql.Connection:
    """创建数据库连接（复用 .env 中的 DB_ 配置）"""
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "useinfo"),
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=10,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _execute_query(sql: str, max_rows: int = 50) -> str:
    """执行 SQL 查询并返回格式化结果"""
    # 安全检查：只允许 SELECT 查询
    stripped = sql.strip().lstrip("(").upper()
    allowed = ("SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN")
    if not any(stripped.startswith(kw) for kw in allowed):
        return "安全限制：只允许执行 SELECT / SHOW / DESCRIBE / EXPLAIN 查询。"

    conn = _get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchmany(max_rows)
            total = cursor.rowcount

            if not rows:
                return "查询成功，没有返回数据。"

            # 格式化输出
            columns = list(rows[0].keys())
            lines = [" | ".join(columns)]
            lines.append("-" * len(lines[0]))
            for row in rows:
                lines.append(" | ".join(str(v) if v is not None else "NULL" for v in row.values()))

            if total > max_rows:
                lines.append(f"\n... 共 {total} 行，仅显示前 {max_rows} 行")
            else:
                lines.append(f"\n共 {len(rows)} 行")

            return "\n".join(lines)
    except pymysql.Error as e:
        return f"SQL 执行错误: {e}"
    finally:
        conn.close()


class SqlSkill(BaseSkill):
    name = "sql"
    description = "查询 MySQL 数据库，支持社团管理系统数据查询"

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="query_database",
                description=(
                    "执行 SQL 查询语句来查询社团管理系统数据库(dangan)。"
                    "只允许 SELECT/SHOW/DESCRIBE 查询，不可修改数据。"
                    "可查询用户档案、部门成员、活动报名、财务记录、OKR等信息。\n\n"
                    f"数据库结构:\n{DB_SCHEMA}"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "要执行的 SQL 查询语句（仅限 SELECT/SHOW/DESCRIBE）",
                        },
                    },
                    "required": ["sql"],
                },
                handler=self._query_database,
            ),
            ToolDefinition(
                name="get_table_schema",
                description="获取指定表的结构信息（字段名、类型等），帮助了解表结构后再编写查询。",
                parameters={
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "表名，如 profiles_profile、auth_user、department_member 等",
                        },
                    },
                    "required": ["table_name"],
                },
                handler=self._get_table_schema,
            ),
        ]

    def _query_database(self, sql: str) -> str:
        if not sql.strip():
            return "请提供 SQL 查询语句。"
        return _execute_query(sql)

    def _get_table_schema(self, table_name: str) -> str:
        if not table_name.strip():
            return "请提供表名。"
        # 防注入：只允许字母数字下划线
        clean = "".join(c for c in table_name if c.isalnum() or c == "_")
        return _execute_query(f"DESCRIBE `{clean}`")


register(SqlSkill)
