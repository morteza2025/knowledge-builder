# ADR-002: Knowledge Graph & Multi-Book Semantic Memory Roadmap

## Status
Partially implemented. `ConceptRelationExtractorPort` has a real, working
adapter (Anthropic Claude, tool use) as of the concept-extraction feature
added July 2026 — see "Implemented now" below. `ConceptMergePort`
(cross-book canonical merging) is still just the seam, no adapter yet.

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

### Extraction and merge logic

**Implemented now:** `app/infrastructure/llm/anthropic_concept_extractor.py`
implements `ConceptRelationExtractorPort` using the Anthropic Claude API
(tool use / forced function-calling, not "ask the model to return JSON in
prose" — guaranteed schema-shaped output, no parsing fragility). It
operates on one `LessonTextExtract` at a time — see
`app/application/use_cases/build_lesson_extracts.py` for how lesson
boundaries are resolved from the outline (ADR itself unchanged: a whole
book is too large for one LLM call, a raw page is too small to capture a
lesson's concepts). Wired into the main pipeline as an opt-in stage
(`ExtractConceptsStage` / `ProcessingContext.extract_concepts`) — off by
default, since unlike every other stage this involves real API cost and
latency. Constructing the adapter never requires an API key; only calling
`.extract()` does, raising `ConceptExtractionNotConfiguredError` (defined
in `app/core/exceptions.py`, not the infrastructure module, so the
application layer can catch it without an infrastructure import) — the
pipeline stage catches this once per book (not once per lesson) and
degrades gracefully rather than failing the whole run. See README.md
"Concept extraction (Knowledge Graph)" for setup and usage.

Concept ids produced this way are lesson-scoped
(`lesson-3:social-action`), not canonical — this is intentional and
honest: nothing here claims cross-lesson or cross-book deduplication it
doesn't actually do yet. That's `ConceptMergePort`'s job.

**Not implemented yet:** `ConceptMergePort` — given a candidate concept and
the existing graph, decide whether it matches an existing canonical
concept (Semantic Memory: "Society" from Book A and Book B should merge).
Likely a mix of embedding similarity and LLM judgment, hidden behind the
port the same way extraction is. Not implemented because there's no
honest way to validate merge logic without at least two books' worth of
real extracted concepts to test it against — extracting from a second book
is now unblocked by this feature, so this is the natural next step.

### Sequencing
1. ~~Fix text extraction (RTL correctness, OCR fallback).~~ — done.
2. ~~Implement `ConceptRelationExtractorPort` with a real LLM-backed
   adapter.~~ — done (Anthropic Claude, per-lesson). Not yet scoped down to
   "one subject, manually reviewed" as originally planned here — that
   review step is still worth doing before trusting output at scale, it
   just hasn't happened yet since API-key setup was deferred.
3. Implement `ConceptMergePort` once there are at least two books' worth of
   extracted concepts to actually test merging against.
4. Wire a `BuildKnowledgeGraphStage` that accumulates across books (today's
   `ExtractConceptsStage` produces one book's concepts/relationships per
   run, exported standalone — not yet merged into a persistent,
   cross-book-growing graph).

## Consequences
- The domain is ready to receive real graph data as soon as an extractor
  adapter exists, with no breaking model changes anticipated.
- Nothing in this rebuild fakes or hand-writes concept relationships — the
  ports exist, the implementations don't, and that gap is intentional and
  tracked here rather than hidden.
- `KnowledgeGraph` deliberately has no reference to student data anywhere in
  its definition, keeping the Student Adaptation Layer boundary enforceable
  at the type level, not just by convention.
