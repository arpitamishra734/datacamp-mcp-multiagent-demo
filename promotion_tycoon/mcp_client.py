from promotion_tycoon.tracing import log_trace, log_error
from promotion_tycoon.config import TAVILY_API_KEY


MCP_CLIENT = None

try:
    from langchain_mcp_adapters.client import MultiServerMCPClient
    if TAVILY_API_KEY:
        MCP_CLIENT = MultiServerMCPClient({
            "tavily": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "tavily-mcp@0.2.4"],
                "env": {"TAVILY_API_KEY": TAVILY_API_KEY},
            }
        })
        log_trace("✅ Tavily MCP configured")
    else:
        log_trace("⚠️ Tavily API key not found - web search disabled")
except Exception as e:
    log_error("MCP Client Setup", e)
    MCP_CLIENT = None
    log_trace("⚠️ MCP unavailable")

async def get_mcp_tools():
    if not MCP_CLIENT: return []
    try:
        tools = await MCP_CLIENT.get_tools()
        log_trace("🔧 MCP tools loaded", count=len(tools) if tools else 0)
        return tools
    except Exception as e:
        log_error("Get MCP Tools", e)
        return []
