"""Call Claude through Anthropic's own API, shaped like Bedrock's Converse API.

Why this exists: the agent loop (agent.py) talks to the model with Bedrock's
`converse(...)` call. This class offers the same `converse(...)` method but sends the
request to api.anthropic.com instead. So the agent, its tests and its audit log stay
exactly the same, and switching providers is one setting (MODEL_PROVIDER).

Think of it as a travel plug adapter: same device, different wall socket.

No extra packages: it uses Python's built-in urllib, so the Lambda zip stays tiny.
The API key is read once from SSM Parameter Store (encrypted), never from code or git.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class ModelError(RuntimeError):
    pass


def _to_anthropic_block(block: dict) -> dict:
    if "text" in block:
        return {"type": "text", "text": block["text"]}
    if "toolUse" in block:
        t = block["toolUse"]
        return {"type": "tool_use", "id": t["toolUseId"], "name": t["name"], "input": t["input"]}
    if "toolResult" in block:
        r = block["toolResult"]
        parts = [json.dumps(c["json"]) if "json" in c else c.get("text", "") for c in r["content"]]
        return {"type": "tool_result", "tool_use_id": r["toolUseId"], "content": "\n".join(parts),
                "is_error": r.get("status") == "error"}
    raise ValueError(f"Unsupported content block: {list(block)}")


def _to_bedrock_block(block: dict) -> dict | None:
    if block["type"] == "text":
        return {"text": block["text"]}
    if block["type"] == "tool_use":
        return {"toolUse": {"toolUseId": block["id"], "name": block["name"], "input": block["input"]}}
    return None  # e.g. thinking blocks: not used by this agent


class AnthropicClient:
    def __init__(self, api_key: str, opener=urllib.request.urlopen, timeout: float = 60.0):
        self.api_key = api_key
        self.opener = opener
        self.timeout = timeout

    def converse(self, modelId, messages, system=None, toolConfig=None, inferenceConfig=None):
        inference = inferenceConfig or {}
        body = {
            "model": modelId,
            "max_tokens": inference.get("maxTokens", 1024),
            "messages": [
                {"role": m["role"], "content": [_to_anthropic_block(b) for b in m["content"]]}
                for m in messages
            ],
        }
        # Not forwarded: `temperature`. Current Claude models reject it (400 "temperature is
        # deprecated for this model"). Accuracy is guarded by the SQL tool + eval set instead.
        if system:
            body["system"] = "\n\n".join(s["text"] for s in system)
        if toolConfig:
            body["tools"] = [
                {"name": t["toolSpec"]["name"], "description": t["toolSpec"]["description"],
                 "input_schema": t["toolSpec"]["inputSchema"]["json"]}
                for t in toolConfig["tools"]
            ]

        req = urllib.request.Request(
            API_URL, data=json.dumps(body).encode(), method="POST",
            headers={"content-type": "application/json", "x-api-key": self.api_key,
                     "anthropic-version": API_VERSION},
        )
        try:
            with self.opener(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            raise ModelError(f"Anthropic API returned {exc.code}: {detail}") from exc

        content = [b for b in (_to_bedrock_block(x) for x in data.get("content", [])) if b]
        usage = data.get("usage", {})
        return {
            "stopReason": data.get("stop_reason"),
            "usage": {"inputTokens": usage.get("input_tokens", 0), "outputTokens": usage.get("output_tokens", 0)},
            "output": {"message": {"role": "assistant", "content": content}},
        }


def from_ssm(parameter_name: str, ssm=None) -> AnthropicClient:
    import boto3

    ssm = ssm or boto3.client("ssm")
    key = ssm.get_parameter(Name=parameter_name, WithDecryption=True)["Parameter"]["Value"]
    return AnthropicClient(key)
