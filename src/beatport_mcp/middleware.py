"""FastMCP middleware for the Beatport server.

``TimingMiddleware`` logs each tool call's wall-clock duration at debug level —
lightweight observability that composes with FastMCP's middleware chain.
(Error messages are made user-friendly at their source in ``client.py``, since
FastMCP resolves a tool's exception into its own ToolError below the middleware
layer.)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

logger = logging.getLogger("beatport_mcp")


class TimingMiddleware(Middleware):
    """Log each tool call's wall-clock duration at debug level."""

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:
        start = time.perf_counter()
        try:
            return await call_next(context)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            name = getattr(context.message, "name", "?")
            logger.debug("tool %s took %.0f ms", name, elapsed_ms)
