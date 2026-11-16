
"""Format retrieved documentation without generating new equipment instructions."""

from dataclasses import dataclass

from services.document_retrieval_service import SearchResult


@dataclass(frozen=True)
class GuideResponse:
    markdown: str
    sources: tuple[str, ...] = ()
    spoken_text: str = ""


class GuideResponseService:
    def respond(self, question: str, result: SearchResult) -> GuideResponse:
        # The question remains part of this interface for a future AI responder.
        if not result.available:
            message = (
                "Reference documentation is unavailable or empty. "
                "Please ask the STEAM Specialist for help."
            )

            return GuideResponse(
                markdown=message,
                spoken_text=message,
            )

        notice = ""
        if result.unreadable_files:
            notice = "\n\nSome reference documents could not be read; these results may be incomplete."

        if result.clarification:
            message = result.clarification + notice

            return GuideResponse(
                markdown=message,
                spoken_text=message,
            )

        if not result.matches:
            message = (
                "I couldn't find a clear answer in the reference documents. "
                "Please include the equipment, application, and specific symptom or error message. "
                "If the instructions do not cover the problem, ask the STEAM Specialist for help."
                + notice
            )

            return GuideResponse(
                markdown=message,
                spoken_text=message,
            )

        best = result.matches[0]
        similar = [
            match for match in result.matches
            if match.score >= best.score * 0.85
        ]

        if len(similar) > 1:
            topics = "\n".join(
                f"- {match.section.source}"
                for match in similar
            )

            message = (
                "Several topics may match. Which equipment or problem do you mean? "
                "Please add that detail to your question."
            )

            return GuideResponse(
                markdown=message + "\n\n" + topics + notice,
                spoken_text=message + notice,
            )

        section = best.section
        content = section.markdown

        if section.context:
            content = section.context + "\n\n" + content

        topic = " → ".join(section.headings) or section.title

        return GuideResponse(
            markdown=(
                "## Relevant instructions\n\n"
                + f"### {topic}\n\n"
                + content + notice
            ),
            sources=(section.source,),
            spoken_text=(
                f"I found relevant instructions for {topic}. "
                "Please review the instructions on screen, "
                "including any safety warnings."
                + notice
            ),
        )
