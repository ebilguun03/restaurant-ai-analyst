"""Safety check for SQL the AI writes, before anything reaches Athena.

The model is helpful but not trusted. This guard makes sure every query is:
  * one single statement
  * read-only (SELECT or WITH ... SELECT)
  * only touching the tables we allow
  * capped with a LIMIT so a bad query can't return millions of rows
"""
from __future__ import annotations

import re

ALLOWED_TABLES = {"fact_item_sales", "dim_menu_item", "monthly_summary"}
DEFAULT_LIMIT = 200

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|create|alter|truncate|grant|revoke|"
    r"unload|msck|call|execute|prepare|deallocate|vacuum|optimize|use|set|reset)\b",
    re.IGNORECASE,
)


class UnsafeSQL(ValueError):
    """The query was blocked. The message is shown to the model so it can fix it."""


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)


def _strip_string_literals(sql: str) -> str:
    # 'Desserts' or 'it''s' -> '' so words inside strings don't trip the checks
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def check_sql(sql: str) -> str:
    """Return a safe, LIMITed version of the query, or raise UnsafeSQL."""
    if not sql or not sql.strip():
        raise UnsafeSQL("Empty query.")

    cleaned = _strip_comments(sql).strip().rstrip(";").strip()
    bare = _strip_string_literals(cleaned)

    if ";" in bare:
        raise UnsafeSQL("Only one statement is allowed.")
    if not re.match(r"^\s*(select|with)\b", bare, re.IGNORECASE):
        raise UnsafeSQL("Only SELECT queries are allowed.")
    bad = FORBIDDEN.search(bare)
    if bad:
        raise UnsafeSQL(f"'{bad.group(0)}' is not allowed; this tool is read-only.")

    cte_names = {m.lower() for m in re.findall(r"(?:with|,)\s*([a-z_][a-z0-9_]*)\s+as\s*\(", bare, re.IGNORECASE)}
    referenced = {
        name.lower().split(".")[-1].strip('"')
        for name in re.findall(r"\b(?:from|join)\s+([a-z_\"][a-z0-9_.\"]*)", bare, re.IGNORECASE)
    }
    unknown = referenced - ALLOWED_TABLES - cte_names
    if unknown:
        raise UnsafeSQL(
            f"Unknown table(s): {sorted(unknown)}. Use only: {sorted(ALLOWED_TABLES)}."
        )

    if not re.search(r"\blimit\s+\d+\s*$", bare, re.IGNORECASE):
        cleaned = f"{cleaned}\nLIMIT {DEFAULT_LIMIT}"
    return cleaned
