"""Unit tests for the pure worker extraction function."""

from multiprocessing.shared_memory import SharedMemory
import pymupdf

from extractor.services.worker import extract_pdf_from_shm


def _make_pdf(text: str = "Hello World") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    tw = pymupdf.TextWriter(page.rect)
    tw.append((72, 72), text)
    tw.write_text(page)
    data = doc.tobytes()
    doc.close()
    return data


class TestExtractPdfFromShm:
    """Tests for ``extract_pdf_from_shm``."""

    def test_returns_content_and_page_count(self) -> None:
        pdf_bytes = _make_pdf()
        shm = SharedMemory(create=True, size=len(pdf_bytes))
        try:
            shm.buf[: len(pdf_bytes)] = pdf_bytes
            result = extract_pdf_from_shm(shm.name, len(pdf_bytes))

            assert "content" in result
            assert "page_count" in result
            assert result["page_count"] == 1
        finally:
            try:
                shm.buf.release()
            except Exception:
                pass
            shm.close()
            shm.unlink()

    def test_content_contains_page_header(self) -> None:
        pdf_bytes = _make_pdf()
        shm = SharedMemory(create=True, size=len(pdf_bytes))
        try:
            shm.buf[: len(pdf_bytes)] = pdf_bytes
            result = extract_pdf_from_shm(shm.name, len(pdf_bytes))

            assert "## Página 1" in result["content"]
        finally:
            try:
                shm.buf.release()
            except Exception:
                pass
            shm.close()
            shm.unlink()

    def test_content_contains_extracted_text(self) -> None:
        pdf_bytes = _make_pdf("Test extraction text")
        shm = SharedMemory(create=True, size=len(pdf_bytes))
        try:
            shm.buf[: len(pdf_bytes)] = pdf_bytes
            result = extract_pdf_from_shm(shm.name, len(pdf_bytes))

            assert "Test extraction text" in result["content"]
        finally:
            try:
                shm.buf.release()
            except Exception:
                pass
            shm.close()
            shm.unlink()

    def test_multi_page_extraction(self) -> None:
        doc = pymupdf.open()
        for i in range(3):
            page = doc.new_page()
            tw = pymupdf.TextWriter(page.rect)
            tw.append((72, 72), f"Page {i + 1} text")
            tw.write_text(page)
        pdf_bytes = doc.tobytes()
        doc.close()

        shm = SharedMemory(create=True, size=len(pdf_bytes))
        try:
            shm.buf[: len(pdf_bytes)] = pdf_bytes
            result = extract_pdf_from_shm(shm.name, len(pdf_bytes))

            assert result["page_count"] == 3
            assert "## Página 1" in result["content"]
            assert "## Página 2" in result["content"]
            assert "## Página 3" in result["content"]
        finally:
            try:
                shm.buf.release()
            except Exception:
                pass
            shm.close()
            shm.unlink()
