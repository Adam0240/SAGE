import pytest

from services.voice_command_service import VoiceCommandService


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Do we have a 3D model of a heart?", "heart"),
        ("Hey SAGE, find a saved brain model.", "brain"),
        ("Do you have a model of the Earth?", "earth"),
        (
            "Pull up the heart 3D print from my previous projects.",
            "heart",
        ),
        ("Why isn't my 3D printer connecting?", None),
        ("How do I use Cura?", None),
    ],
)
def test_project_search_commands(question, expected):
    service = VoiceCommandService()

    assert service.get_project_search_query(question) == expected

@pytest.mark.parametrize(
    "question, expected",
    [
        ("Show me the first one.", "first one"),
        ("Open number two.", "number two"),
        ("Open the anatomical heart.", "anatomical heart"),
        ("How do I use Cura?", None),
    ],
)
def test_project_selection_commands(question, expected):
    service = VoiceCommandService()

    assert service.get_project_selection(question) == expected


@pytest.mark.parametrize(
    "selection, expected",
    [
        ("first one", 0),
        ("number two", 1),
        ("option three", 2),
        ("anatomical heart", None),
    ],
)
def test_project_selection_index(selection, expected):
    service = VoiceCommandService()

    assert service.get_selection_index(selection) == expected