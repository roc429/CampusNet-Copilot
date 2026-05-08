"""启动 Campus-Tool MCP Server。"""

from __future__ import annotations

import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from mcp_server.main import mcp, settings

if __name__ == "__main__":
    mcp.run(transport=settings.transport)  # type: ignore[arg-type]
