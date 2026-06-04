"""DiagnosisAgent单独测试脚本(待完善)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.agents.diagnosis_agent import DiagnosisAgent
from app.schemas import AnomalyEvent, DiagnosisResult


async def main() -> None:
    """执行 DiagnosisAgent 真实集成测试。"""

    sys.stdout.reconfigure(encoding="utf-8")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    anomaly_queue: asyncio.Queue[AnomalyEvent] = asyncio.Queue()
    diagnosis_queue: asyncio.Queue[DiagnosisResult] = asyncio.Queue()

    agent = DiagnosisAgent(anomaly_queue=anomaly_queue, diagnosis_queue=diagnosis_queue)
    task = asyncio.create_task(agent.run(), name="diagnosis-agent-test")

    await anomaly_queue.put(
        AnomalyEvent(
            event_id="evt-integration-001",
            location="图书馆三层",
            issue_desc="三层网络掉线并伴随高丢包",
            packet_loss=0.11,
            latency_ms=188.0,
            device_hint="AP-LIB-01",
        )
    )

    try:
        result = await asyncio.wait_for(diagnosis_queue.get(), timeout=180)
    except TimeoutError as exc:
        if task.done():
            if task.cancelled():
                raise RuntimeError("DiagnosisAgent 已被取消，未产出诊断结果。") from exc
            err = task.exception()
            raise RuntimeError(f"DiagnosisAgent 提前退出，异常: {err}") from exc
        raise RuntimeError("180 秒内未收到诊断结果。") from exc
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert result.event_id == "evt-integration-001", result.model_dump_json(indent=2)
    assert isinstance(result.final_reasoning, str) and result.final_reasoning.strip(), result.model_dump_json(indent=2)

    print("DiagnosisAgent integration compatibility test passed.")
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
