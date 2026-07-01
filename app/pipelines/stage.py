from abc import ABC, abstractmethod
from typing import Generic, TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class PipelineStage(ABC, Generic[InputT, OutputT]):
    name: str

    @abstractmethod
    def run(self, data: InputT) -> OutputT:
        raise NotImplementedError