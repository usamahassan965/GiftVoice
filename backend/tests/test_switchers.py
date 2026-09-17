import asyncio

import pytest
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.service_switcher import ServiceSwitcher, ServiceSwitcherStrategyFailover
from pipecat.pipeline.worker import PipelineWorker
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.workers.runner import WorkerRunner

from app.agent.switchers import FlushSafeServiceSwitcher


class Passthrough(FrameProcessor):
    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)


async def flush_through(switcher_cls) -> bool:
    switcher = switcher_cls(services=[Passthrough(), Passthrough()], strategy_type=ServiceSwitcherStrategyFailover)
    worker = PipelineWorker(Pipeline([Passthrough(), switcher, Passthrough()]), cancel_on_idle_timeout=False)
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    run = asyncio.create_task(runner.run())
    await asyncio.sleep(0.5)
    try:
        return await worker.flush_pipeline(timeout=1.0)
    finally:
        await worker.cancel()
        await run


@pytest.mark.parametrize("switcher_cls, drains", [(ServiceSwitcher, False), (FlushSafeServiceSwitcher, True)])
def test_flush_probe_survives_switcher(switcher_cls, drains):
    # Typed text waits on this flush; Pipecat's own switcher drops the probe's return trip.
    assert asyncio.run(flush_through(switcher_cls)) is drains
