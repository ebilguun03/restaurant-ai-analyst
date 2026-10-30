"""The AI analyst: a small tool-use loop on Amazon Bedrock.

How it works:
  1. The owner's question goes to the model with the schema and one tool: run_sql.
  2. The model decides what it needs and asks to run a SQL query.
  3. We check the SQL (sql_guard), run it in Athena, and hand back the rows.
  4. Steps 2-3 repeat until the model has enough to answer (max MAX_TOOL_CALLS).
  5. The model replies in plain English, using only numbers it got from the data.
"""
from __future__ import annotations

import json
import time

from athena import QueryFailed, run_query
from schema import SCHEMA
from sql_guard import UnsafeSQL, check_sql

MAX_TOOL_CALLS = 6

SYSTEM_PROMPT = f"""You are a sales analyst for an independent restaurant. You answer the owner's
questions using ONLY numbers returned by the run_sql tool. Never guess or invent numbers.

{SCHEMA}

How to work:
  * Query first, then answer. Use as few queries as possible.
  * If the data can't answer the question (e.g. days of the week, customers, months not loaded),
    say so plainly and suggest what the data CAN tell them.
  * You can only read data. If asked to change or delete anything, explain that you are read-only.
  * Answer in 1-4 short sentences a busy owner can act on. Round money to the cent, use $ and commas.
"""

RUN_SQL_TOOL = {
    "toolSpec": {
        "name": "run_sql",
        "description": "Run one read-only Athena SQL query against the sales tables and get the rows back.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "A single SELECT query (Trino SQL)."},
                    "why": {"type": "string", "description": "One short line on what this query checks."},
                },
                "required": ["sql"],
            }
        },
    }
}


def ask(question: str, bedrock, model_id: str, run_sql=run_query) -> dict:
    """Answer one question. Returns the answer plus a full trace for the audit log."""
    started = time.time()
    messages = [{"role": "user", "content": [{"text": question}]}]
    trace: list[dict] = []
    usage = {"input_tokens": 0, "output_tokens": 0}

    for _ in range(MAX_TOOL_CALLS + 1):
        resp = bedrock.converse(
            modelId=model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=messages,
            toolConfig={"tools": [RUN_SQL_TOOL]},
            inferenceConfig={"maxTokens": 1024, "temperature": 0},
        )
        usage["input_tokens"] += resp.get("usage", {}).get("inputTokens", 0)
        usage["output_tokens"] += resp.get("usage", {}).get("outputTokens", 0)
        message = resp["output"]["message"]
        messages.append(message)

        tool_calls = [c["toolUse"] for c in message["content"] if "toolUse" in c]
        if resp.get("stopReason") != "tool_use" or not tool_calls:
            answer = " ".join(c["text"] for c in message["content"] if "text" in c).strip()
            return _result(answer, trace, usage, started)

        if len(trace) >= MAX_TOOL_CALLS:
            break

        results = []
        for call in tool_calls:
            step = {"sql": call["input"].get("sql", ""), "why": call["input"].get("why", "")}
            try:
                safe_sql = check_sql(step["sql"])
                step["sql"] = safe_sql
                out = run_sql(safe_sql)
                step.update(rows=len(out["rows"]), athena_ms=out.get("athena_ms"))
                content, status = {"columns": out["columns"], "rows": out["rows"]}, "success"
            except (UnsafeSQL, QueryFailed) as exc:
                step["error"] = str(exc)
                content, status = {"error": str(exc)}, "error"
            trace.append(step)
            results.append({"toolResult": {"toolUseId": call["toolUseId"], "content": [{"json": content}], "status": status}})
        messages.append({"role": "user", "content": results})

    return _result(
        "I couldn't finish that within my query limit. Try asking a narrower question.",
        trace, usage, started,
    )


def _result(answer: str, trace: list, usage: dict, started: float) -> dict:
    return {"answer": answer, "queries": trace, **usage, "seconds": round(time.time() - started, 2)}


if __name__ == "__main__":  # local use: python src/analyst/agent.py "question"
    import os
    import sys

    import boto3

    out = ask(" ".join(sys.argv[1:]), boto3.client("bedrock-runtime"), os.environ["MODEL_ID"])
    print(json.dumps(out, indent=2))
