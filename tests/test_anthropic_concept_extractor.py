from dataclasses import dataclass, field
from typing import Any

import pytest

from app.core.settings import settings
from app.domain.document import LessonTextExtract, SourceRef
from app.infrastructure.llm.anthropic_concept_extractor import (
    AnthropicConceptExtractor,
    ConceptExtractionNotConfiguredError,
    _build_user_message,
)


@dataclass
class FakeToolUseBlock:
    input: dict
    type: str = "tool_use"
    name: str = "record_lesson_concepts"


@dataclass
class FakeResponse:
    content: list


class FakeMessages:
    def __init__(self, response: FakeResponse):
        self._response = response
        self.last_call_kwargs: dict[str, Any] = {}

    def create(self, **kwargs):
        self.last_call_kwargs = kwargs
        return self._response


class FakeClient:
    def __init__(self, response: FakeResponse):
        self.messages = FakeMessages(response)


def _sample_lesson() -> LessonTextExtract:
    return LessonTextExtract(
        book_title="جامعه شناسی (۱)",
        course="انسانی",
        grade="دهم",
        chapter_order=1,
        chapter_title="زندگی اجتماعی",
        lesson_order=1,
        lesson_title="کنش های ما",
        start_page=11,
        end_page=17,
        text="متن نمونه‌ی درس یک درباره‌ی کنش اجتماعی و انواع آن.",
        source_refs=[SourceRef(filename="book.pdf", page=p) for p in range(11, 18)],
    )


def test_extract_raises_when_no_api_key_and_no_client_given(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    extractor = AnthropicConceptExtractor()
    with pytest.raises(ConceptExtractionNotConfiguredError):
        extractor.extract(_sample_lesson())


def test_extract_parses_concepts_and_relationships_from_a_valid_response():
    fake_response = FakeResponse(
        content=[
            FakeToolUseBlock(
                input={
                    "concepts": [
                        {
                            "id": "social-action",
                            "title": "کنش اجتماعی",
                            "definition": "تعریف کنش اجتماعی",
                            "examples": ["مثال ۱"],
                            "common_misconceptions": ["تصور غلط ۱"],
                            "confidence_score": 0.9,
                        },
                        {"id": "meaning", "title": "معنا"},
                    ],
                    "relationships": [
                        {
                            "source_concept_id": "meaning",
                            "target_concept_id": "social-action",
                            "relation_type": "prerequisite",
                            "notes": "یادداشت",
                        }
                    ],
                }
            )
        ]
    )
    extractor = AnthropicConceptExtractor(client=FakeClient(fake_response))

    concepts, relationships = extractor.extract(_sample_lesson())

    assert len(concepts) == 2
    social_action = next(c for c in concepts if c.title == "کنش اجتماعی")
    assert social_action.id == "lesson-1:social-action"
    assert social_action.definition == "تعریف کنش اجتماعی"
    assert social_action.confidence_score == 0.9
    assert social_action.source_refs[0].filename == "book.pdf"

    assert len(relationships) == 1
    rel = relationships[0]
    assert rel.source_concept_id == "lesson-1:meaning"
    assert rel.target_concept_id == "lesson-1:social-action"
    assert rel.relation_type.value == "prerequisite"


def test_extract_drops_relationships_referencing_unknown_concepts():
    fake_response = FakeResponse(
        content=[
            FakeToolUseBlock(
                input={
                    "concepts": [{"id": "a", "title": "A"}],
                    "relationships": [
                        {
                            "source_concept_id": "a",
                            "target_concept_id": "does-not-exist",
                            "relation_type": "related",
                        }
                    ],
                }
            )
        ]
    )
    extractor = AnthropicConceptExtractor(client=FakeClient(fake_response))
    concepts, relationships = extractor.extract(_sample_lesson())

    assert len(concepts) == 1
    assert relationships == []


def test_extract_drops_relationships_with_invalid_relation_type():
    fake_response = FakeResponse(
        content=[
            FakeToolUseBlock(
                input={
                    "concepts": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}],
                    "relationships": [
                        {
                            "source_concept_id": "a",
                            "target_concept_id": "b",
                            "relation_type": "not_a_real_type",
                        }
                    ],
                }
            )
        ]
    )
    extractor = AnthropicConceptExtractor(client=FakeClient(fake_response))
    concepts, relationships = extractor.extract(_sample_lesson())

    assert len(concepts) == 2
    assert relationships == []


def test_extract_returns_empty_lists_when_no_tool_use_block_present():
    fake_response = FakeResponse(content=[])
    extractor = AnthropicConceptExtractor(client=FakeClient(fake_response))
    concepts, relationships = extractor.extract(_sample_lesson())
    assert concepts == []
    assert relationships == []


def test_extract_calls_the_api_with_expected_model_and_tool_choice():
    fake_response = FakeResponse(
        content=[FakeToolUseBlock(input={"concepts": [], "relationships": []})]
    )
    fake_client = FakeClient(fake_response)
    extractor = AnthropicConceptExtractor(
        client=fake_client, model="claude-sonnet-5", max_tokens=2048
    )

    extractor.extract(_sample_lesson())

    call_kwargs = fake_client.messages.last_call_kwargs
    assert call_kwargs["model"] == "claude-sonnet-5"
    assert call_kwargs["max_tokens"] == 2048
    assert call_kwargs["tool_choice"] == {
        "type": "tool",
        "name": "record_lesson_concepts",
    }
    assert call_kwargs["tools"][0]["name"] == "record_lesson_concepts"


def test_build_user_message_includes_book_metadata_and_text():
    lesson = _sample_lesson()
    message = _build_user_message(lesson)
    assert lesson.book_title in message
    assert lesson.lesson_title in message
    assert lesson.chapter_title in message
    assert lesson.text in message
