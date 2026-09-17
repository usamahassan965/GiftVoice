"""Pipecat Flows: specialist agent nodes sharing one conversation.

gift_concierge  discovery, recommendations, bundles, photo search, recipient memory
checkout        cart, gift wrap/message, delivery timing, confirmation and payment link
after_sales     order tracking, returns, escalation

Product-expert duties live in the concierge node so a follow-up question about a
product never pays for a handoff. Tools are the same handlers the tests exercise
(app.agent.tools); Flows only decides which ones each node can see.
"""

from collections.abc import Callable

from pipecat.flows import NO_RESPONSE, FlowManager, FlowsFunctionSchema, NodeConfig

from app.agent import prompts
from app.agent.tools import TOOLS, ToolContext, run_tool

GLOBAL_TOOLS = ["view_cart", "set_language", "note_mood", "escalate_to_human"]

NODE_TOOLS = {
    "gift_concierge": ["search_products", "get_product", "compare_products", "show_products", "image_search",
                       "build_bundle", "add_to_cart", "remove_from_cart", "check_delivery",
                       "get_recipient_profiles", "save_recipient_profile"],
    "checkout": ["set_gift_options", "add_to_cart", "remove_from_cart", "check_delivery", "create_checkout",
                 "show_products", "get_product", "get_recipient_profiles", "save_recipient_profile"],
    "after_sales": ["track_order", "start_return", "get_recipient_profiles", "save_recipient_profile"],
}

ROLE_PROMPTS = {
    "gift_concierge": prompts.CONCIERGE,
    "checkout": prompts.CHECKOUT,
    "after_sales": prompts.AFTER_SALES,
}

TRANSITIONS = {
    "gift_concierge": ("go_to_gift_concierge",
                       "Switch to gift discovery: the shopper wants to browse, find or swap a gift."),
    "checkout": ("go_to_checkout",
                 "Switch to checkout: the shopper has chosen gifts and wants wrap, a message, delivery or to pay."),
    "after_sales": ("go_to_after_sales",
                    "Switch to order help: tracking an existing order, a return, exchange or a problem."),
}


def tool_schema(ctx: ToolContext, name: str, settle: Callable[[], object] | None = None) -> FlowsFunctionSchema:
    """`settle` (see GiftFlows.settle_call) decides whether this result should prompt a reply."""
    tool = TOOLS[name]

    async def handler(args: dict, _flow_manager: FlowManager):
        result = await run_tool(ctx, name, args)
        return (result, settle()) if settle else result

    return FlowsFunctionSchema(name=tool.name, description=tool.description, properties=tool.properties,
                               required=tool.required, handler=handler)


class GiftFlows:
    """Builds node configs bound to one session's ToolContext."""

    def __init__(self, ctx: ToolContext):
        self.ctx = ctx
        self.stage = "gift_concierge"
        self.pending_calls = 0

    def calls_started(self, count: int) -> None:
        """Hook for the LLM's on_function_calls_started event."""
        self.pending_calls = count

    def settle_call(self):
        """Flows asks the LLM for a reply after every tool result, bypassing Pipecat's grouping of
        parallel calls, so a search plus a profile lookup produced two spoken answers. Only the
        last call of a batch prompts the reply."""
        self.pending_calls = max(0, self.pending_calls - 1)
        return NO_RESPONSE if self.pending_calls else None

    def global_functions(self) -> list[FlowsFunctionSchema]:
        return [tool_schema(self.ctx, name, self.settle_call) for name in GLOBAL_TOOLS]

    def _transition(self, target: str) -> FlowsFunctionSchema:
        name, description = TRANSITIONS[target]

        async def handler(args: dict, _flow_manager: FlowManager):
            self.settle_call()  # the new node prompts the reply itself
            self.stage = target
            await self.ctx.emit("agent_stage", {"stage": target})
            return {"now_handling": target, "reason": args.get("reason")}, self.node(target)

        return FlowsFunctionSchema(
            name=name, description=description,
            properties={"reason": {"type": "string", "description": "One short phrase"}}, required=[],
            handler=handler,
        )

    def node(self, stage: str, greet: bool = False) -> NodeConfig:
        functions = [tool_schema(self.ctx, n, self.settle_call) for n in NODE_TOOLS[stage]]
        functions += [self._transition(t) for t in TRANSITIONS if t != stage]
        if greet:
            task = prompts.GREETING_INSTRUCTION.format(store=prompts.config.STORE_NAME)
        else:
            task = ("You are now handling this part of the conversation. Continue naturally from the shopper's "
                    "last request without re-introducing yourself.")
        return NodeConfig(
            name=stage,
            role_message=f"{prompts.persona(self.ctx.now)}\n{ROLE_PROMPTS[stage]}",
            task_messages=[{"role": "developer", "content": task}],
            functions=functions,
        )

    def initial_node(self) -> NodeConfig:
        return self.node("gift_concierge", greet=True)
