"""本地启动 Agent API（:8002）。在 net_infra 目录执行: python run_agent.py"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.app:app",
        host="0.0.0.0",
        port=8002,
        reload=False,
    )
