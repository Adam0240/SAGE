from pathlib import Path
from unittest.mock import patch

import pytest

from services.document_retrieval_service import DocumentRetrievalService, parse_sections
from services.guide_response_service import GuideResponseService


DOCUMENTS = Path(__file__).resolve().parents[2] / "STEAM_Tutorials"


@pytest.mark.parametrize("question, heading", [
    ("The laser is not dark enough", "The Engraving Is Too Light"),
    ("The engraving isn't light enough", "The Engraving Is Too Dark"),
    ("The engraving isn’t dark enough", "The Engraving Is Too Light"),
    ("The laser engraving is too light", "The Engraving Is Too Light"),
    ("Why is no filament coming out?", "No Filament Is Coming Out"),
])
def test_symptom_meaning_is_preserved(question, heading):
    result = DocumentRetrievalService(DOCUMENTS).search(question)
    response = GuideResponseService().respond(question, result)
    assert result.matches[0].section.headings[-1] == heading
    assert response.sources == (result.matches[0].section.source,)


@pytest.mark.parametrize("question", [
    "My laser print turned into spaghetti", "The printer and laser won't connect",
    "The laser is not too dark", "The print is not sticking but not a pile of string",
    "Which materials are not allowed in the laser?",
])
def test_conflicting_or_uninterpreted_meaning_requests_clarification(question):
    result = DocumentRetrievalService(DOCUMENTS).search(question)
    assert result.clarification
    response = GuideResponseService().respond(question, result)
    assert not response.sources
    assert result.clarification in response.markdown


def test_explicit_laser_cannot_return_printer_spaghetti_instructions():
    result = DocumentRetrievalService(DOCUMENTS).search("The laser makes spaghetti")
    assert not any("3DPrinter" in match.section.filename for match in result.matches)


@pytest.mark.parametrize("question, heading", [
    ("Why won't OctoPrint connect?", "OctoPrint Is Not Connecting to the Printer"),
    ("My print isn't sticking.", "The Print Is Not Sticking"),
    ("My print turned into spaghetti.", "The Print Looks Like a Pile of String"),
    ("THE LASER ENGRAVING IS TOO DARK!", "The Engraving Is Too Dark"),
])
def test_documented_questions_return_original_instructions(question, heading):
    result = DocumentRetrievalService(DOCUMENTS).search(question)
    best = result.matches[0].section
    assert best.headings[-1] == heading
    response = GuideResponseService().respond(question, result)
    assert best.markdown in response.markdown
    assert response.sources == (best.source,)


def test_vague_connection_question_requests_clarification():
    result = DocumentRetrievalService(DOCUMENTS).search("It won't connect")
    response = GuideResponseService().respond("It won't connect", result)
    assert "Which equipment" in response.markdown
    assert "OctoPrint" in response.markdown
    assert "LightBurn" in response.markdown
    assert not response.sources


@pytest.mark.parametrize("question", [
    "How do I repair a spaceship?", "Why is the printer making a grinding noise?",
    "3d printer error", "", "Hey SAGE please help",
])
def test_unsupported_or_insufficient_questions_do_not_guess(question):
    result = DocumentRetrievalService(DOCUMENTS).search(question)
    assert not result.matches
    response = GuideResponseService().respond(question, result)
    assert "couldn't find a clear answer" in response.markdown
    assert not response.sources


def test_parser_preserves_context_lists_code_and_stable_identity():
    text = """# Printer
## Troubleshooting
Ask staff before adjusting equipment.
### Jammed filament
1. Stop the job.
2. Ask staff.

```text
# This is code, not a heading
```
### Empty
"""
    sections = parse_sections("printer.md", text)
    assert len(sections) == 2
    section = sections[-1]
    assert section.headings == ("Troubleshooting", "Jammed filament")
    assert "1. Stop the job.\n2. Ask staff." in section.markdown
    assert "# This is code, not a heading" in section.markdown
    assert section.context == "Ask staff before adjusting equipment."
    edited = parse_sections("printer.md", text.replace("Stop the job.", "Cancel the job."))
    assert edited[-1].identifier == section.identifier


@pytest.mark.parametrize("line, expected", [
    ("## Heading", "Heading"),
    ("   ###### Heading ###  ", "Heading"),
    ("##\t Heading\t##\t", "Heading"),
    ("## Heading###", "Heading"),
    ("## Heading # #  ", "Heading #"),
    ("## C# examples", "C# examples"),
    ("## ###", "#"),
    ("##  ", " "),
    ("## \t", "\t"),
    ("## ", None),
    ("##", None),
    ("##Heading", None),
    ("####### Heading", None),
    ("    ## Heading", None),
])
def test_heading_delimiters_preserve_existing_behavior(line, expected):
    section, = parse_sections("guide.md", line + "\nInstructions.")
    assert section.headings == (() if expected is None else (expected,))
    assert section.markdown == (
        (line + "\nInstructions.").strip() if expected is None else "Instructions.")


def test_long_heading_whitespace_and_hash_runs_preserve_text():
    # Trailing text after long whitespace/hash runs forced the old lazy regex
    # to repeatedly reconsider potential closing delimiters.
    text = "Heading" + " " * 100_000 + "#" * 100_000 + " end"
    section, = parse_sections("guide.md", "## " + text + " ###\nInstructions.")
    assert section.headings == (text,)
    assert section.markdown == "Instructions."


def test_parent_cautions_are_included_in_response(tmp_path):
    (tmp_path / "printer.md").write_text(
        "# Printer\n## Troubleshooting\nAsk staff before adjustments.\n"
        "### Jammed filament\nStop the job.", encoding="utf-8")
    result = DocumentRetrievalService(tmp_path).search("jammed filament")
    response = GuideResponseService().respond("jammed filament", result)
    assert "Ask staff before adjustments." in response.markdown
    assert "Stop the job." in response.markdown


@pytest.mark.parametrize("second_caution", ["Second setup caution.", ""])
def test_repeated_parent_headings_keep_only_their_own_guidance(second_caution):
    text = ("# Guide\nShared guidance.\n## Setup\nFirst setup caution.\n"
            "### Procedure\nFirst procedure.\n## Setup\n" + second_caution +
            "\n### Procedure\nSecond procedure.")
    sections = parse_sections("guide.md", text)
    procedures = [section for section in sections if section.headings == ("Setup", "Procedure")]
    assert procedures[0].context == "Shared guidance.\n\nFirst setup caution."
    assert procedures[1].context == "Shared guidance." + (
        "\n\n" + second_caution if second_caution else "")
    assert procedures[0].identifier != procedures[1].identifier
    edited = parse_sections("guide.md", text.replace("Second procedure.", "Edited procedure."))
    assert edited[-1].identifier == procedures[1].identifier


def test_nested_repeated_headings_and_skipped_levels_preserve_ancestor_order():
    sections = parse_sections("guide.md", """# Guide
Root caution.
## Setup
Outer caution.
#### Setup
Inner caution.
###### Action
First instructions.
#### Setup
###### Action
Second instructions.
## Other
### Action
Third instructions.
""")
    actions = [section for section in sections if section.headings[-1:] == ("Action",)]
    assert [section.context for section in actions] == [
        "Root caution.\n\nOuter caution.\n\nInner caution.",
        "Root caution.\n\nOuter caution.",
        "Root caution.",
    ]


def test_repeated_document_heading_does_not_reuse_previous_root_guidance():
    sections = parse_sections("guide.md", "# Guide\nFirst root caution.\n"
                              "## Task\nFirst instructions.\n# Guide\n"
                              "Second root caution.\n## Task\nSecond instructions.")
    tasks = [section for section in sections if section.headings == ("Task",)]
    assert [section.context for section in tasks] == ["First root caution.", "Second root caution."]


@pytest.mark.parametrize("question, own, other", [
    ("alpha procedure", "First setup caution.", "Second setup caution."),
    ("beta procedure", "Second setup caution.", "First setup caution."),
])
def test_retrieved_response_excludes_other_repeated_parent_guidance(tmp_path, question, own, other):
    (tmp_path / "guide.md").write_text(
        "# Guide\n## Setup\nFirst setup caution.\n### Alpha procedure\nAlpha instructions.\n"
        "## Setup\nSecond setup caution.\n### Beta procedure\nBeta instructions.", encoding="utf-8")
    result = DocumentRetrievalService(tmp_path).search(question)
    response = GuideResponseService().respond(question, result)
    assert response.sources == (result.matches[0].section.source,)
    assert own in response.markdown
    assert other not in response.markdown


def test_add_edit_and_remove_documents_are_reflected(tmp_path):
    service = DocumentRetrievalService(tmp_path)
    path = tmp_path / "printer.MD"
    path.write_text("# Printer\n## Filament jam\nAsk Adam.", encoding="utf-8")
    first = service.search("filament jam").matches[0].section
    path.write_text("# Printer\n## Filament jam\nAsk Jane.", encoding="utf-8")
    edited = service.search("filament jam").matches[0].section
    assert edited.identifier == first.identifier
    assert edited.markdown == "Ask Jane."
    path.unlink()
    assert not service.search("filament jam").available
    assert service.files == ()


def test_missing_empty_and_unreadable_documents(tmp_path):
    assert not DocumentRetrievalService(tmp_path / "missing").search("jam").available
    path = tmp_path / "empty.md"
    path.write_text("# Heading only", encoding="utf-8")
    service = DocumentRetrievalService(tmp_path)
    assert not service.search("heading").available
    path.write_bytes(b"\xff")
    result = service.search("heading")
    assert result.unreadable_files == ("empty.md",)
    assert "unavailable or empty" in GuideResponseService().respond("heading", result).markdown
    with patch.object(Path, "read_text", side_effect=PermissionError):
        assert not service.search("heading").available


def test_partial_read_failure_keeps_usable_answers_and_discloses_missing_files(tmp_path):
    (tmp_path / "bad.md").write_bytes(b"\xff")
    (tmp_path / "good.md").write_text("# Printer\n## Filament jam\nAsk staff.", encoding="utf-8")
    result = DocumentRetrievalService(tmp_path).search("filament jam")
    response = GuideResponseService().respond("filament jam", result)
    assert "Ask staff." in response.markdown
    assert "may be incomplete" in response.markdown
    assert response.sources == ("good.md → Filament jam",)
