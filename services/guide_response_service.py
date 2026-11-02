"""Format retrieved documentation without generating new equipment instructions."""

from dataclasses import dataclass

from services.document_retrieval_service import SearchResult


@dataclass(frozen=True)
class GuideResponse:
    markdown: str
    sources: tuple[str, ...] = ()


class GuideResponseService:
    def respond(self, question: str, result: SearchResult) -> GuideResponse:
        # The question remains part of this interface for a future AI responder.
        if not result.available:
            return GuideResponse(
                "Reference documentation is unavailable or empty. "
                "Please ask the STEAM Specialist for help."
            )
        notice = ""
        if result.unreadable_files:
            notice = "\n\nSome reference documents could not be read; these results may be incomplete."
        if result.clarification:
            return GuideResponse(result.clarification + notice)
        if not result.matches:
            return GuideResponse(
                "I couldn't find a clear answer in the reference documents. "
                "Please include the equipment, application, and specific symptom or error message. "
                "If the instructions do not cover the problem, ask the STEAM Specialist for help."
                + notice
            )
        best = result.matches[0]
        similar = [match for match in result.matches if match.score >= best.score * 0.85]
        if len(similar) > 1:
            topics = "\n".join(f"- {match.section.source}" for match in similar)
            return GuideResponse(
                "Several topics may match. Which equipment or problem do you mean? "
                "Please add that detail to your question.\n\n" + topics + notice
            )
        section = best.section
        content = section.markdown
        if section.context:
            content = section.context + "\n\n" + content
        return GuideResponse(
            "## Relevant instructions\n\n"
            + f"### {' → '.join(section.headings) or section.title}\n\n"
            + content + notice,
            (section.source,),
        )
