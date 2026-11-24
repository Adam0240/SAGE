from services.octoprint_file_service import RemoteFile
from services.project_search_service import ProjectSearchService


def test_search_saved_projects():
    service = ProjectSearchService()

    folders = {
        "": [
            RemoteFile("Anatomy", is_folder=True),
            RemoteFile("Heart_Keychain.gcode"),
        ],
        "Anatomy": [
            RemoteFile("Anatomy/Anatomical_Heart.gcode"),
            RemoteFile("Anatomy/Human_Brain.gcode"),
        ],
    }

    matches = service.search("heart", folders)

    assert len(matches) == 2


def test_search_is_case_insensitive():
    service = ProjectSearchService()

    folders = {
        "": [RemoteFile("Anatomical_Heart.gcode")]
    }

    assert len(service.search("HEART", folders)) == 1


def test_no_matching_projects():
    service = ProjectSearchService()

    folders = {
        "": [RemoteFile("Heart.gcode")]
    }

    assert service.search("dinosaur", folders) == []


def test_response_for_single_project():
    service = ProjectSearchService()

    response = service.create_response(
        "heart",
        [RemoteFile("Anatomical_Heart.gcode")],
    )

    assert "anatomical heart" in response


def test_response_for_missing_project():
    service = ProjectSearchService()

    response = service.create_response("heart", [])

    assert "could not find" in response


def test_find_project_selection():
    service = ProjectSearchService()

    matches = [
        RemoteFile("Anatomical_Heart.gcode"),
        RemoteFile("Heart_Keychain.gcode"),
    ]

    results = service.find_selection(
        "anatomical heart",
        matches,
    )

    assert results == [matches[0]]


def test_ambiguous_project_selection():
    service = ProjectSearchService()

    matches = [
        RemoteFile("Anatomical_Heart.gcode"),
        RemoteFile("Heart_Keychain.gcode"),
    ]

    results = service.find_selection("heart", matches)

    assert len(results) == 2