# ADR-002: Knowledge Graph & Multi-Book Semantic Memory Roadmap

## Status
Accepted (roadmap) — domain models in place, extraction/merge logic not yet
implemented.

## Context
Knowledge Builder must eventually become more than a per-book PDF-to-text
pipeline. The long-term vision (see project roadmap discussion, July 2026)
requires:

1. **Knowledge Graph** — concepts carry semantic relationships to each other
   (prerequisite, depends-on, parent/child, related, similar, opposite,
   frequently-confused), not just isolated definitions.
2. **Student Adaptation Layer** — personalization happens *outside* Knowledge
   Builder, consuming its canonical output. Knowledge Builder must never
   become aware of student-specific data.
3. **Semantic Memory** — the same concept found in multiple books (e.g.
   "Society" in Book A and Book B) merges into one canonical
   `EducationalConcept`, not duplicate records.
4. **Multi-Book Knowledge** — output represents *concepts*, aggregated across
   textbooks, supplementary books, teacher notes, and articles — not
   isolated per-book documents.
5. **Educational Reasoning** — future AI services (gap detection, revision
   strategy, learning-path generation) reason over structured knowledge, not
   raw text.

## Decision

### Domain models (implemented now)
- `app/domain/concept.py` defines `EducationalConcept`, `ConceptRelationship`,
  `ConceptRelationType`, and `KnowledgeGraph`. A `KnowledgeGraph` is a
  separate aggregate from `KnowledgeDocument`: one `KnowledgeDocument` is
  produced per source PDF, but many `KnowledgeDocument`s feed into a single,
  growing `KnowledgeGraph` over time (Multi-Book Knowledge).
- Every `EducationalConcept` and `ConceptRelationship` carries
  `confidence_score`, `version`, and `source_refs` — Design Principles #9
  (Versioned Knowledge) and #10 (Source Traceability) are non-negotiable,
  not optional metadata bolted on later.
- Relationships are first-class edge objects (not string lists on
  `EducationalConcept`) so each edge can have its own confidence, source, and
  be queried from either direction (`KnowledgeGraph.relationships_for`).

### Extraction and merge logic (NOT implemented yet — this is the roadmap)
Two application-level ports are defined in `app/application/ports.py` as the
seams for future work:

- `ConceptRelationExtractorPort` — given a `KnowledgeDocument`, propose
  `EducationalConcept`s and `ConceptRelationship`s. This is almost certainly
  LLM-assisted (an LLM reading extracted text and proposing "Derivative
  requires Limit"). The port exists precisely so the domain and application
  layers never import an LLM SDK directly — Design Principle #4 (LLM
  Independent).
- `ConceptMergePort` — given a candidate concept and the existing graph,
  decide whether it matches an existing canonical concept (Semantic Memory).
  Likely a mix of embedding similarity and LLM judgment, again hidden behind
  the port.

**Why not implement these now:** both require real inference over real
educational content (an LLM call, or a trained similarity model) — there is
no honest way to stub this out with placeholder logic without producing a
knowledge graph that looks structured but is actually meaningless. Building
on top of unverified concept-relationships would be worse than not having
them, especially while the underlying text-extraction quality was itself
still being fixed (see ADR-001 follow-up: the RTL word/character-order bug).

### Sequencing
1. ~~Fix text extraction (RTL correctness, OCR fallback).~~ — done, this
   rebuild.
2. Implement `ConceptRelationExtractorPort` with a real LLM-backed adapter,
   scoped initially to a single subject (e.g. one grade's sociology book) so
   output quality can be manually reviewed before scaling up.
3. Implement `ConceptMergePort` once there are at least two books' worth of
   extracted concepts to actually test merging against.
4. Only after both are validated: wire a `BuildKnowledgeGraphStage` into the
   pipeline (see `app/application/pipeline/`) so graph construction becomes
   part of the standard per-book run, not a separate offline script.

## Consequences
- The domain is ready to receive real graph data as soon as an extractor
  adapter exists, with no breaking model changes anticipated.
- Nothing in this rebuild fakes or hand-writes concept relationships — the
  ports exist, the implementations don't, and that gap is intentional and
  tracked here rather than hidden.
- `KnowledgeGraph` deliberately has no reference to student data anywhere in
  its definition, keeping the Student Adaptation Layer boundary enforceable
  at the type level, not just by convention.
