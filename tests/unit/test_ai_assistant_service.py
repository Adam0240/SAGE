
# Tests for SAGE's local AI assistant

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from services.ai_assistant_service import AIAssistantService
from services.document_retrieval_service import DocumentRetrievalService


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
