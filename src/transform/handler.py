"""AWS Lambda entry point: runs every time a Toast export lands in the raw bucket.

Flow for each uploaded file:
  1. Skip it if DynamoDB says we've already processed this exact file (idempotency).
  2. Parse + check it (parser.py).
  3. Write clean JSON lines to the curated bucket, partitioned by month.
  4. Record the file in DynamoDB so a retry or re-upload doesn't double count.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse

import boto3
from botocore.exceptions import ClientError

from toast_parser import ParseError, parse_product_mix

log = logging.getLogger()
log.setLevel(logging.INFO)

s3 = boto3.client("s3")
dynamodb = boto3.client("dynamodb")

CURATED_BUCKET = os.environ["CURATED_BUCKET"]
LEDGER_TABLE = os.environ["LEDGER_TABLE"]


def curated_key(restaurant_id: str, month: str) -> str:
    # One file per restaurant per month. Re-processing the same month OVERWRITES
    # this key instead of adding a second copy, so totals can never double.
    return f"fact_item_sales/month={month}/{restaurant_id}.jsonl"


def already_processed(etag: str) -> bool:
    item = dynamodb.get_item(TableName=LEDGER_TABLE, Key={"file_etag": {"S": etag}})
    return "Item" in item


def record_processed(etag: str, source_key: str, result: dict, output_key: str) -> None:
    try:
        dynamodb.put_item(
            TableName=LEDGER_TABLE,
            Item={
                "file_etag": {"S": etag},
                "source_key": {"S": source_key},
                "output_key": {"S": output_key},
                "month": {"S": result["month"]},
                "restaurant_id": {"S": result["restaurant"]["restaurant_id"]},
                "rows": {"N": str(result["check"]["rows"])},
                "net_sales": {"N": str(result["check"]["net_sales"])},
                "processed_at": {"N": str(int(time.time()))},
            },
            # Two Lambdas racing on the same file: only the first one wins.
            ConditionExpression="attribute_not_exists(file_etag)",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise


def process_object(bucket: str, key: str) -> dict:
    head = s3.head_object(Bucket=bucket, Key=key)
    etag = head["ETag"].strip('"')  # fingerprint of the file's contents
    if already_processed(etag):
        log.info(json.dumps({"event": "skipped_duplicate", "key": key, "etag": etag}))
        return {"key": key, "status": "skipped_duplicate"}

    started = time.time()
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    result = parse_product_mix(body, source_name=key.rsplit("/", 1)[-1])

    out_key = curated_key(result["restaurant"]["restaurant_id"], result["month"])
    lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in result["rows"]) + "\n"
    s3.put_object(
        Bucket=CURATED_BUCKET,
        Key=out_key,
        Body=lines.encode("utf-8"),
        ContentType="application/x-ndjson",
    )
    record_processed(etag, key, result, out_key)

    summary = {
        "event": "processed",
        "key": key,
        "output": out_key,
        "month": result["month"],
        "rows": result["check"]["rows"],
        "net_sales": result["check"]["net_sales"],
        "seconds": round(time.time() - started, 2),
    }
    log.info(json.dumps(summary))  # structured logs -> easy to search in CloudWatch
    return {"key": key, "status": "processed", **summary}


def lambda_handler(event, context):
    results = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        try:
            results.append(process_object(bucket, key))
        except ParseError as exc:
            # Bad file: log it loudly and move on. Retrying won't fix a bad file.
            log.error(json.dumps({"event": "rejected", "key": key, "reason": str(exc)}))
            results.append({"key": key, "status": "rejected", "reason": str(exc)})
    return {"results": results}
