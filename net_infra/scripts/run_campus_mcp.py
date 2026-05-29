"""启动 Campus MCP Server (端口 9000)。"""

from __future__ import annotations

import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from mcp_servers.campus_mcp.main import mcp, settings  # noqa: E402

if __name__ == "__main__":
    mcp.run(transport=settings.transport)  # type: ignore[arg-type]
