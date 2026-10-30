"""Tests the agent loop with a scripted fake model, so no Bedrock or Athena calls are made."""
from agent import MAX_TOOL_CALLS, ask


class FakeBedrock:
    """Plays back a list of model turns and records what it was sent."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})  # snapshot; the list keeps growing
        return self.turns.pop(0)


def tool_turn(sql, tid="t1"):
    return {
        "stopReason": "tool_use",
        "usage": {"inputTokens": 100, "outputTokens": 20},
        "output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": tid, "name": "run_sql", "input": {"sql": sql}}}]}},
    }


def text_turn(text):
    return {
        "stopReason": "end_turn",
        "usage": {"inputTokens": 150, "outputTokens": 30},
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
    }


def fake_sql(sql):
    return {"columns": ["net"], "rows": [["12345.67"]], "athena_ms": 400}


def test_runs_query_then_answers():
    bedrock = FakeBedrock([
        tool_turn("SELECT sum(net_sales) AS net FROM fact_item_sales WHERE month = '2026-03'"),
        text_turn("March net sales were $12,345.67."),
    ])
    out = ask("What were sales in March?", bedrock, "model", run_sql=fake_sql)

    assert out["answer"] == "March net sales were $12,345.67."
    assert len(out["queries"]) == 1 and out["queries"][0]["rows"] == 1
    assert out["input_tokens"] == 250 and out["output_tokens"] == 50
    tool_result = bedrock.calls[1]["messages"][-1]["content"][0]["toolResult"]
    assert tool_result["status"] == "success"
    assert tool_result["content"][0]["json"]["rows"] == [["12345.67"]]


def test_unsafe_sql_is_blocked_and_reported_back_to_model():
    ran = []
    bedrock = FakeBedrock([tool_turn("DELETE FROM fact_item_sales"), text_turn("I can only read data.")])
    out = ask("Delete everything", bedrock, "model", run_sql=lambda s: ran.append(s))

    assert ran == []  # nothing reached Athena
    assert "Only SELECT" in out["queries"][0]["error"]
    assert bedrock.calls[1]["messages"][-1]["content"][0]["toolResult"]["status"] == "error"


def test_stops_after_max_tool_calls():
    turns = [tool_turn("SELECT 1 FROM fact_item_sales", f"t{i}") for i in range(MAX_TOOL_CALLS + 1)]
    out = ask("Loop forever", FakeBedrock(turns), "model", run_sql=fake_sql)

    assert len(out["queries"]) == MAX_TOOL_CALLS
    assert "query limit" in out["answer"]


def test_answers_directly_without_queries():
    out = ask("Hi", FakeBedrock([text_turn("Ask me about sales.")]), "model", run_sql=fake_sql)
    assert out["answer"] == "Ask me about sales." and out["queries"] == []
