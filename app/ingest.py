"""Knowledge-base ingestion: parse source documents, chunk, embed, upsert.

Run offline/manually, not exposed over HTTP (see CODING_STANDARDS.md and
CONTEXT.md). Parses pdf/docx/txt/md, splits each document into fragments
(~200-500 tokens), embeds them, and upserts them into Qdrant with a stable id
derived from ``source`` + chunk index — so re-running ingestion overwrites the
same fragments rather than duplicating them.

Usage:
    python -m app.ingest <path-to-file-or-directory>
"""

from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

from qdrant_client.models import PointStruct

from app.rag import _ensure_collection, _qdrant_client, embed
from app import config

# Extensions we know how to parse.
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".txt", ".md"})

# Target upper bound of words per fragment. ~300 words ≈ ~200-500 tokens.
DEFAULT_MAX_WORDS: int = 300

# Fixed namespace so point ids are stable across runs (uuid5 is deterministic).
_ID_NAMESPACE: uuid.UUID = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(path: Path) -> str:
    from docx import Document

    document = Document(str(path))
    return "\n\n".join(paragraph.text for paragraph in document.paragraphs)


def extract_text(path: Path) -> str:
    """Return the plain text of a supported document."""
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    raise ValueError(f"Unsupported file type: {path.suffix} ({path})")


def _split_paragraph(paragraph: str, max_words: int) -> list[str]:
    """Split a single over-budget paragraph into word-bounded slices."""
    words = paragraph.split()
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]


_HEADING_RE = re.compile(r"#{1,6}(\s|$)")


def _is_heading_line(line: str) -> bool:
    """True for an ATX Markdown heading line (``#`` – ``######`` then space)."""
    return bool(_HEADING_RE.match(line.lstrip()))


def chunk_text(text: str, max_words: int = DEFAULT_MAX_WORDS) -> list[str]:
    """Split ``text`` into fragments of at most ``max_words`` words.

    Packs whole paragraphs (blank-line separated) greedily up to the budget;
    any single paragraph larger than the budget is split on word boundaries.
    A Markdown heading starts a new fragment (issue #28: packing several
    subsections into one large fragment dilutes the embedding's specificity,
    so retrieval misses details inside it). The heading may sit on its own
    (blank line before the body) or share the paragraph with the body's first
    line — both start a section. A heading-only paragraph rides along with
    the section body that follows it rather than becoming its own fragment.
    After changing this logic, existing documents must be re-ingested
    (``python -m app.ingest ...``) for the new chunks to be live.
    """
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    current_has_body = False

    def flush() -> None:
        nonlocal current, current_words, current_has_body
        if current:
            chunks.append("\n\n".join(current))
            current = []
            current_words = 0
            current_has_body = False

    for raw in text.split("\n\n"):
        paragraph = raw.strip()
        if not paragraph:
            continue
        lines = paragraph.splitlines()
        starts_section = _is_heading_line(lines[0])
        heading_only = starts_section and len(lines) == 1
        words = len(paragraph.split())
        if starts_section and current_has_body:
            flush()
        if not heading_only and words > max_words:
            if current_has_body:
                flush()
            pending = current  # headings waiting for their body, if any
            current = []
            current_words = 0
            slices = _split_paragraph(paragraph, max_words)
            if pending:
                slices[0] = "\n\n".join(pending + [slices[0]])
            chunks.extend(slices)
            continue
        if current_words + words > max_words:
            flush()
        current.append(paragraph)
        current_words += words
        current_has_body = current_has_body or not heading_only

    flush()
    return chunks


def _point_id(source: str, index: int) -> str:
    """Deterministic point id for the ``index``-th fragment of ``source``."""
    return str(uuid.uuid5(_ID_NAMESPACE, f"{source}:{index}"))


def ingest_file(path: Path, max_words: int = DEFAULT_MAX_WORDS) -> int:
    """Parse, chunk, embed and upsert one document. Returns fragments upserted."""
    source = path.name
    chunks = chunk_text(extract_text(path), max_words=max_words)
    if not chunks:
        return 0

    _ensure_collection()
    points = [
        PointStruct(
            id=_point_id(source, index),
            vector=embed(chunk),
            payload={"text": chunk, "source": source},
        )
        for index, chunk in enumerate(chunks)
    ]
    _qdrant_client().upsert(collection_name=config.QDRANT_COLLECTION, points=points)
    return len(points)


def ingest_path(path: Path, max_words: int = DEFAULT_MAX_WORDS) -> int:
    """Ingest a single file or every supported file under a directory."""
    if path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.suffix.lower() in SUPPORTED_EXTENSIONS)
    else:
        files = [path]

    total = 0
    for file in files:
        count = ingest_file(file, max_words=max_words)
        print(f"{file}: {count} fragments")
        total += count
    return total


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage: python -m app.ingest <path-to-file-or-directory>", file=sys.stderr)
        return 2
    target = Path(args[0])
    if not target.exists():
        print(f"Path not found: {target}", file=sys.stderr)
        return 1
    total = ingest_path(target)
    print(f"Done. {total} fragments ingested.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
