"""Live voice sessions, so REST endpoints (photo upload) can reach the agent's ToolContext."""

from typing import Any

from app.agent.tools import ToolContext

_contexts: dict[str, ToolContext] = {}
_pending_images: dict[str, Any] = {}


def register(ctx: ToolContext) -> None:
    _contexts[ctx.session_id] = ctx
    if ctx.session_id in _pending_images:
        ctx.uploaded_image = _pending_images.pop(ctx.session_id)


def unregister(session_id: str) -> None:
    _contexts.pop(session_id, None)
    _pending_images.pop(session_id, None)


def set_uploaded_image(session_id: str, image: Any) -> None:
    ctx = _contexts.get(session_id)
    if ctx:
        ctx.uploaded_image = image
    else:
        _pending_images[session_id] = image
