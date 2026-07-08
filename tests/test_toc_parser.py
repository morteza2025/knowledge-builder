from app.infrastructure.text.toc_parser import parse_toc_text

_SIMPLE_TOC = """فهرست
فصل اول: زندگی اجتماعی .............................................. 1
درس اول: کنش های ما .............................................. 3
پرسش نمونه اول؟.......................................................... 3
پرسش نمونه دوم؟.......................................................... 6
درس دوم: پدیده های اجتماعی ...................................... 10
فصل دوم: هویت ........................................................... 65
درس سوم: هویت فردی .................................................. 67
"""


def test_parses_chapters_lessons_and_subtopics_with_correct_page_numbers():
    outline = parse_toc_text(_SIMPLE_TOC)

    assert len(outline.chapters) == 2

    chapter_1 = outline.chapters[0]
    assert chapter_1.order == 1
    assert chapter_1.title == "زندگی اجتماعی"
    assert chapter_1.page == 1
    assert len(chapter_1.lessons) == 2

    lesson_1 = chapter_1.lessons[0]
    assert lesson_1.order == 1
    assert lesson_1.title == "کنش های ما"
    assert lesson_1.page == 3
    assert len(lesson_1.subtopics) == 2
    assert lesson_1.subtopics[0].title == "پرسش نمونه اول؟"
    assert lesson_1.subtopics[0].page == 3
    assert lesson_1.subtopics[1].page == 6

    lesson_2 = chapter_1.lessons[1]
    assert lesson_2.order == 2
    assert lesson_2.page == 10

    chapter_2 = outline.chapters[1]
    assert chapter_2.order == 2
    assert chapter_2.lessons[0].order == 3  # global numbering, not per-chapter


def test_handles_mixed_script_page_numbers():
    # Page 29 as Latin '2' + Persian-Indic '٩' (=9), the exact pattern
    # verified against input/C110220.pdf.
    toc = "فهرست\nدرس اول: موضوع نمونه .......................... 2٩\n"
    outline = parse_toc_text(toc)
    assert outline.chapters == []  # no chapter seen -> lesson has nowhere to attach
    # Wrap it in a chapter so the lesson attaches, to check the page value:
    toc_with_chapter = (
        "فهرست\nفصل اول: عنوان .......................... 1\n"
        "درس اول: موضوع نمونه .......................... 2٩\n"
    )
    outline = parse_toc_text(toc_with_chapter)
    assert outline.chapters[0].lessons[0].page == 29


def test_merges_a_wrapped_continuation_line_before_the_label():
    # Reproduces the exact verified quirk: a single word ("کنش") lands on
    # its own line ABOVE the "درس اول: ..." line it belongs with.
    toc = (
        "فهرست\n"
        "فصل اول: عنوان .......................... 1\n"
        "کنش\n"
        "درس اول: های ما .............................. 3\n"
    )
    outline = parse_toc_text(toc)
    lesson = outline.chapters[0].lessons[0]
    assert lesson.order == 1
    assert lesson.title == "کنش های ما"
    assert lesson.page == 3


def test_merges_a_wrapped_continuation_line_after_a_subtopic_label():
    toc = (
        "فهرست\n"
        "فصل اول: عنوان .......................... 1\n"
        "درس اول: عنوان درس .............................. 3\n"
        "کنش\n"
        "اجتماعی چیست؟.............................. 5\n"
    )
    outline = parse_toc_text(toc)
    subtopic = outline.chapters[0].lessons[0].subtopics[0]
    assert subtopic.title == "کنش اجتماعی چیست؟"
    assert subtopic.page == 5


def test_fixes_the_avval_shadda_artifact_for_both_chapter_and_lesson():
    # Reproduces the exact verified artifact: "اول" (first) extracts as
    # "ا ّول" with a stray space around its shadda diacritic.
    toc = (
        "فهرست\n"
        "فصل ا ّول: زندگی اجتماعی .............................. 1\n"
        "درس ا ّول: عنوان .............................. 3\n"
    )
    outline = parse_toc_text(toc)
    assert outline.chapters[0].order == 1
    assert outline.chapters[0].lessons[0].order == 1


def test_toc_heading_label_itself_is_not_treated_as_an_entry():
    toc = "فهرست\nفصل اول: عنوان .............................. 1\n"
    outline = parse_toc_text(toc)
    assert len(outline.chapters) == 1  # "فهرست" line didn't become a bogus chapter


def test_empty_toc_text_produces_an_empty_outline():
    outline = parse_toc_text("")
    assert outline.chapters == []
