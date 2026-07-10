"""
Anthropic Claude-backed implementation of ConceptRelationExtractorPort.

Uses tool use (forced function-calling) rather than asking the model to
"return JSON" in prose — the response is then guaranteed to be valid,
schema-shaped data. No markdown-fence stripping, no "the model added a
sentence before the JSON" parsing fragility.

Requires ANTHROPIC_API_KEY to be set in the environment (read automatically
by the Anthropic SDK) — this is intentionally NOT checked at import or
construction time, only when .extract() is actually called, so the rest of
this pipeline keeps working perfectly well without an API key configured
at all. Model name and token limit come from settings
(concept_extraction_model / concept_extraction_max_tokens) so they can be
changed without touching this file.
"""

import os
from typing import Optional

import anthropic

from app.application.ports import ConceptRelationExtractorPort
from app.core.exceptions import ConceptExtractionNotConfiguredError
from app.core.logger import app_logger
from app.core.settings import settings
from app.domain.concept import ConceptRelationship, ConceptRelationType, EducationalConcept
from app.domain.document import LessonTextExtract, SourceRef


# Re-exported for convenience/backward compatibility — the canonical
# definition lives in app.core.exceptions so the application layer can
# catch it without importing anything infrastructure-specific.
__all__ = ["AnthropicConceptExtractor", "ConceptExtractionNotConfiguredError"]


_TOOL_SCHEMA = {
    "name": "record_lesson_concepts",
    "description": (
        "Record the educational concepts and relationships between them "
        "found in this lesson's text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "concepts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": (
                                "Short, stable, slug-like id in English "
                                "(e.g. 'social-action'). Used to link "
                                "relationships below — must be unique "
                                "within this response."
                            ),
                        },
                        "title": {
                            "type": "string",
                            "description": "Concept name, in the lesson's own language.",
                        },
                        "definition": {"type": "string"},
                        "explanation": {"type": "string"},
                        "examples": {"type": "array", "items": {"type": "string"}},
                        "common_misconceptions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "confidence_score": {
                            "type": "number",
                            "description": (
                                "0.0-1.0: how clearly this concept is "
                                "actually taught in this text vs. loosely "
                                "inferred."
                            ),
                        },
                    },
                    "required": ["id", "title"],
                },
            },
            "relationships": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_concept_id": {"type": "string"},
                        "target_concept_id": {"type": "string"},
                        "relation_type": {
                            "type": "string",
                            "enum": [t.value for t in ConceptRelationType],
                        },
                        "notes": {"type": "string"},
                    },
                    "required": [
                        "source_concept_id",
                        "target_concept_id",
                        "relation_type",
                    ],
                },
            },
        },
        "required": ["concepts", "relationships"],
    },
}

_SYSTEM_PROMPT = (
    "You are analyzing one lesson from a Persian-language school textbook "
    "to build a structured knowledge graph for an adaptive learning "
    "platform. Extract the concepts actually taught in this lesson — not "
    "generic background knowledge about the subject — and the "
    "relationships between them (prerequisite, depends_on, parent, child, "
    "related, similar, opposite, frequently_confused). Write concept "
    "titles/definitions/explanations in the same language as the source "
    "text. Only record a relationship between two concepts that are BOTH "
    "in your concepts list. Be conservative: it is better to extract "
    "fewer, clearly-supported concepts than to pad the list with loosely "
    "related ideas."
)


def _build_user_message(lesson: LessonTextExtract) -> str:
    header_lines = [f"کتاب: {lesson.book_title}"]
    if lesson.course:
        header_lines.append(f"درس/رشته: {lesson.course}")
    if lesson.grade:
        header_lines.append(f"پایه: {lesson.grade}")
    header_lines.append(f"فصل: {lesson.chapter_title}")
    header_lines.append(f"عنوان درس: {lesson.lesson_title}")

    header = "\n".join(header_lines)
    return f"{header}\n\n---\n\n{lesson.text}"


class AnthropicConceptExtractor(ConceptRelationExtractorPort):
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        client: Optional[anthropic.Anthropic] = None,
    ):
        # Stored, not resolved into a client yet — see _get_client().
        # Constructing this adapter must never fail just because no key is
        # configured; only .extract() should. Passing `client` directly
        # (e.g. a test double) bypasses the API-key check entirely.
        self._api_key = api_key or settings.anthropic_api_key
        self._model = model or settings.concept_extraction_model
        self._max_tokens = max_tokens or settings.concept_extraction_max_tokens
        self._client = client

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is not None:
            return self._client

        if not self._api_key and not os.environ.get("ANTHROPIC_API_KEY"):
            raise ConceptExtractionNotConfiguredError(
                "Concept extraction requires an Anthropic API key. Set the "
                "ANTHROPIC_API_KEY environment variable (or "
                "settings.anthropic_api_key / a .env entry) and try again. "
                "Every other part of this pipeline works without one."
            )

        # api_key=None here is fine and intentional: the SDK falls back to
        # the ANTHROPIC_API_KEY env var itself when not given explicitly.
        self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def extract(
        self, lesson: LessonTextExtract
    ) -> tuple[list[EducationalConcept], list[ConceptRelationship]]:
        client = self._get_client()

        response = client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_message(lesson)}],
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "record_lesson_concepts"},
        )

        tool_use = next(
            (block for block in response.content if block.type == "tool_use"), None
        )
        if tool_use is None:
            app_logger.warning(
                "Concept extraction: no tool_use block in response for lesson %s",
                lesson.lesson_order,
            )
            return [], []

        return self._parse_tool_input(tool_use.input, lesson)

    @staticmethod
    def _parse_tool_input(
        data: dict, lesson: LessonTextExtract
    ) -> tuple[list[EducationalConcept], list[ConceptRelationship]]:
        # Concept ids from the model are lesson-scoped slugs (e.g.
        # "social-action"). Prefixed with the lesson order to guarantee
        # uniqueness across the whole book — cross-lesson/cross-book
        # canonical merging is ConceptMergePort's job (not implemented
        # yet, see ADR-002), so these ids are intentionally NOT canonical
        # yet, just internally consistent for this one extraction run.
        source_refs = [
            SourceRef(filename=ref.filename, page=ref.page)
            for ref in lesson.source_refs
        ] or [SourceRef(filename=lesson.book_title, page=lesson.start_page)]

        raw_concept_ids: set[str] = set()
        concepts: list[EducationalConcept] = []

        for raw in data.get("concepts", []) or []:
            raw_id = raw.get("id")
            title = raw.get("title")
            if not raw_id or not title:
                continue

            raw_concept_ids.add(raw_id)
            concepts.append(
                EducationalConcept(
                    id=f"lesson-{lesson.lesson_order}:{raw_id}",
                    title=title,
                    definition=raw.get("definition"),
                    explanation=raw.get("explanation"),
                    examples=list(raw.get("examples") or []),
                    common_misconceptions=list(
                        raw.get("common_misconceptions") or []
                    ),
                    confidence_score=float(raw.get("confidence_score") or 0.7),
                    source_refs=source_refs,
                )
            )

        relationships: list[ConceptRelationship] = []
        for index, raw in enumerate(data.get("relationships", []) or [], start=1):
            source_id = raw.get("source_concept_id")
            target_id = raw.get("target_concept_id")
            relation_type_raw = raw.get("relation_type")

            if (
                not source_id
                or not target_id
                or source_id not in raw_concept_ids
                or target_id not in raw_concept_ids
            ):
                continue

            try:
                relation_type = ConceptRelationType(relation_type_raw)
            except ValueError:
                continue

            relationships.append(
                ConceptRelationship(
                    id=f"lesson-{lesson.lesson_order}:rel-{index}",
                    source_concept_id=f"lesson-{lesson.lesson_order}:{source_id}",
                    target_concept_id=f"lesson-{lesson.lesson_order}:{target_id}",
                    relation_type=relation_type,
                    source_refs=source_refs,
                    notes=raw.get("notes"),
                )
            )

        return concepts, relationships
