"""数据库查询 Skill - 动态发现表结构并查询 MySQL 数据库"""

from __future__ import annotations

import os
import re

import pymysql
from assistant.skills.base import BaseSkill, ToolDefinition, register


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
                name="list_tables",
                description=(
                    "【第1步】列出数据库中所有的表。"
                    "查询数据库时必须先调用此工具，看看有哪些表可用，"
                    "再决定查哪张表。可按关键词过滤。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "可选，按关键词过滤表名（如 'user'、'finance'、'activity'）",
                        },
                    },
                },
                handler=self._list_tables,
                metadata={
                    "category": "read",
                    "blackboard_writes": ["last_db_result"],
                    "store_result": ["last_db_result"],
                },
                result_parser=self._parse_list_tables_result,
                keywords=["数据库表", "查看表", "有哪些表"],
                intents=["list_database_tables"],
            ),
            ToolDefinition(
                name="get_table_schema",
                description=(
                    "【第2步】查看指定表的字段结构（字段名、类型、注释、外键关系）。"
                    "在构造 SQL 之前必须先调用此工具了解表有哪些字段、每个字段的含义，"
                    "不要凭猜测写 SQL。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "表名，如 auth_user、finance_financerecord 等",
                        },
                    },
                    "required": ["table_name"],
                },
                handler=self._get_table_schema,
                metadata={
                    "category": "read",
                    "required_all": ["table_name"],
                    "blackboard_writes": ["last_db_result"],
                    "store_args": {"table_name": "last_table_name"},
                    "store_result": ["last_db_result"],
                },
                result_parser=self._parse_schema_result,
                keywords=["表结构", "字段信息", "schema", "列定义"],
                intents=["inspect_table_schema"],
            ),
            ToolDefinition(
                name="query_database",
                description=(
                    "【第3步】执行 SQL 查询语句。只允许 SELECT/SHOW/DESCRIBE 查询，不可修改数据。\n\n"
                    "重要：在执行查询前，你必须已经完成：\n"
                    "1. 调用 list_tables 找到相关的表\n"
                    "2. 调用 get_table_schema 查看表的字段和含义\n"
                    "3. 根据真实字段信息构造正确的 SQL\n"
                    "禁止跳过前两步直接查询。"
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
                metadata={
                    "category": "read",
                    "required_all": ["sql"],
                    "blackboard_writes": ["last_db_result"],
                    "store_result": ["last_db_result"],
                },
                result_parser=self._parse_query_result,
                keywords=["SQL查询", "查数据库", "执行查询", "select"],
                intents=["query_database"],
            ),
        ]

    def _list_tables(self, keyword: str = "") -> str:
        conn = _get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                rows = cursor.fetchall()
                if not rows:
                    return "数据库中没有表。"
                table_names = [list(r.values())[0] for r in rows]
                if keyword:
                    keyword_lower = keyword.lower()
                    table_names = [t for t in table_names if keyword_lower in t.lower()]
                if not table_names:
                    return f"没有找到包含 '{keyword}' 的表。"
                return f"共 {len(table_names)} 张表:\n" + "\n".join(f"  - {t}" for t in table_names)
        except pymysql.Error as e:
            return f"查询失败: {e}"
        finally:
            conn.close()

    def _get_table_schema(self, table_name: str) -> str:
        if not table_name.strip():
            return "请提供表名。"
        # 防注入：只允许字母数字下划线
        clean = "".join(c for c in table_name if c.isalnum() or c == "_")

        conn = _get_connection()
        try:
            with conn.cursor() as cursor:
                # SHOW FULL COLUMNS 可以拿到 Comment
                cursor.execute(f"SHOW FULL COLUMNS FROM `{clean}`")
                rows = cursor.fetchall()
                if not rows:
                    return f"表 {clean} 不存在或没有字段。"

                lines = [f"表 `{clean}` 的字段结构:"]
                lines.append(f"{'字段名':<25} {'类型':<20} {'允许NULL':<8} {'键':<6} {'注释'}")
                lines.append("-" * 90)
                for r in rows:
                    field = r.get("Field", "")
                    ftype = r.get("Type", "")
                    null = r.get("Null", "")
                    key = r.get("Key", "")
                    comment = r.get("Comment", "")
                    lines.append(f"{field:<25} {ftype:<20} {null:<8} {key:<6} {comment}")

                # 查看外键关系
                db_name = os.getenv("DB_NAME", "useinfo")
                cursor.execute(
                    "SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
                    "FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
                    "AND REFERENCED_TABLE_NAME IS NOT NULL",
                    (db_name, clean),
                )
                fk_rows = cursor.fetchall()
                if fk_rows:
                    lines.append("\n外键关系:")
                    for fk in fk_rows:
                        lines.append(
                            f"  {fk['COLUMN_NAME']} → "
                            f"{fk['REFERENCED_TABLE_NAME']}.{fk['REFERENCED_COLUMN_NAME']}"
                        )

                return "\n".join(lines)
        except pymysql.Error as e:
            return f"查询表结构失败: {e}"
        finally:
            conn.close()

    def _query_database(self, sql: str) -> str:
        if not sql.strip():
            return "请提供 SQL 查询语句。"
        return _execute_query(sql)

    def _parse_list_tables_result(self, args: dict, result: str) -> dict | None:
        tables = []
        for line in result.splitlines():
            match = re.match(r"^\s*-\s+([A-Za-z0-9_]+)$", line.strip())
            if match:
                tables.append(match.group(1))
        return {
            "action": "list_tables",
            "keyword": str(args.get("keyword", "")).strip(),
            "tables": tables,
        }

    def _parse_schema_result(self, args: dict, result: str) -> dict | None:
        table_name = str(args.get("table_name", "")).strip()
        fields = []
        for line in result.splitlines():
            line = line.rstrip()
            if not line or line.startswith("表 `") or line.startswith("-") or line.startswith("字段名") or line.startswith("外键关系"):
                continue
            if "→" in line:
                continue
            parts = re.split(r"\s{2,}", line.strip())
            if len(parts) >= 2:
                fields.append(
                    {
                        "name": parts[0].strip(),
                        "type": parts[1].strip(),
                        "nullable": parts[2].strip() if len(parts) > 2 else "",
                        "key": parts[3].strip() if len(parts) > 3 else "",
                        "comment": parts[4].strip() if len(parts) > 4 else "",
                    }
                )
        return {
            "action": "get_table_schema",
            "table_name": table_name,
            "fields": fields,
            "result": result[:500],
        }

    def _parse_query_result(self, args: dict, result: str) -> dict | None:
        sql = str(args.get("sql", "")).strip()
        lines = [line for line in result.splitlines() if line.strip()]
        if len(lines) < 2:
            return {"action": "query_database", "sql": sql, "rows": [], "result": result[:500]}

        header = lines[0]
        divider = lines[1]
        if "|" not in header or set(divider) != {"-"}:
            return {"action": "query_database", "sql": sql, "rows": [], "result": result[:500]}

        columns = [part.strip() for part in header.split("|")]
        rows = []
        for line in lines[2:]:
            if line.startswith("共 ") or line.startswith("... 共"):
                break
            values = [part.strip() for part in line.split("|")]
            if len(values) == len(columns):
                rows.append(dict(zip(columns, values)))

        return {
            "action": "query_database",
            "sql": sql,
            "columns": columns,
            "rows": rows,
            "result": result[:500],
        }


register(SqlSkill)
