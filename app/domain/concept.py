"""
Domain models for the Knowledge Graph roadmap (see
docs/architecture/ADR-002-knowledge-graph-roadmap.md).

These models define WHAT a concept and a relationship between concepts look
like. They intentionally contain no extraction/inference logic — discovering
that "Derivative" requires "Limit" is an application-level concern (almost
certainly LLM-assisted) that lives behind the ConceptRelationExtractorPort in
app/application/ports.py. The domain stays framework- and LLM-independent
(Design Principles #3 Framework Independent, #4 LLM Independent).
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.domain.document import SourceRef


class ConceptRelationType(str, Enum):
    prerequisite = "prerequisite"
    depends_on = "depends_on"
    parent = "parent"
    child = "child"
    related = "related"
    similar = "similar"
    opposite = "opposite"
    frequently_confused = "frequently_confused"


class ConceptRelationship(BaseModel):
    """A single directed edge in the Knowledge Graph.

    Kept as its own first-class object (rather than string lists on
    EducationalConcept) so that each edge can carry its own confidence score
    and source traceability, and so the graph can be queried in either
    direction without re-deriving the inverse relationship.
    """

    id: str
    source_concept_id: str
    target_concept_id: str
    relation_type: ConceptRelationType
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    source_refs: list[SourceRef] = Field(default_factory=list)
    notes: Optional[str] = None


class EducationalConcept(BaseModel):
    """A canonical educational concept.

    'Canonical' matters: per the Semantic Memory roadmap item, the same
    concept discovered in Book A and Book B should merge into one
    EducationalConcept record with multiple source_refs, not two duplicate
    records. Merge logic is an application-level use case, not implemented
    here — this model just needs to be able to represent the merged result.
    """

    id: str
    title: str
    definition: Optional[str] = None
    explanation: Optional[str] = None
    examples: list[str] = Field(default_factory=list)
    common_misconceptions: list[str] = Field(default_factory=list)
    socratic_questions: list[str] = Field(default_factory=list)

    # Design Principle #9 (Versioned Knowledge) + #10 (Source Traceability):
    # every concept must know where it came from, what pipeline version
    # produced it, and how confident that pipeline was.
    version: int = 1
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    source_refs: list[SourceRef] = Field(default_factory=list)


class KnowledgeGraph(BaseModel):
    """A collection of concepts and the relationships between them, spanning
    however many source documents contributed to it (Multi-Book Knowledge
    roadmap item). This is deliberately a separate aggregate from
    KnowledgeDocument: one KnowledgeDocument is produced per PDF, but many
    KnowledgeDocuments feed into a single, growing KnowledgeGraph over time.
    """

    concepts: list[EducationalConcept] = Field(default_factory=list)
    relationships: list[ConceptRelationship] = Field(default_factory=list)
    version: int = 1

    def relationships_for(self, concept_id: str) -> list[ConceptRelationship]:
        """All edges touching a concept, in either direction."""
        return [
            rel
            for rel in self.relationships
            if concept_id in (rel.source_concept_id, rel.target_concept_id)
        ]

    def find_concept(self, concept_id: str) -> Optional[EducationalConcept]:
        for concept in self.concepts:
            if concept.id == concept_id:
                return concept
        return None
