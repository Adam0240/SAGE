
# Tests for SAGE's local AI assistant

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services.ai_assistant_service import AIAssistantService
from services.document_retrieval_service import DocumentRetrievalService
from services.guide_response_service import GuideResponseService

DOCUMENTS = Path(__file__).resolve().parents[2] / "STEAM_Tutorials"


def make_assistant():
    fake_ollama = Mock()
    retrieval = DocumentRetrievalService(DOCUMENTS)
    assistant = AIAssistantService(retrieval, client=fake_ollama)
    return assistant, fake_ollama


def test_documented_question_generates_answer():
    assistant, fake_ollama = make_assistant()

    fake_ollama.chat.return_value = SimpleNamespace(
        message=SimpleNamespace(
            content="Close Cura and reconnect through OctoPrint."
        )
    )

    response = assistant.respond("Why won't OctoPrint connect?")

    assert "Close Cura and reconnect" in response.markdown
    assert "3DPrinter_Snapmaker2.0.md" in response.sources[0]
    assert "OctoPrint Is Not Connecting" in response.sources[0]
    assert fake_ollama.chat.call_count == 1
    assert "AI-generated summary" in response.markdown

    # Confirm the actual documentation was supplied to Ollama.
    messages = fake_ollama.chat.call_args.kwargs["messages"]
    assert "Close Cura" in messages[1]["content"]


def test_ollama_failure_uses_documentation_fallback():
    assistant, fake_ollama = make_assistant()

    fake_ollama.chat.side_effect = ConnectionError(
        "Ollama unavailable"
    )

    response = assistant.respond("Why won't OctoPrint connect?")

    assert "Close Cura" in response.markdown
    assert "3DPrinter_Snapmaker2.0.md" in response.sources[0]
    assert fake_ollama.chat.call_count == 1


def test_unsupported_question_does_not_call_ai():
    assistant, fake_ollama = make_assistant()

    response = assistant.respond("How do I repair a spaceship?")

    assert not response.sources
    assert "couldn't find a clear answer" in response.markdown
    fake_ollama.chat.assert_not_called()


def test_ambiguous_question_requests_clarification():
    assistant, fake_ollama = make_assistant()

    response = assistant.respond(
        "The printer and laser won't connect"
    )

    assert not response.sources
    assert "Do you mean" in response.markdown
    fake_ollama.chat.assert_not_called()


def test_original_safety_instructions_are_preserved(tmp_path):
    document = tmp_path / "printer.md"
    document.write_text(
        "# Printer\n"
        "Ask staff before touching the hot nozzle.\n"
        "## Filament jam\n"
        "Stop the printer and ask staff.\n",
        encoding="utf-8",
    )

    fake_ollama = Mock()
    fake_ollama.chat.return_value = SimpleNamespace(
        message=SimpleNamespace(content="Stop printing.")
    )

    assistant = AIAssistantService(
        DocumentRetrievalService(tmp_path),
        client=fake_ollama,
    )

    response = assistant.respond("filament jam")

    assert "Ask staff before touching the hot nozzle" in response.markdown
    assert "Stop the printer and ask staff" in response.markdown
    assert "Ask staff before touching the hot nozzle" in response.spoken_text
    assert "Stop the printer and ask staff" in response.spoken_text
    assert response.sources == ("printer.md → Filament jam",)



def test_undocumented_settings_are_rejected():
    assistant, fake_ollama = make_assistant()

    fake_ollama.chat.return_value = SimpleNamespace(
        message=SimpleNamespace(
            content="Use a layer height of 0.4 mm."
        )
    )

    response = assistant.respond(
        "What layer height setting should I use in Cura?"
    )

    assert "0.4 mm" not in response.markdown
    assert "does not confirm" in response.markdown
    assert response.sources


@pytest.mark.parametrize("answer", [
    "Stop printing.",  # Omits both supervision and the specific caution.
    "Heat the nozzle to 999 C and remove the cover.",  # Unrecognized units.
    "Set the temperature to nine hundred degrees.",
    "Set the power to 999.",  # Unitless setting.
    "Remove the cover while the printer runs.",  # Invented nonnumeric action.
    "Set the nozzle diameter to 0.2 mm.",  # Documented number, wrong setting.
    "Set layer height to 0.4 mm.",  # Recognized unsupported setting.
    "",  # Empty-answer fallback must preserve the same cautions.
    None,
])
def test_speech_preserves_full_reference_instead_of_generated_procedures(tmp_path, answer):
    (tmp_path / "printer.md").write_text(
        "# Printer\nStaff supervision is required.\n"
        "## Filament jam\nStop the printer and ask staff.\n"
        "Do not remove the cover while the printer runs.\n"
        "The documented layer height is 0.2 mm.\n", encoding="utf-8")
    # Partial read failures must also remain audible, including on AI success.
    (tmp_path / "unreadable.md").write_bytes(b"\xff")
    retrieval = DocumentRetrievalService(tmp_path)
    expected = GuideResponseService().respond("filament jam", retrieval.search("filament jam"))
    client = Mock()
    client.chat.return_value = SimpleNamespace(message=SimpleNamespace(content=answer))
    response = AIAssistantService(retrieval, client=client).respond("filament jam")
    client.chat.assert_called_once()
    assert response.spoken_text == expected.spoken_text
    assert "Staff supervision is required." in response.spoken_text
    assert "Do not remove the cover" in response.spoken_text
    assert "may be incomplete" in response.spoken_text
    assert response.sources == expected.sources
    assert "Staff supervision is required." in response.markdown
    assert "Do not remove the cover" in response.markdown
