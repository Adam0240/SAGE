"""Identify supported SAGE voice commands."""

import re


class VoiceCommandService:

    @staticmethod
    def get_project_search_query(transcript):
        """Identify requests to search for saved 3D printing projects."""

        # Normalize the recognized speech.
        text = transcript.casefold().strip()
        text = re.sub(r"\b3[\s-]*d\b", "3d", text)
        text = re.sub(r"[^\w\s]", " ", text)
        text = " ".join(text.split())

        # Remove the optional greeting.
        text = re.sub(r"^(?:hey\s+)?sage\s+", "", text)

        # Identify requests to locate existing projects.
        prefixes = (
            "do we have ",
            "do you have ",
            "can you find ",
            "can you check if we have ",
            "find ",
            "search for ",
            "look for ",
            "pull up ",
            "show me ",
            "open ",
            "display ",
        )

        for prefix in prefixes:
            if text.startswith(prefix):
                query = text[len(prefix):]
                break
        else:
            return None

        # Ensure the request relates to a model or saved project.
        if not re.search(
            r"\b(?:3d|models?|projects?|prints?|gcode)\b",
            query,
        ):
            return None

        # Remove references to the saved project collection.
        query = re.sub(
            r"\b(?:from|in)\s+(?:my|our|the)\s+"
            r"(?:previous|saved|existing)\s+projects?\b",
            "",
            query,
        )

        # Remove words that are not part of the model name.
        query = re.sub(
            r"\b(?:a|an|the|of|for|3d|model|models|"
            r"print|prints|project|projects|saved|"
            r"existing|previous|already|gcode)\b",
            " ",
            query,
        )

        return " ".join(query.split()) or None

    @staticmethod
    def get_project_selection(transcript):
        """Identify a request to display a project."""

        # Normalize the recognized speech.
        text = transcript.casefold().strip()
        text = re.sub(r"[^\w\s]", " ", text)
        text = " ".join(text.split())

        # Remove the optional greeting.
        text = re.sub(r"^(?:hey\s+)?sage\s+", "", text)

        # Identify requests to display an existing project.
        prefixes = (
            "show me ",
            "open ",
            "display ",
            "pull up ",
            "select ",
        )

        for prefix in prefixes:
            if text.startswith(prefix):
                selection = text[len(prefix):]
                selection = re.sub(r"^the\s+", "", selection)
                return selection

        return None

    @staticmethod
    def get_selection_index(selection):
        """Convert a spoken selection into a result index."""

        # Associate spoken numbers with their corresponding index.
        selections = {
            "first": 0,
            "one": 0,
            "1": 0,
            "second": 1,
            "two": 1,
            "2": 1,
            "third": 2,
            "three": 2,
            "3": 2,
        }

        # Remove unnecessary words from the selection.
        selection = re.sub(
            r"^(?:option|number|result)\s+",
            "",
            selection,
        )

        selection = re.sub(r"\s+one$", "", selection)

        return selections.get(selection)