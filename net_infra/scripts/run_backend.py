"""启动所有后端服务。"""

from __future__ import annotations

import os
import sys

import uvicorn

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


if __name__ == "__main__":
    uvicorn.run("app.app:app", host="0.0.0.0", port=8080, reload=False)
