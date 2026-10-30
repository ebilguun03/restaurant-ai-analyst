"""Run a (pre-checked) SQL query in Athena and return the rows."""
from __future__ import annotations

import os
import time

import boto3

MAX_ROWS_TO_MODEL = 50  # the model gets a sample; it doesn't need thousands of rows


class QueryFailed(RuntimeError):
    pass


def run_query(sql: str, athena=None, timeout_s: float = 30.0) -> dict:
    athena = athena or boto3.client("athena")
    started = time.time()
    qid = athena.start_query_execution(
        QueryString=sql,
        WorkGroup=os.environ["ATHENA_WORKGROUP"],
        QueryExecutionContext={"Database": os.environ["GLUE_DATABASE"]},
    )["QueryExecutionId"]

    while True:
        ex = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        state = ex["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            raise QueryFailed(ex["Status"].get("StateChangeReason", state))
        if time.time() - started > timeout_s:
            athena.stop_query_execution(QueryExecutionId=qid)
            raise QueryFailed(f"Query took longer than {timeout_s:.0f}s and was stopped.")
        time.sleep(0.4)

    result = athena.get_query_results(QueryExecutionId=qid, MaxResults=MAX_ROWS_TO_MODEL + 1)
    rows = [[c.get("VarCharValue") for c in r["Data"]] for r in result["ResultSet"]["Rows"]]
    columns, data = (rows[0], rows[1:]) if rows else ([], [])
    stats = ex.get("Statistics", {})
    return {
        "columns": columns,
        "rows": data,
        "athena_ms": stats.get("TotalExecutionTimeInMillis"),
        "bytes_scanned": stats.get("DataScannedInBytes"),
    }
