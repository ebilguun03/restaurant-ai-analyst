"""End-to-end test of the Lambda against fake AWS (moto), no real account needed."""
import importlib
import json

import boto3
import pytest
from moto import mock_aws

from conftest import build_export

RAW, CURATED, TABLE = "raw-test", "curated-test", "ledger-test"


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.setenv("CURATED_BUCKET", CURATED)
    monkeypatch.setenv("LEDGER_TABLE", TABLE)
    with mock_aws():
        s3 = boto3.client("s3")
        for bucket in (RAW, CURATED):
            s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
        boto3.client("dynamodb").create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "file_etag", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "file_etag", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        import handler
        importlib.reload(handler)  # pick up the mocked clients and env vars
        yield s3, handler


def _event(key):
    return {"Records": [{"s3": {"bucket": {"name": RAW}, "object": {"key": key}}}]}


def test_processes_file_into_curated_partition(aws):
    s3, handler = aws
    key = "toast/product_mix/ProductMix_2026-01-01_2026-01-28.xlsx"
    s3.put_object(Bucket=RAW, Key=key, Body=build_export())

    out = handler.lambda_handler(_event(key), None)["results"][0]

    assert out["status"] == "processed"
    body = s3.get_object(Bucket=CURATED, Key="fact_item_sales/month=2026-01/test-izakaya.jsonl")["Body"].read()
    rows = [json.loads(line) for line in body.decode().splitlines()]
    assert len(rows) == 5


def test_same_file_twice_is_skipped(aws):
    s3, handler = aws
    key = "toast/product_mix/ProductMix_2026-01-01_2026-01-28.xlsx"
    s3.put_object(Bucket=RAW, Key=key, Body=build_export())

    handler.lambda_handler(_event(key), None)
    second = handler.lambda_handler(_event(key), None)["results"][0]

    assert second["status"] == "skipped_duplicate"
    listing = s3.list_objects_v2(Bucket=CURATED)["Contents"]
    assert len(listing) == 1  # still exactly one file for the month


def test_bad_file_is_rejected_not_crashed(aws):
    s3, handler = aws
    key = "toast/product_mix/broken.xlsx"
    s3.put_object(Bucket=RAW, Key=key, Body=b"not excel")

    out = handler.lambda_handler(_event(key), None)["results"][0]

    assert out["status"] == "rejected"
    assert "Contents" not in s3.list_objects_v2(Bucket=CURATED)
