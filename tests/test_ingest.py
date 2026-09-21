"""Unit tests for app.ingest — all external clients mocked, no network."""

from unittest.mock import MagicMock

import pytest

import app.ingest as ingest


def test_extract_text_txt(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("Hello world\nsecond line", encoding="utf-8")
    assert ingest.extract_text(p) == "Hello world\nsecond line"


def test_extract_text_md(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# Title\n\nbody text", encoding="utf-8")
    assert ingest.extract_text(p) == "# Title\n\nbody text"


def test_extract_text_unsupported_extension(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("x,y", encoding="utf-8")
    with pytest.raises(ValueError):
        ingest.extract_text(p)


def test_chunk_text_packs_paragraphs():
    text = "para one here\n\npara two here\n\npara three here"
    chunks = ingest.chunk_text(text, max_words=100)
    assert chunks == ["para one here\n\npara two here\n\npara three here"]


def test_chunk_text_splits_when_over_budget():
    text = "\n\n".join(f"word{i}a word{i}b" for i in range(5))
    chunks = ingest.chunk_text(text, max_words=4)
    # 5 paragraphs of 2 words each, budget 4 words -> 2 paragraphs per chunk.
    assert len(chunks) == 3
    assert all(chunk.strip() for chunk in chunks)


def test_chunk_text_splits_oversized_single_paragraph():
    text = " ".join(f"w{i}" for i in range(10))
    chunks = ingest.chunk_text(text, max_words=4)
    assert len(chunks) == 3
    assert chunks[0] == "w0 w1 w2 w3"


def test_chunk_text_empty():
    assert ingest.chunk_text("   \n\n  ") == []


def test_chunk_text_starts_new_chunk_at_each_heading():
    # Multi-section doc well under a single max_words budget: without heading
    # splitting this would collapse into one chunk (issue #28 — large mixed
    # fragments dilute embedding specificity and miss retrieval).
    sections = [
        f"### Section {i}\n\n" + " ".join(f"s{i}w{j}" for j in range(20)) for i in range(4)
    ]
    text = "## Serveis\n\n" + "\n\n".join(sections)
    chunks = ingest.chunk_text(text, max_words=300)
    assert len(chunks) == 4
    # Each section's heading stays attached to its own body.
    for i, chunk in enumerate(chunks):
        assert f"### Section {i}" in chunk
        assert f"s{i}w0" in chunk
    # A heading with no body yet (the leading "##") rides into the next chunk
    # instead of becoming a heading-only fragment.
    assert chunks[0].startswith("## Serveis")


def test_chunk_text_heading_sections_still_respect_word_budget():
    body = " ".join(f"w{j}" for j in range(10))
    text = f"### Only section\n\n{body}"
    chunks = ingest.chunk_text(text, max_words=4)
    assert len(chunks) == 3
    # The pending heading attaches to the body's first slice instead of being
    # emitted as a heading-only fragment.
    assert chunks[0] == "### Only section\n\nw0 w1 w2 w3"
    assert chunks[1] == "w4 w5 w6 w7"


def test_chunk_text_splits_when_heading_and_body_share_a_paragraph():
    # Real KB style (the knowledge base §4): the heading is followed by
    # the body on the next line, no blank line between them. Each such
    # paragraph still starts its own fragment.
    sections = [
        f"### 4.{i} Section\n**Què fem:** " + " ".join(f"s{i}w{j}" for j in range(20))
        for i in range(3)
    ]
    chunks = ingest.chunk_text("\n\n".join(sections), max_words=300)
    assert len(chunks) == 3
    for i, chunk in enumerate(chunks):
        assert chunk.startswith(f"### 4.{i} Section")


def test_chunk_text_hash_word_is_not_a_heading():
    text = "#1 al sector en assessoria\n\nsegon paràgraf curt"
    chunks = ingest.chunk_text(text, max_words=300)
    assert chunks == ["#1 al sector en assessoria\n\nsegon paràgraf curt"]


def test_point_id_is_stable_and_source_indexed():
    a = ingest._point_id("guide.pdf", 0)
    b = ingest._point_id("guide.pdf", 0)
    c = ingest._point_id("guide.pdf", 1)
    d = ingest._point_id("other.pdf", 0)
    assert a == b
    assert a != c
    assert a != d


def test_ingest_file_upserts_chunks(tmp_path, monkeypatch):
    p = tmp_path / "kb.txt"
    p.write_text("alpha beta\n\ngamma delta", encoding="utf-8")

    monkeypatch.setattr(ingest, "_ensure_collection", lambda: None)
    monkeypatch.setattr(ingest, "embed", lambda text: [0.0] * 1536)
    qdrant = MagicMock()
    monkeypatch.setattr(ingest, "_qdrant_client", lambda: qdrant)

    count = ingest.ingest_file(p, max_words=2)

    assert count == 2
    assert qdrant.upsert.called
    _, kwargs = qdrant.upsert.call_args
    points = kwargs["points"]
    assert len(points) == 2
    assert points[0].payload["text"] == "alpha beta"
    assert points[0].payload["source"] == "kb.txt"
    # Stable id derived from source + index.
    assert points[0].id == ingest._point_id("kb.txt", 0)


def test_ingest_file_empty_document_upserts_nothing(tmp_path, monkeypatch):
    p = tmp_path / "empty.txt"
    p.write_text("   \n\n  ", encoding="utf-8")
    monkeypatch.setattr(ingest, "_ensure_collection", lambda: None)
    monkeypatch.setattr(ingest, "embed", lambda text: [0.0] * 1536)
    qdrant = MagicMock()
    monkeypatch.setattr(ingest, "_qdrant_client", lambda: qdrant)

    count = ingest.ingest_file(p)

    assert count == 0
    qdrant.upsert.assert_not_called()


def test_ingest_path_walks_directory(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "b.md").write_text("bravo", encoding="utf-8")
    (tmp_path / "skip.csv").write_text("nope", encoding="utf-8")

    seen = []
    monkeypatch.setattr(ingest, "ingest_file", lambda path, **k: seen.append(path.name) or 1)

    total = ingest.ingest_path(tmp_path)

    assert total == 2
    assert sorted(seen) == ["a.txt", "b.md"]
