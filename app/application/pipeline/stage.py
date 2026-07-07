"""
Generic pipeline stage abstraction.

Today's pipeline is just Extract -> Build -> Export. The point of modeling it
as named stages over a shared, mutable context (rather than one function that
does everything) is that future stages — concept extraction, relationship
inference, semantic-memory merging — slot in the same way, without changing
how earlier stages work. See docs/architecture/ADR-002-knowledge-graph-roadmap.md.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

ContextT = TypeVar("ContextT")


class PipelineStage(ABC, Generic[ContextT]):
    name: str = "unnamed_stage"

    @abstractmethod
    def run(self, context: ContextT) -> ContextT:
        ...
