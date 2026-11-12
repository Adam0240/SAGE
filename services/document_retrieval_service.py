"""Local Markdown retrieval, independent of Qt and response generation."""

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class DocumentSection:
    identifier: str
    filename: str
    title: str
    headings: tuple[str, ...]
    markdown: str
    context: str = ""

    @property
    def source(self):
        return f"{self.filename} → {' → '.join(self.headings) or self.title}"


@dataclass(frozen=True)
class SectionMatch:
    section: DocumentSection
    score: float


@dataclass(frozen=True)
class SearchResult:
    matches: tuple[SectionMatch, ...]
    available: bool
    unreadable_files: tuple[str, ...] = ()
    clarification: str = ""


STOP_WORDS = set("""a an the is are am was were be been being it its my me i you
your we our they their this that these those to of for in on at from with and or
but as by do does did how why what when where can could would should please hey
sage help having have has get getting looks look like will not no wont isnt cannot
dont work working problem issue error something need want im turned into too""".split())
ALIASES = {
    "printing": "print", "printed": "print", "prints": "print",
    "printer": "print", "printers": "print",
    "connecting": "connect", "connection": "connect", "connected": "connect",
    "connections": "connect", "sticking": "stick", "sticks": "stick",
    "adhesion": "stick", "engraving": "engrave", "engraver": "engrave",
    "engraved": "engrave", "settings": "setting", "details": "detail",
    "hours": "hour", "materials": "material", "files": "file",
    "spaghetti": "string", "strings": "string",
}
EQUIPMENT_WORDS = {"3d", "print", "laser", "engrave", "snapmaker", "2", "0"}


def normalize(text):
    text = text.casefold().replace("’", "'")
    return re.sub(
        r"\b(?:won't|isn't|aren't|can't|cannot|doesn't|don't|isnt|wont|cant|doesnt|dont)\b",
        "not", text,
    )


def tokens(text):
    text = normalize(text).replace("'", "")
    return [ALIASES.get(word, word) for word in re.findall(r"[a-z0-9]+", text)
            if word not in STOP_WORDS]


def equipment(text):
    words = set(tokens(text))
    groups = set()
    if words & {"3d", "print"}:
        groups.add("printer")
    if words & {"laser", "engrave"}:
        groups.add("laser")
    return groups


def interpret_question(question):
    """Recognize a small set of failure phrases; clarify other negation.

    Keyword ranking must not silently discard a word that reverses the symptom.
    This deliberately does not attempt general natural-language understanding.
    """
    question = normalize(question)
    for adjective, opposite in (("dark", "light"), ("light", "dark")):
        question = re.sub(rf"\bnot\s+{adjective}\s+enough\b", opposite, question)
    # Removing these recognized negations is safe only for failure retrieval.
    question = re.sub(r"\bnot\s+((?:(?:octoprint|cura|luban|lightburn|it|the printer|my print)\s+)?"
                      r"(?:be\s+)?(?:connect(?:ing|ed)?|stick(?:ing)?))\b",
                      r"\1", question)
    question = re.sub(r"\bno\s+filament\b", "filament", question)
    if re.search(r"\b(?:not|no|never|without|neither)\b", question):
        return question, (
            "Please describe the symptom directly so I don't reverse its meaning. "
            "For example: 'engraving too light', 'print not sticking', or 'OctoPrint won't connect'."
        )
    return question, ""


@dataclass
class _Heading:
    level: int
    text: str
    body: str = ""


def _parse_heading(line):
    # Match only the bounded prefix; scan whitespace and closing hashes with
    # string operations so long headings cannot trigger regex backtracking.
    prefix = re.match(r"^\s{0,3}(#{1,6})\s", line)
    if prefix is None:
        return None
    remainder = line[prefix.end():]
    if not remainder:
        return None
    text = remainder.lstrip() or remainder[-1]
    # Preserve the old pattern's nonempty heading text, including headings
    # consisting only of hashes or whitespace.
    text = text[0] + text[1:].rstrip().rstrip("#").rstrip()
    return _Heading(len(prefix.group(1)), text)


def parse_sections(filename, markdown):
    """Split ATX headings, retaining lists, fenced code, and ancestor guidance."""
    title = Path(filename).stem
    stack = []
    records = []
    lines = []
    fence = None

    def flush():
        body = "\n".join(lines).strip()
        if body:
            # Snapshot actual ancestors while this heading instance is active.
            # A later heading with the same text belongs to a different branch.
            context = "\n\n".join(node.body for node in stack[:-1] if node.body)
            hierarchy = tuple((node.level, node.text) for node in stack)
            records.append((hierarchy, body, context))
            if stack:
                stack[-1].body = body
        lines.clear()

    for line in markdown.splitlines():
        fence_match = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            lines.append(line)
            continue
        heading = None if fence else _parse_heading(line)
        if heading:
            flush()
            level, text = heading.level, heading.text
            while stack and stack[-1].level >= level:
                stack.pop()
            stack.append(_Heading(level, text))
            if level == 1:
                title = text
        else:
            lines.append(line)
    flush()

    sections = []
    counts = {}
    for hierarchy, body, context in records:
        headings = tuple(text for level, text in hierarchy if level != 1)
        key = "/".join(text for _, text in hierarchy) or title
        counts[key] = counts.get(key, 0) + 1
        sections.append(DocumentSection(
            f"{filename}#{key}:{counts[key]}", filename, title, headings, body, context,
        ))
    return tuple(sections)


class DocumentRetrievalService:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.sections = ()
        self.files = ()
        self.unreadable_files = ()
        self._cache = {}
        self.refresh()

    def refresh(self):
        # These small local documents are read on each query, so same-size edits
        # and rapid saves are picked up without depending on filesystem timestamps.
        try:
            paths = sorted((p for p in self.directory.iterdir()
                            if p.is_file() and p.suffix.lower() == ".md"),
                           key=lambda p: p.name.casefold())
        except OSError:
            paths = []
        cache, sections, unreadable = {}, [], []
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                unreadable.append(path.name)
                continue
            previous = self._cache.get(path.name)
            parsed = previous[1] if previous and previous[0] == text else parse_sections(path.name, text)
            cache[path.name] = (text, parsed)
            sections.extend(parsed)
        self._cache = cache
        self.files = tuple(paths)
        self.sections = tuple(sections)
        self.unreadable_files = tuple(unreadable)

    def search(self, question, limit=3):
        self.refresh()
        requested_equipment = equipment(question)
        if len(requested_equipment) > 1:
            return SearchResult((), bool(self.sections), self.unreadable_files,
                                "Do you mean the 3D printer or the laser engraver? "
                                "Please specify one machine and its symptom.")
        question, clarification = interpret_question(question)
        if clarification:
            return SearchResult((), bool(self.sections), self.unreadable_files, clarification)
        query = set(tokens(question))
        specific = query - EQUIPMENT_WORDS
        matches = []
        for section in self.sections:
            section_equipment = equipment(section.title)
            if (requested_equipment and section_equipment
                    and not requested_equipment & section_equipment):
                continue
            heading = set(tokens(" ".join(section.headings)))
            body = set(tokens(section.markdown))
            title = set(tokens(section.title))
            overlap = query & (heading | body | title)
            # Equipment names alone cannot identify a problem or an answer.
            if not specific or not specific & (heading | body):
                continue
            coverage = len(overlap) / len(query)
            if coverage < 0.6:
                continue
            score = (5 * len(query & heading) + 2 * len(query & body)
                     + len(query & title)) * coverage
            query_phrase = " ".join(tokens(question))
            if query_phrase and query_phrase in " ".join(tokens(" ".join(section.headings))):
                score += 3
            matches.append(SectionMatch(section, score))
        matches.sort(key=lambda match: (-match.score, match.section.identifier))
        return SearchResult(tuple(matches[:limit]), bool(self.sections), self.unreadable_files)
