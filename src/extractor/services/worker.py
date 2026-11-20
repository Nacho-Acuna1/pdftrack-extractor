"""Pure extraction function executed in a subprocess via ProcessPoolExecutor.

This module is intentionally self-contained: ``pymupdf`` is imported
inside the function so the main process never loads it.
"""

import gc
from multiprocessing.shared_memory import SharedMemory


def extract_pdf_from_shm(shm_name: str, size: int) -> dict:
    """Open a PDF from a SharedMemory segment and extract text page by page.

    The caller creates the segment, copies the raw PDF bytes into it, and
    passes only the *shm_name* and *size* — no pickle serialisation of the
    PDF payload (Zero-Copy IPC).

    Args:
        shm_name: Name of the ``SharedMemory`` segment containing the PDF.
        size: Number of valid bytes in the segment.

    Returns:
        ``{"content": "## Página 1\\n\\n…", "page_count": N}``
    """
    import pymupdf  # noqa: PLC0415

    shm = SharedMemory(name=shm_name, create=False)
    buf_slice = shm.buf[:size]
    doc = None
    try:
        doc = pymupdf.open(stream=buf_slice, filetype="pdf")
        pages: list[str] = []
        for i, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            pages.append(f"## Página {i}\n\n{text}")
        content = "\n\n".join(pages)
        return {"content": content, "page_count": len(doc)}
    finally:
        if doc is not None:
            doc.close()
        del doc
        del buf_slice
        gc.collect()
        try:
            shm.buf.release()
        except Exception:
            pass
        shm.close()
