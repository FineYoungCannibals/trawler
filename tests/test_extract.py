"""Tests for trawler.search.extract — PDF/DOCX text extraction."""
from __future__ import annotations

from pathlib import Path

import pytest

from trawler.search.extract import EXTRACTABLE_EXTENSIONS, extract_text


# ---------------------------------------------------------------------------
# Plain text fallback
# ---------------------------------------------------------------------------

def test_plain_text_file_returned_as_is(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("hello world\nline two\n", encoding="utf-8")
    assert extract_text(f) == "hello world\nline two\n"


def test_unknown_extension_read_as_utf8(tmp_path):
    f = tmp_path / "data.log"
    f.write_text("log entry", encoding="utf-8")
    assert "log entry" in extract_text(f)


# ---------------------------------------------------------------------------
# EXTRACTABLE_EXTENSIONS constant
# ---------------------------------------------------------------------------

def test_extractable_extensions_contains_pdf_and_docx():
    assert ".pdf" in EXTRACTABLE_EXTENSIONS
    assert ".docx" in EXTRACTABLE_EXTENSIONS


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def _make_pdf(path: Path, text: str) -> Path:
    """Write a minimal single-page PDF with the given text."""
    pypdf = pytest.importorskip("pypdf")
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, ArrayObject, NumberObject, ByteStringObject

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)

    # Embed a simple text stream manually
    stream = (
        f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
    ).encode()
    page = writer.pages[0]
    # Add a font resource so the PDF is valid
    from pypdf.generic import DictionaryObject
    resources = DictionaryObject()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    resources[NameObject("/Font")] = DictionaryObject({NameObject("/F1"): font})
    page[NameObject("/Resources")] = resources
    from pypdf.generic import ContentStream, DecodedStreamObject
    stream_obj = DecodedStreamObject()
    stream_obj.set_data(stream)
    page[NameObject("/Contents")] = stream_obj

    with open(path, "wb") as f:
        writer.write(f)
    return path


def test_pdf_extraction_returns_string(tmp_path):
    """extract_text on a PDF file returns a str (may be empty for minimal PDF)."""
    pytest.importorskip("pypdf")
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")   # minimal (empty) PDF
    result = extract_text(pdf)
    assert isinstance(result, str)


def test_pdf_corrupt_returns_empty_string(tmp_path):
    """Corrupt PDF files return empty string rather than raising."""
    pdf = tmp_path / "bad.pdf"
    pdf.write_bytes(b"not a real pdf at all")
    result = extract_text(pdf)
    assert result == ""


# ---------------------------------------------------------------------------
# DOCX extraction
# ---------------------------------------------------------------------------

def _make_docx(path: Path, paragraphs: list[str]) -> Path:
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    for para in paragraphs:
        doc.add_paragraph(para)
    doc.save(path)
    return path


def test_docx_extraction_returns_paragraphs(tmp_path):
    pytest.importorskip("docx")
    docx_path = _make_docx(tmp_path / "test.docx", ["Hello world", "Second paragraph"])
    result = extract_text(docx_path)
    assert "Hello world" in result
    assert "Second paragraph" in result


def test_docx_table_cells_included(tmp_path):
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "username"
    table.cell(0, 1).text = "password123"
    path = tmp_path / "table.docx"
    doc.save(path)
    result = extract_text(path)
    assert "username" in result
    assert "password123" in result


def test_docx_corrupt_returns_empty_string(tmp_path):
    """Corrupt DOCX files return empty string rather than raising."""
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a zip file")
    result = extract_text(bad)
    assert result == ""
