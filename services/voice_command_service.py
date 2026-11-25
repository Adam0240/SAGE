"""Identify supported SAGE voice commands."""

import re


def _normalize_transcript(transcript, *, join_3d=False):
    text = transcript.casefold().strip()
    if join_3d:
        text = re.sub(r"\b3[\s-]*d\b", "3d", text)
    text = " ".join(re.sub(r"[^\w\s]", " ", text).split())
    return re.sub(r"^(?:hey\s+)?sage\s+", "", text)

class VoiceCommandService:

    @staticmethod
    def get_project_search_query(transcript):
        """Identify requests to search for saved 3D printing projects."""

        # Normalize the recognized speech.
        text = _normalize_transcript(transcript, join_3d=True)

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
        text = _normalize_transcript(transcript)

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

    @staticmethod
    def is_printer_status_command(transcript):
        """Identify requests for the current printer status."""

        # Normalize the recognized speech.
        text = _normalize_transcript(transcript)

        # Identify supported printer status requests.
        commands = (
            "printer status",
            "print status",
            "check printer status",
            "check the printer status",
            "check print status",
            "check the print status",
            "what is the printer status",
            "what is the print status",
            "what s the printer status",
            "what s the print status",
            "is the printer connected",
            "is the printer busy",
            "is the printer printing",
            "is the printer ready",
            "how long is left on the print",
            "how much time is left on the print",
            "how much time is remaining on the print",
            "how long until the print is finished",
            "when will the print be finished",
            "how long until the print is done",
            "how much longer until the print is done",
            "remaining print time",
            "how much time is remaining",
        )

        return text in commands
