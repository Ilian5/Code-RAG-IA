"""MCP server for the tech-news aggregator. Streamable HTTP transport.

Exposed at https://mcp.leoharlay.dev via Caddy (Basic Auth in front).
The MCP protocol endpoint is at /mcp.
"""

import contextlib

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from tools import register_all


mcp = FastMCP("tech-news")
register_all(mcp)

# The MCP session manager's lifespan must run; we forward it through the outer app.
mcp_app = mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def lifespan(_app):
    async with mcp.session_manager.run():
        yield


async def health(_request):
    return JSONResponse({"status": "ok", "name": "tech-news-mcp"})


app = Starlette(
    routes=[
        Route("/health", health),
        Mount("/", app=mcp_app),
    ],
    lifespan=lifespan,
)
