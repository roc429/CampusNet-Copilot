"""TelemetryAgent:遥测异常发现智能体。"""

from __future__ import annotations

import asyncio
import logging
import random
from uuid import uuid4

from app.config import settings
from app.schemas import AnomalyEvent
from app.stores import OpsMemoryStore


class TelemetryAgent:
    """周期采集网络指标并上报异常事件。

    设计目标：
    - 与诊断、报告链路完全解耦
    - 支持高并发场景下持续生产异常事件
    """

    def __init__(
        self,
        anomaly_queue: asyncio.Queue[AnomalyEvent],
        interval_seconds: int = 5,
        store: OpsMemoryStore | None = None,
    ) -> None:
        self.anomaly_queue = anomaly_queue
        self.interval_seconds = interval_seconds
        self.store = store
        self.logger = logging.getLogger(self.__class__.__name__)

    async def run(self) -> None:
        """持续采集指标，若丢包率超过阈值则投递异常。"""

        while True:
            await asyncio.sleep(self.interval_seconds)
            if not settings.telemetry_mock_enabled:
                continue
            packet_loss = round(random.uniform(0.0, 0.12), 3)
            latency_ms = round(random.uniform(12, 280), 1)

            if packet_loss > 0.05:
                event = AnomalyEvent(
                    event_id=f"evt-{uuid4().hex[:10]}",
                    location=random.choice(["图书馆三楼", "宿舍A3二层", "教学楼B1"]),
                    issue_desc="检测到链路丢包异常，用户可能出现掉线或高延迟。",
                    packet_loss=packet_loss,
                    latency_ms=latency_ms,
                    device_hint=random.choice(["AP-EXAM-301", "AP-LIB-01"]),
                )
                if self.store is not None:
                    self.store.save_event(event)
                await self.anomaly_queue.put(event)
                self.logger.info("Telemetry anomaly enqueued event_id=%s", event.event_id)
