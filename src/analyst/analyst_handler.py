"""HTTP entry point (API Gateway -> Lambda).

  GET  /     -> the chat page
  POST /ask  -> {"question": "..."} with header x-access-key  ->  answer + trace

Every question and answer is written to DynamoDB, so there is a full audit trail of
what was asked, which SQL ran and what the AI said.
"""
from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import time
import uuid
from decimal import Decimal
from pathlib import Path

import boto3

from agent import ask

log = logging.getLogger()
log.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
PAGE = (Path(__file__).parent / "page.html").read_text(encoding="utf-8")
MAX_QUESTION_CHARS = 500
_model_client = None


def model_client():
    """Pick the model provider once per Lambda container (MODEL_PROVIDER = anthropic | bedrock)."""
    global _model_client
    if _model_client is None:
        if os.environ.get("MODEL_PROVIDER", "bedrock") == "anthropic":
            from anthropic_client import from_ssm
            _model_client = from_ssm(os.environ["ANTHROPIC_KEY_PARAM"])
        else:
            _model_client = boto3.client("bedrock-runtime")
    return _model_client


def _json(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"content-type": "application/json"}, "body": json.dumps(body)}


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "/")

    if method == "GET" and path in ("/", ""):
        return {"statusCode": 200, "headers": {"content-type": "text/html; charset=utf-8"}, "body": PAGE}
    if not (method == "POST" and path == "/ask"):
        return _json(404, {"error": "Not found"})

    key = (event.get("headers") or {}).get("x-access-key", "")
    if not hmac.compare_digest(key.encode(), os.environ["ACCESS_KEY"].encode()):
        return _json(401, {"error": "Wrong access key"})

    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    try:
        question = str(json.loads(raw).get("question", "")).strip()
    except json.JSONDecodeError:
        return _json(400, {"error": "Body must be JSON"})
    if not question or len(question) > MAX_QUESTION_CHARS:
        return _json(400, {"error": f"Ask a question of 1-{MAX_QUESTION_CHARS} characters"})

    try:
        result = ask(question, model_client(), os.environ["MODEL_ID"])
    except Exception as exc:  # model or AWS outage: tell the user, keep details in logs
        log.exception("ask failed")
        return _json(502, {"error": f"The analyst is unavailable right now ({type(exc).__name__})."})

    record = {
        "id": str(uuid.uuid4()),
        "asked_at": int(time.time()),
        "question": question,
        "answer": result["answer"],
        "queries": json.dumps(result["queries"]),
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "seconds": Decimal(str(result["seconds"])),
        "model_id": os.environ["MODEL_ID"],
        "provider": os.environ.get("MODEL_PROVIDER", "bedrock"),
    }
    dynamodb.Table(os.environ["QUESTION_LOG_TABLE"]).put_item(Item=record)
    log.info(json.dumps({"event": "answered", "id": record["id"], "queries": len(result["queries"]),
                         "seconds": result["seconds"], "input_tokens": result["input_tokens"],
                         "output_tokens": result["output_tokens"]}))
    return _json(200, {"id": record["id"], **result})
