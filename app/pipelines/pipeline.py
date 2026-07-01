from typing import Any

from app.core.logger import app_logger
from app.core.exceptions import PipelineStageError
from app.pipelines.stage import PipelineStage


class Pipeline:
    def init(self, stages: list[PipelineStage]):
        self.stages = stages

    def run(self, initial_data: Any) -> Any:
        data = initial_data

        for stage in self.stages:
            stage_name = getattr(stage, "name", stage.class.name)
            app_logger.info(f"Running pipeline stage: {stage_name}")

            try:
                data = stage.run(data)
            except Exception as exc:
                app_logger.exception(f"Pipeline stage failed: {stage_name}")
                raise PipelineStageError(f"Stage failed: {stage_name}") from exc

        return data