"""Search previously prepared OctoPrint projects."""

import re
from pathlib import PurePosixPath


class ProjectSearchService:

    @staticmethod
    def normalize(text):
        """Normalize project names for comparison."""

        # Separate camel case filenames.
        text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)

        # Remove capitalization and filename separators.
        text = text.casefold()
        text = re.sub(r"[\W_]+", " ", text)

        return " ".join(text.split())

    def search(self, query, folders):
        """Search all available OctoPrint folders for matching projects."""

        normalized_query = self.normalize(query)

        if not normalized_query:
            return []

        query_words = set(normalized_query.split())
        matches = []

        # Search every folder returned by OctoPrint.
        for entries in folders.values():
            for entry in entries:

                # Ignore folders themselves.
                if entry.is_folder:
                    continue

                # Remove the G-code file extension.
                normalized_path = self.normalize(
                    str(PurePosixPath(entry.path).with_suffix(""))
                )

                # Match project names and their containing folders.
                if query_words.issubset(
                    set(normalized_path.split())
                ):
                    matches.append(entry)

        # Return matches in alphabetical order.
        return sorted(
            matches,
            key=lambda entry: entry.path.casefold(),
        )

    def find_selection(self, selection, matches):
        """Locate a previously retrieved project by name."""

        normalized_selection = self.normalize(selection)

        if not normalized_selection:
            return []

        # Prefer an exact project name or path.
        exact_matches = [
            entry for entry in matches
            if normalized_selection in (
                self.normalize(PurePosixPath(entry.name).stem),
                self.normalize(
                    str(PurePosixPath(entry.path).with_suffix(""))
                ),
            )
        ]

        if exact_matches:
            return exact_matches

        # Otherwise, search for a partial name match.
        query_words = set(normalized_selection.split())

        return [
            entry for entry in matches
            if query_words.issubset(
                set(
                    self.normalize(
                        str(
                            PurePosixPath(entry.path).with_suffix("")
                        )
                    ).split()
                )
            )
        ]

    def create_response(self, query, matches):
        """Create a spoken response based on actual search results."""

        if not matches:
            return (
                f"I could not find a saved project matching "
                f"{query} in OctoPrint."
            )

        # Include folder names to distinguish similarly named files.
        names = [
            self.normalize(
                str(PurePosixPath(entry.path).with_suffix(""))
            )
            for entry in matches
        ]

        if len(matches) == 1:
            return (
                f"Yes, I found a previously prepared project "
                f"named {names[0]}. "
                "Say open the first one to display it."
            )

        # Provide numbered options for voice selection.
        options = ". ".join(
            f"Option {index}: {name}"
            for index, name in enumerate(names[:3], start=1)
        )

        response = (
            f"I found {len(matches)} saved projects matching "
            f"{query}. {options}. "
            "Which project would you like me to display?"
        )

        if len(matches) > 3:
            response += (
                " You can also narrow your search to find "
                "additional results."
            )

        return response