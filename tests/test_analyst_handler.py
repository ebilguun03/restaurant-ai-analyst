"""HTTP layer: auth, input checks, page serving and audit logging (mocked AWS)."""
import importlib
import json

import boto3
import pytest
from moto import mock_aws

TABLE = "question-log-test"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.setenv("ACCESS_KEY", "secret123")
    monkeypatch.setenv("MODEL_ID", "test-model")
    monkeypatch.setenv("QUESTION_LOG_TABLE", TABLE)
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        import analyst_handler
        importlib.reload(analyst_handler)
        monkeypatch.setattr(analyst_handler, "ask", lambda q, b, m: {
            "answer": "March net sales were $12,345.67.",
            "queries": [{"sql": "SELECT 1", "rows": 1}],
            "input_tokens": 250, "output_tokens": 50, "seconds": 2.5,
        })
        yield analyst_handler


def event(method="POST", path="/ask", body=None, key="secret123"):
    return {
        "rawPath": path,
        "requestContext": {"http": {"method": method}},
        "headers": {"x-access-key": key} if key else {},
        "body": json.dumps(body) if body is not None else None,
    }


def test_serves_chat_page(api):
    res = api.lambda_handler(event("GET", "/", key=None), None)
    assert res["statusCode"] == 200 and "Restaurant AI Analyst" in res["body"]


def test_rejects_wrong_key(api):
    res = api.lambda_handler(event(body={"question": "sales?"}, key="nope"), None)
    assert res["statusCode"] == 401


def test_rejects_empty_and_long_questions(api):
    assert api.lambda_handler(event(body={"question": ""}), None)["statusCode"] == 400
    assert api.lambda_handler(event(body={"question": "x" * 501}), None)["statusCode"] == 400


def test_answers_and_writes_audit_log(api):
    res = api.lambda_handler(event(body={"question": "What were sales in March?"}), None)
    body = json.loads(res["body"])

    assert res["statusCode"] == 200 and "12,345.67" in body["answer"]
    item = boto3.resource("dynamodb").Table(TABLE).get_item(Key={"id": body["id"]})["Item"]
    assert item["question"] == "What were sales in March?"
    assert json.loads(item["queries"])[0]["sql"] == "SELECT 1"
