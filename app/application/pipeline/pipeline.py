from dataclasses import dataclass, field
from typing import Generic, TypeVar

from app.application.pipeline.stage import PipelineStage
from app.core.logger import app_logger

ContextT = TypeVar("ContextT")


@dataclass
class Pipeline(Generic[ContextT]):
    stages: list[PipelineStage[ContextT]] = field(default_factory=list)

    def add(self, stage: PipelineStage[ContextT]) -> "Pipeline[ContextT]":
        self.stages.append(stage)
        return self

    def run(self, context: ContextT) -> ContextT:
        for stage in self.stages:
            app_logger.info("Running pipeline stage: %s", stage.name)
            context = stage.run(context)
        return context
