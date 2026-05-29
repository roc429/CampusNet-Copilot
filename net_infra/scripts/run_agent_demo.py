"""运行 Telemetry -> Diagnosis -> Reporting三智能体Demo。"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import suppress

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 调试模式下直接暴露 LLM 异常，避免 fallback 掩盖根因。
os.environ.setdefault("LLM_STRICT", "true")
for proxy_key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(proxy_key, None)

from app.agents.diagnosis_agent import DiagnosisAgent
from app.agents.reporting_agent import ReportingAgent
from app.agents.telemetry_agent import TelemetryAgent
from app.schemas import AnomalyEvent, DiagnosisResult, OpsReport


async def main() -> None:
    """启动三智能体并等待最终运维简报。"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    anomaly_queue: asyncio.Queue[AnomalyEvent] = asyncio.Queue()
    diagnosis_queue: asyncio.Queue[DiagnosisResult] = asyncio.Queue()
    report_queue: asyncio.Queue[OpsReport] = asyncio.Queue()

    telemetry_agent = TelemetryAgent(
        anomaly_queue=anomaly_queue,
        interval_seconds=1,
    )
    diagnosis_agent = DiagnosisAgent(
        anomaly_queue=anomaly_queue,
        diagnosis_queue=diagnosis_queue,
    )
    reporting_agent = ReportingAgent(
        diagnosis_queue=diagnosis_queue,
        report_queue=report_queue,
    )

    tasks = [
        asyncio.create_task(telemetry_agent.run(), name="telemetry-agent-demo"),
        asyncio.create_task(diagnosis_agent.run(), name="diagnosis-agent-demo"),
        asyncio.create_task(reporting_agent.run(), name="reporting-agent-demo"),
    ]

    try:
        report = await asyncio.wait_for(report_queue.get(), timeout=180)
    except TimeoutError as exc:
        failed = [task for task in tasks if task.done() and task.exception() is not None]
        if failed:
            details = ", ".join(f"{task.get_name()}: {task.exception()}" for task in failed)
            raise RuntimeError(f"流水线任务异常退出：{details}") from exc
        raise RuntimeError("180秒内未收到运维报告,可能是遥测未触发异常或下游链路阻塞。") from exc
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task

    print("===== Ops Report (Telemetry -> Diagnosis -> Reporting) =====")
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
