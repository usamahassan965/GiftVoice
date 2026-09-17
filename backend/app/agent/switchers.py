"""Service switchers that let Pipecat's flush probe finish its round trip.

A ParallelPipeline (which every ServiceSwitcher is) lets each frame id out only once. The flush
probe used before injecting typed text passes through three times with the same id (down, back up,
down again), so the switcher swallowed its return legs and every typed message waited forever.
"""

from pipecat.frames.frames import Frame, PipelineFlushFrame
from pipecat.pipeline.llm_switcher import LLMSwitcher
from pipecat.pipeline.service_switcher import ServiceSwitcher
from pipecat.processors.frame_processor import FrameDirection


class FlushProbeMixin:
    async def _parallel_push_frame(self, frame: Frame, direction: FrameDirection):
        if not isinstance(frame, PipelineFlushFrame):
            return await super()._parallel_push_frame(frame, direction)
        leg = (frame.id, direction, frame.returning)
        if leg not in self._seen_ids:
            self._seen_ids.add(leg)
            if self._synchronizing:
                self._buffered_frames.append((frame, direction))
            else:
                await self.push_frame(frame, direction)


class FlushSafeServiceSwitcher(FlushProbeMixin, ServiceSwitcher):
    pass


class FlushSafeLLMSwitcher(FlushProbeMixin, LLMSwitcher):
    pass
