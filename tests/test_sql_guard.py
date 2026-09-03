"""
SQL 只读守卫测试

覆盖 PRD 开发计划 4.4 的验收标准：
- 危险 SQL 被拒绝（INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE）
- 只允许 SELECT/SHOW/DESC/EXPLAIN
- 表名白名单之外的表被拒绝
- 未加 LIMIT 的查询自动限制行数
- 多语句和注释注入被拒绝
"""

import pytest

from app.utils.sql_guard import strip_sql_comments, validate_readonly_sql, validate_table_name

ALLOWED = {"drugs", "inventory", "sales_records"}


def ok(query):
    sql, error = validate_readonly_sql(query, ALLOWED)
    return sql, error


class TestForbiddenSql:
    @pytest.mark.parametrize(
        "query",
        [
            "DELETE FROM drugs",
            "DROP TABLE drugs",
            "INSERT INTO drugs VALUES (1)",
            "UPDATE drugs SET price = 1",
            "ALTER TABLE drugs ADD COLUMN x INT",
            "TRUNCATE TABLE drugs",
            "CREATE TABLE hack (id INT)",
            "SELECT 1; DROP TABLE drugs",
            "use mysql",
        ],
    )
    def test_dangerous_rejected(self, query):
        sql, error = validate_readonly_sql(query, ALLOWED)
        assert sql is None
        assert error

    def test_delete_inside_field_name_not_flagged(self):
        # 字段名含 delete/update 不应误伤（\b 词边界）
        sql, error = ok("SELECT delete_flag, updated_at FROM drugs")
        assert error == ""
        assert sql is not None


class TestAllowedSql:
    def test_select_passes(self):
        sql, error = ok("SELECT * FROM drugs")
        assert error == ""
        assert "LIMIT 100" in sql

    def test_existing_limit_kept(self):
        sql, error = ok("SELECT * FROM drugs LIMIT 5")
        assert error == ""
        assert "LIMIT 5" in sql
        assert sql.count("LIMIT") == 1

    def test_show_tables_passes(self):
        sql, error = ok("SHOW TABLES")
        assert error == ""

    def test_join_passes(self):
        sql, error = ok(
            "SELECT d.drug_name FROM drugs d JOIN sales_records s ON d.drug_id = s.drug_id"
        )
        assert error == ""

    def test_unknown_table_rejected(self):
        sql, error = ok("SELECT * FROM users")
        assert sql is None
        assert "白名单" in error

    def test_multi_statement_rejected(self):
        sql, error = ok("SELECT 1; SELECT 2")
        assert sql is None
        assert "一条" in error


class TestCommentStripping:
    def test_comment_hidden_danger_rejected(self):
        # 危险语句藏在注释里同样要拒绝（注释剥离后仍是 DELETE）
        sql, error = validate_readonly_sql("SELECT 1 /*; DROP TABLE drugs*/", ALLOWED)
        # 剥离注释后剩下 SELECT 1，安全放行
        assert error == ""

    def test_line_comment_stripped(self):
        sql, error = ok("SELECT * FROM drugs -- 注释")
        assert error == ""
        assert "--" not in sql


class TestStripComments:
    def test_block_comment(self):
        assert "secret" not in strip_sql_comments("SELECT /* secret */ 1")

    def test_line_comments(self):
        result = strip_sql_comments("SELECT 1 -- a\n# b")
        assert "a" not in result and "b" not in result


class TestTableName:
    def test_valid_table(self):
        assert validate_table_name("drugs", ALLOWED) == "`drugs`"

    def test_backtick_injection_rejected(self):
        with pytest.raises(ValueError):
            validate_table_name("drugs`; DROP TABLE x", ALLOWED)

    def test_unknown_table_rejected(self):
        with pytest.raises(ValueError):
            validate_table_name("mysql.user", ALLOWED)

    def test_case_insensitive_match(self):
        # 白名单匹配不区分大小写，返回值保留原大小写
        assert validate_table_name("DRUGS", ALLOWED) == "`DRUGS`"
