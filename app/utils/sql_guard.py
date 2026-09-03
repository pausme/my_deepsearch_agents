"""
SQL 只读守卫（纯函数，可独立测试）

对模型生成的 SQL 做安全校验后再交给 mysql-connector 执行：
- 只允许 SELECT / SHOW / DESC / EXPLAIN
- 表名必须在白名单内（白名单来自 SHOW TABLES 的真实结果）
- 自动补 LIMIT，防止全表扫描拖垮教学库
- 拒绝多语句、注释注入和危险关键字

设计原则：校验通过返回改写后的安全 SQL；不通过返回明确错误原因，
由工具层把错误作为字符串交回模型，让它自行修正查询。
"""

import re

# 危险关键字：作为独立单词出现即拒绝（\b 边界保证不会误伤 updated_at、delete_flag 等字段名）
_FORBIDDEN_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|replace|grant|revoke|"
    r"rename|call|lock|unlock|handler|load_file|outfile|set|use|information_schema|"
    r"mysql\.|performance_schema)\b",
    re.IGNORECASE,
)

_ALLOWED_LEADING = re.compile(
    r"^\s*(select|show|desc|describe|explain)\b",
    re.IGNORECASE,
)

# 表引用提取：FROM/JOIN/INTO/UPDATE 后面的标识符（支持反引号）
_TABLE_REF_PATTERN = re.compile(
    r"\b(?:from|join|into|update)\s+`?([A-Za-z0-9_一-鿿]+)`?",
    re.IGNORECASE,
)

_DEFAULT_LIMIT = 100


def strip_sql_comments(query: str) -> str:
    """去掉 SQL 注释（--、#、 块注释），防止把危险语句藏进注释绕过校验。"""
    query = re.sub(r"/\*.*?\*/", " ", query, flags=re.DOTALL)
    query = re.sub(r"(?m)(--|#)[^\n]*$", " ", query)
    return query.strip()


def validate_readonly_sql(query: str, allowed_tables: set[str] | list[str]) -> tuple[str | None, str]:
    """
    校验并规范化只读 SQL

    :param query: 模型生成的 SQL
    :param allowed_tables: 允许查询的表名集合
    :return: (安全 SQL, 错误信息)；校验通过时错误信息为空串，失败时安全 SQL 为 None
    """
    if not query or not query.strip():
        return None, "SQL 语句为空"

    cleaned = strip_sql_comments(query)

    # 拒绝多语句：注释剥离后按分号切分，多于一个非空片段即拒绝
    statements = [s for s in cleaned.split(";") if s.strip()]
    if len(statements) > 1:
        return None, "安全限制：一次只允许执行一条 SQL 语句"
    cleaned = statements[0].strip().rstrip(";").strip()

    if not cleaned:
        return None, "SQL 语句为空"

    if not _ALLOWED_LEADING.match(cleaned):
        return None, "安全限制：只允许执行 SELECT / SHOW / DESC / EXPLAIN 只读查询"

    forbidden = _FORBIDDEN_PATTERN.search(cleaned)
    if forbidden:
        return None, f"安全限制：检测到不允许的关键字 '{forbidden.group(1).upper()}'"

    allowed = {table.lower() for table in allowed_tables}
    referenced = [t.lower() for t in _TABLE_REF_PATTERN.findall(cleaned)]
    unknown = [t for t in referenced if t not in allowed]
    if unknown:
        return None, f"安全限制：表不在可查询白名单内：{', '.join(unknown)}"

    # SELECT 自动补 LIMIT；SHOW/DESC/EXPLAIN 不需要
    if cleaned.lower().startswith("select") and not re.search(r"\blimit\s+\d+", cleaned, re.IGNORECASE):
        cleaned = f"{cleaned} LIMIT {_DEFAULT_LIMIT}"

    return cleaned, ""


def validate_table_name(table_name: str, allowed_tables: set[str] | list[str]) -> str:
    """
    校验表名是否在白名单内，返回带反引号的安全标识符

    :raises ValueError: 表名不合法或不在白名单内
    """
    name = str(table_name).strip().strip("`")
    if not re.fullmatch(r"[A-Za-z0-9_一-鿿]+", name):
        raise ValueError(f"表名包含非法字符：{table_name}")
    allowed = {t.lower() for t in allowed_tables}
    if name.lower() not in allowed:
        raise ValueError(f"表不在可查询白名单内：{name}")
    return f"`{name}`"
