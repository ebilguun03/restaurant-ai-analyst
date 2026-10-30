"""The Anthropic adapter: Bedrock-shaped request in, Anthropic API call out, Bedrock-shaped reply back."""
import io
import json
import urllib.error

import boto3
import pytest
from moto import mock_aws

from agent import RUN_SQL_TOOL, ask
from anthropic_client import AnthropicClient, ModelError, from_ssm


class FakeAPI:
    """Stands in for urllib.request.urlopen and records each request body."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    def __call__(self, req, timeout=None):
        self.sent.append({"headers": dict(req.header_items()), "body": json.loads(req.data)})
        return io.BytesIO(json.dumps(self.replies.pop(0)).encode())


def tool_reply(sql):
    return {"stop_reason": "tool_use", "usage": {"input_tokens": 100, "output_tokens": 20},
            "content": [{"type": "text", "text": "Let me check."},
                        {"type": "tool_use", "id": "tu_1", "name": "run_sql", "input": {"sql": sql}}]}


def text_reply(text):
    return {"stop_reason": "end_turn", "usage": {"input_tokens": 150, "output_tokens": 30},
            "content": [{"type": "text", "text": text}]}


def test_translates_request_and_reply():
    api = FakeAPI([tool_reply("SELECT 1")])
    out = AnthropicClient("sk-test", opener=api).converse(
        modelId="claude-haiku-5-5",
        system=[{"text": "You are an analyst."}],
        messages=[{"role": "user", "content": [{"text": "Sales?"}]}],
        toolConfig={"tools": [RUN_SQL_TOOL]},
        inferenceConfig={"maxTokens": 1024, "temperature": 0},
    )
    body = api.sent[0]["body"]
    assert api.sent[0]["headers"]["X-api-key"] == "sk-test"
    assert body["model"] == "claude-haiku-5-5" and body["system"] == "You are an analyst."
    assert "temperature" not in body  # current Claude models reject it
    assert body["tools"][0]["name"] == "run_sql" and "sql" in body["tools"][0]["input_schema"]["properties"]
    assert out["stopReason"] == "tool_use"
    assert out["output"]["message"]["content"][1]["toolUse"] == {"toolUseId": "tu_1", "name": "run_sql", "input": {"sql": "SELECT 1"}}
    assert out["usage"] == {"inputTokens": 100, "outputTokens": 20}


def test_full_agent_loop_through_adapter():
    api = FakeAPI([tool_reply("SELECT SUM(net_sales) FROM monthly_summary"), text_reply("March was $12,345.67.")])
    client = AnthropicClient("sk-test", opener=api)
    out = ask("March sales?", client, "claude-haiku-5-5",
              run_sql=lambda sql: {"columns": ["net"], "rows": [["12345.67"]]})

    assert out["answer"] == "March was $12,345.67."
    # The second request carries the tool result back as an Anthropic tool_result block.
    result_block = api.sent[1]["body"]["messages"][-1]["content"][0]
    assert result_block["type"] == "tool_result" and result_block["tool_use_id"] == "tu_1"
    assert "12345.67" in result_block["content"] and result_block["is_error"] is False


def test_api_error_is_raised_clearly():
    def failing(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error":"bad key"}'))

    with pytest.raises(ModelError, match="401"):
        AnthropicClient("bad", opener=failing).converse(modelId="m", messages=[{"role": "user", "content": [{"text": "hi"}]}])


def test_reads_key_from_ssm(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    with mock_aws():
        boto3.client("ssm").put_parameter(Name="/test/anthropic-key", Value="sk-from-ssm", Type="SecureString")
        assert from_ssm("/test/anthropic-key").api_key == "sk-from-ssm"
