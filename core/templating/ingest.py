"""Template input modes → a single raw template-text string.

Three modes converge on one string that :func:`core.templating.spec.
parse_template` then structures:

  * ``text``  — pasted string, used verbatim
  * ``file``  — ``.md`` / ``.txt`` upload, decoded UTF-8
  * ``image`` — ``.png`` / ``.jpg`` / … OCR'd to text via the existing
                Tesseract stack (no new dependency, no LLM egress)

JAMES ships zero templates (CLAUDE.md rule #1); this module only
*transports* operator-supplied bytes into text — it has no knowledge of
what the template is for. See ``docs/design/v0.6-template-formatting-ui.md``
§3 and ARCHITECTURE §5.7.14.

The image path deliberately reuses the same Tesseract configuration as
``processors/file_processor.py`` (``lang="kor+eng"``, ``--psm 6``) so
no new OCR dependency is introduced and the bytes never leave the box.
"""
from __future__ import annotations

import os

from core.templating.store import TemplateStoreError

# Text-file extensions accepted by the `file` mode.
_TEXT_EXTS = (".md", ".markdown", ".txt", ".text")
# Image extensions accepted by the `image` (OCR) mode — mirrors the
# multimodal stack's supported set (tools/multimodal/image_analyzer).
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff")


def _ext(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


def ingest_text(raw_text: str) -> str:
    """Pasted-text mode: return the string verbatim (validated non-empty)."""
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise TemplateStoreError("template text must be non-empty")
    return raw_text


def ingest_file(data: bytes, filename: str = "") -> str:
    """File mode: decode an uploaded ``.md`` / ``.txt`` as UTF-8."""
    ext = _ext(filename)
    if ext and ext not in _TEXT_EXTS:
        raise TemplateStoreError(
            f"file mode expects a text file {_TEXT_EXTS}, got {ext!r}"
        )
    try:
        text = data.decode("utf-8")
    except (UnicodeDecodeError, AttributeError) as e:
        raise TemplateStoreError(f"file is not valid UTF-8 text: {e}")
    if not text.strip():
        raise TemplateStoreError("file is empty")
    return text


def ingest_image(image_path: str) -> str:
    """Image mode: OCR an image file to raw template text.

    Uses Tesseract (kor+eng, ``--psm 6``) exactly like
    ``processors/file_processor.py`` — no new dependency, no LLM egress.
    Raises :class:`TemplateStoreError` if the OCR stack is unavailable
    or the image yields no text.
    """
    ext = _ext(image_path)
    if ext and ext not in _IMAGE_EXTS:
        raise TemplateStoreError(
            f"image mode expects an image {_IMAGE_EXTS}, got {ext!r}"
        )
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        raise TemplateStoreError(f"OCR stack unavailable: {e}")

    # Honour the operator-configured Tesseract binary path, same as
    # config.py / file_processor.py do.
    try:
        from config import TESSERACT_PATH
        if TESSERACT_PATH:
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
    except Exception:
        pass

    try:
        img = Image.open(image_path).convert("L")
        text = pytesseract.image_to_string(
            img, lang="kor+eng", config="--psm 6"
        )
    except Exception as e:
        raise TemplateStoreError(f"OCR failed: {e}")

    if not text.strip():
        raise TemplateStoreError("OCR produced no text from the image")
    return text


# ── v0.6.1 — document ingest (`.docx` / `.pdf` / `.pptx` / `.xlsx`) ─

# Office / PDF extensions handled by markitdown (already a JAMES
# dependency for the chat answer-export feature). Lightweight call —
# no heavy FileProcessor / cv2 / whisper imports, per design memo §1.
_DOC_EXTS = (".docx", ".doc", ".pdf", ".pptx", ".xlsx", ".hwp", ".hwpx")


def ingest_document(file_path: str) -> str:
    """Document mode: extract text from an office / PDF file.

    Uses ``markitdown`` (already a JAMES dep) — supports `.docx /
    .pdf / .pptx / .xlsx` natively. `.hwp` / `.hwpx` falls through to
    markitdown's attempt; many builds return empty text, in which
    case the caller surfaces an explicit error pointing the operator
    at the "한글에서 .docx 로 저장 후 업로드" workaround. No new
    dependency, no LLM egress; the bytes never leave the box.
    """
    ext = _ext(file_path)
    if ext and ext not in _DOC_EXTS:
        raise TemplateStoreError(
            f"document mode expects an office / PDF file {_DOC_EXTS}, got {ext!r}"
        )
    try:
        from markitdown import MarkItDown
    except ImportError as e:
        raise TemplateStoreError(f"document stack unavailable: {e}")

    try:
        md = MarkItDown()
        result = md.convert(file_path)
        text = (getattr(result, "text_content", "") or "").strip()
    except Exception as e:
        # `.hwp` typically lands here on builds where markitdown has no
        # parser. Honest error — point to the workaround.
        if ext in (".hwp", ".hwpx"):
            raise TemplateStoreError(
                "`.hwp` extraction failed in this build of markitdown. "
                "Workaround: open the file in 한글 / 한컴오피스 and "
                "save as `.docx` (다른 이름으로 저장 → Word 문서), then "
                "upload the `.docx`."
            )
        raise TemplateStoreError(f"document extraction failed: {e}")

    if not text:
        if ext in (".hwp", ".hwpx"):
            raise TemplateStoreError(
                "`.hwp` produced no extractable text. "
                "Workaround: open in 한글 and save as `.docx`, then upload."
            )
        raise TemplateStoreError("document produced no extractable text")
    return text


__all__ = ["ingest_text", "ingest_file", "ingest_image", "ingest_document"]
