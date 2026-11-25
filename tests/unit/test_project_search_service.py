from services.octoprint_file_service import RemoteFile
from services.project_search_service import ProjectSearchService


def test_search_saved_projects():
    service = ProjectSearchService()

    folders = {
        "": [
            RemoteFile("Heart", is_folder=True),
            RemoteFile("Heart_Keychain.gcode"),
        ],
        "Anatomy": [
            RemoteFile("Anatomy/AnatomicalHeart.gcode"),
            RemoteFile("Anatomy/Human_Brain.gcode"),
        ],
    }

    matches = service.search("heart", folders)

    assert [entry.path for entry in matches] == [
        "Anatomy/AnatomicalHeart.gcode", "Heart_Keychain.gcode"]
    assert service.search("", folders) == []
    assert service.search("gcode", folders) == []
    assert [entry.path for entry in service.search("anatomical heart", folders)] == [
        "Anatomy/AnatomicalHeart.gcode"]


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


def test_response_limits_spoken_options_and_offers_narrowing():
    service = ProjectSearchService()
    entries = [RemoteFile(f"Heart_{index}.gcode") for index in range(4)]
    response = service.create_response("heart", entries)
    assert "4 saved projects" in response
    assert "Option 1: heart 0" in response and "Option 3: heart 2" in response
    assert "Option 4" not in response and "narrow your search" in response
