from pathlib import Path
from ingest.parse import extract_pages
from ingest.chunker import build_chunks

PDF = Path("reports/fy25-press-release-eng-12022026.pdf")

def pages():
    return extract_pages(PDF)

def test_extract_pages_count_and_content():
    p = pages()
    assert len(p) == 14
    assert "FY25 HIGHLIGHTS" in p[0]["text"]
    assert p[0]["page"] == 1

def test_chunks_have_metadata_and_size():
    chunks = build_chunks(pages())
    assert len(chunks) >= 20
    for c in chunks:
        assert c["chunk_id"] and c["section"] and c["page"] >= 1
        assert 0 < len(c["text"]) <= 1600

def test_table_and_glossary_pages_excluded():
    chunks = build_chunks(pages())
    assert all(c["page"] not in (12, 13, 14) for c in chunks)
    assert not any("978,799" in c["text"] for c in chunks)  # table row only on p13

def test_sections_detected():
    sections = {c["section"] for c in build_chunks(pages())}
    assert "INCOME STATEMENT" in sections
    assert "BALANCE SHEET" in sections
    assert "FY25 HIGHLIGHTS" in sections
