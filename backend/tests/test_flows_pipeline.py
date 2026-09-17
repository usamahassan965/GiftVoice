"""Flows wiring (which tools each specialist sees, transitions) and the per-turn latency observer."""

import asyncio
from types import SimpleNamespace

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)

from app.agent import flows
from app.agent.pipeline import LatencyObserver
from app.agent.tools import TOOLS
from tests.test_tools_conversation import make_ctx


def names(node) -> set[str]:
    return {f.name for f in node["functions"]}


def test_every_node_tool_exists():
    for stage, tools in flows.NODE_TOOLS.items():
        assert set(tools) <= set(TOOLS), stage
    assert set(flows.GLOBAL_TOOLS) <= set(TOOLS)


def test_nodes_expose_their_tools_and_other_transitions():
    ctx, _ = make_ctx()
    gift_flows = flows.GiftFlows(ctx)
    for stage in flows.NODE_TOOLS:
        node = gift_flows.node(stage)
        own_transition = flows.TRANSITIONS[stage][0]
        others = {flows.TRANSITIONS[t][0] for t in flows.TRANSITIONS if t != stage}
        assert names(node) == set(flows.NODE_TOOLS[stage]) | others
        assert own_transition not in names(node)
        assert node["role_message"]
    # Payment link only from checkout; returns only from after-sales.
    assert "create_checkout" not in names(gift_flows.node("gift_concierge"))
    assert "start_return" in names(gift_flows.node("after_sales"))


def test_transition_emits_stage_and_returns_next_node():
    ctx, events = make_ctx()
    gift_flows = flows.GiftFlows(ctx)
    node = gift_flows.initial_node()
    go = next(f for f in node["functions"] if f.name == "go_to_checkout")
    result, next_node = asyncio.run(go.handler({"reason": "ready to pay"}, None))
    assert result["now_handling"] == "checkout"
    assert next_node["name"] == "checkout"
    assert gift_flows.stage == "checkout"
    assert ("agent_stage", {"stage": "checkout"}) in events


def test_tool_schema_runs_shared_handler():
    ctx, events = make_ctx()
    schema = flows.tool_schema(ctx, "view_cart")
    result = asyncio.run(schema.handler({}, None))
    assert result["items"] == [] and result["total"] == 0
    assert any(name == "cart_updated" for name, _ in events)


def test_parallel_tool_calls_prompt_one_reply():
    ctx, _ = make_ctx()
    gift_flows = flows.GiftFlows(ctx)
    schema = flows.tool_schema(ctx, "view_cart", gift_flows.settle_call)
    gift_flows.calls_started(2)
    first = asyncio.run(schema.handler({}, None))
    last = asyncio.run(schema.handler({}, None))
    assert first[1] is flows.NO_RESPONSE  # the LLM waits for the rest of the batch
    assert last[1] is None  # the final result prompts the single reply


def test_latency_observer_reports_turn(monkeypatch):
    sent = []

    async def send(event, payload):
        sent.append((event, payload))

    clock = iter([0.0, 1.0, 1.3, 1.5, 2.0, 2.2, 2.4])
    monkeypatch.setattr("app.agent.pipeline.time", SimpleNamespace(monotonic=lambda: next(clock)))
    observer = LatencyObserver(send)
    frames = [
        VADUserStartedSpeakingFrame(),
        VADUserStoppedSpeakingFrame(),                     # 1.0 speech ends
        TranscriptionFrame(text="hi", user_id="u", timestamp=""),  # 1.3
        LLMFullResponseStartFrame(),                       # 1.5
        LLMTextFrame(text="Hello"),                        # 2.0
        TTSAudioRawFrame(audio=b"\0\0", sample_rate=24000, num_channels=1),  # 2.2
        BotStartedSpeakingFrame(),                         # 2.4
    ]

    async def push_all():
        for frame in frames:
            await observer.on_push_frame(SimpleNamespace(frame=frame))
            await observer.on_push_frame(SimpleNamespace(frame=frame))  # same frame seen by the next processor

    asyncio.run(push_all())
    assert sent == [("latency", {"stt_ms": 300, "llm_ttfb_ms": 500, "tts_ttfb_ms": 200, "total_ms": 1400})]
