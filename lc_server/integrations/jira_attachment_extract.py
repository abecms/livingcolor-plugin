"""Download Jira ticket attachments and extract text for delivery agents."""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from lc_constants import get_livingcolor_home

logger = logging.getLogger(__name__)

MAX_ATTACHMENTS = 8
MAX_TEXT_CHARS = 12_000
MAX_IMAGE_BYTES = 8 * 1024 * 1024
VISION_PROMPT = (
    "This image is a Jira ticket attachment. Describe everything visible that helps "
    "understand the bug or feature request: UI text, labels, error messages, expected "
    "vs actual behavior, URLs, page titles, and any annotations. Be specific and factual."
)

_TEXT_MIME_PREFIXES = ("text/", "application/json", "application/xml", "application/javascript")
_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".xml",
    ".csv",
    ".log",
    ".html",
    ".htm",
    ".yaml",
    ".yml",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".css",
    ".sql",
}


def enrich_snapshot_with_attachment_extracts(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Add attachmentExtracts to a Jira snapshot when attachments are present."""
    enriched = dict(snapshot)
    existing = enriched.get("attachmentExtracts")
    if _attachment_extracts_usable(existing):
        return enriched

    attachments = enriched.get("attachments")
    if not isinstance(attachments, list) or not attachments:
        return enriched

    issue_key = str(enriched.get("key") or "").strip()
    if not issue_key:
        return enriched

    try:
        enriched["attachmentExtracts"] = extract_jira_attachment_context(issue_key, attachments)
    except Exception as exc:
        logger.warning("Jira attachment extraction failed for %s: %s", issue_key, exc)
        enriched["attachmentExtracts"] = [
            {
                "name": str(item.get("name") or "attachment"),
                "mimeType": str(item.get("mimeType") or ""),
                "extractKind": "error",
                "content": "",
                "error": str(exc),
            }
            for item in attachments[:MAX_ATTACHMENTS]
            if isinstance(item, dict)
        ]
    return enriched


def _attachment_extracts_usable(raw: Any) -> bool:
    if not isinstance(raw, list) or not raw:
        return False
    for item in raw:
        if not isinstance(item, dict):
            continue
        if str(item.get("content") or "").strip():
            return True
        kind = str(item.get("extractKind") or "")
        if kind in {"text", "image_description", "pdf_text", "pdf_vision_fallback"}:
            return True
    return False


def merge_attachment_context_into_pack(
    context_pack: dict[str, Any],
    jira_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """Ensure context pack carries attachment extracts before developer planning/execution."""
    pack = dict(context_pack or {})
    if pack.get("jira_attachment_extracts"):
        return pack

    snapshot = dict(jira_snapshot or {})
    attachments = snapshot.get("attachments")
    if not isinstance(attachments, list) or not attachments:
        return pack

    enriched = enrich_snapshot_with_attachment_extracts(snapshot)
    extracts = enriched.get("attachmentExtracts")
    if isinstance(extracts, list) and extracts:
        pack["jira_attachment_extracts"] = extracts

    ticket = dict(pack.get("jira_ticket") or {})
    if isinstance(enriched.get("attachments"), list):
        ticket["attachments"] = enriched["attachments"]
    if enriched.get("description") and not str(ticket.get("description") or "").strip():
        ticket["description"] = enriched["description"]
    pack["jira_ticket"] = ticket

    if not pack.get("jira_comments") and isinstance(enriched.get("comments"), list):
        pack["jira_comments"] = enriched["comments"]

    return pack


def extract_jira_attachment_context(issue_key: str, attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Download and extract content from Jira attachment metadata records."""
    safe_key = str(issue_key or "").strip()
    if not safe_key:
        return []

    extracts: list[dict[str, Any]] = []
    for item in attachments[:MAX_ATTACHMENTS]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("filename") or "attachment").strip()
        attachment_id = str(item.get("id") or "").strip()
        mime_type = str(item.get("mimeType") or item.get("mime_type") or "").strip().lower()
        try:
            extracts.append(
                _extract_one_attachment(
                    safe_key,
                    name,
                    attachment_id,
                    mime_type,
                    attachment_url=str(item.get("url") or ""),
                )
            )
        except Exception as exc:
            logger.warning("Failed to extract Jira attachment %s on %s: %s", name, safe_key, exc)
            extracts.append(
                {
                    "name": name,
                    "mimeType": mime_type,
                    "extractKind": "error",
                    "content": "",
                    "error": str(exc),
                }
            )
    return extracts


def _extract_one_attachment(
    issue_key: str,
    name: str,
    attachment_id: str,
    mime_type: str,
    *,
    attachment_url: str = "",
) -> dict[str, Any]:
    from hermes_cli.jira_dashboard import JiraDashboardError, fetch_jira_attachment_preview

    raw_bytes: bytes | None = None
    resolved_mime = mime_type or "application/octet-stream"
    last_error = ""

    try:
        raw_bytes, resolved_mime = fetch_jira_attachment_preview(
            issue_key,
            attachment_id=attachment_id,
            name=name,
        )
    except Exception as exc:
        last_error = str(exc)
        raw_bytes = _download_attachment_via_jira_api(attachment_url)
        if raw_bytes is None:
            return {
                "name": name,
                "mimeType": mime_type or "",
                "extractKind": "error",
                "content": "",
                "error": last_error or "Could not download attachment",
            }
        resolved_mime = mime_type or _guess_mime_type(name, raw_bytes)

    assert raw_bytes is not None
    local_path = _persist_attachment_bytes(issue_key, name, raw_bytes)
    resolved_mime = (resolved_mime or mime_type or "application/octet-stream").lower()

    if resolved_mime.startswith("image/"):
        if len(raw_bytes) > MAX_IMAGE_BYTES:
            return {
                "name": name,
                "mimeType": resolved_mime,
                "extractKind": "skipped",
                "content": "",
                "localPath": str(local_path),
                "error": f"Image exceeds {MAX_IMAGE_BYTES} byte limit",
            }
        description = _describe_image_attachment(local_path)
        return {
            "name": name,
            "mimeType": resolved_mime,
            "extractKind": "image_description",
            "content": description,
            "localPath": str(local_path),
        }

    if _is_text_attachment(resolved_mime, name):
        text = _decode_text_bytes(raw_bytes)
        return {
            "name": name,
            "mimeType": resolved_mime,
            "extractKind": "text",
            "content": text[:MAX_TEXT_CHARS],
            "localPath": str(local_path),
        }

    if resolved_mime == "application/pdf" or name.lower().endswith(".pdf"):
        pdf_text = _extract_pdf_text(raw_bytes)
        if pdf_text.strip():
            return {
                "name": name,
                "mimeType": resolved_mime,
                "extractKind": "pdf_text",
                "content": pdf_text[:MAX_TEXT_CHARS],
                "localPath": str(local_path),
            }
        return {
            "name": name,
            "mimeType": resolved_mime,
            "extractKind": "unsupported",
            "content": "",
            "localPath": str(local_path),
            "error": "PDF downloaded but no readable text or slide titles were extracted",
        }

    return {
        "name": name,
        "mimeType": resolved_mime,
        "extractKind": "unsupported",
        "content": "",
        "localPath": str(local_path),
        "error": "Unsupported attachment type for automatic extraction",
    }


def _is_text_attachment(mime_type: str, name: str) -> bool:
    if any(mime_type.startswith(prefix) for prefix in _TEXT_MIME_PREFIXES):
        return True
    suffix = Path(name).suffix.lower()
    return suffix in _TEXT_EXTENSIONS


def _decode_text_bytes(raw_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def _guess_mime_type(name: str, raw_bytes: bytes) -> str:
    if raw_bytes.startswith(b"%PDF"):
        return "application/pdf"
    if raw_bytes.startswith(b"\x89PNG"):
        return "image/png"
    if raw_bytes.startswith(b"\xff\xd8"):
        return "image/jpeg"
    guessed = mimetypes.guess_type(name)[0]
    return guessed or "application/octet-stream"


def _download_attachment_via_jira_api(url: str) -> bytes | None:
    safe_url = str(url or "").strip()
    if not safe_url:
        return None

    import base64
    import urllib.error
    import urllib.request

    from lc_server.integrations.mcp_server_resolver import active_jira_mcp_name
    from hermes_cli.mcp_config import _get_mcp_servers

    cfg = _get_mcp_servers().get(active_jira_mcp_name()) or {}
    env = cfg.get("env") if isinstance(cfg.get("env"), dict) else {}
    username = str(env.get("JIRA_USERNAME") or "").strip()
    token = str(env.get("JIRA_API_TOKEN") or "").strip()
    if not username or not token:
        return None

    credentials = base64.b64encode(f"{username}:{token}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        safe_url,
        headers={
            "Authorization": f"Basic {credentials}",
            "Accept": "*/*",
            "User-Agent": "LivingColor Server",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError:
        return None
    except urllib.error.URLError:
        return None


def _extract_pdf_text(raw_bytes: bytes) -> str:
    import io

    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore[no-redef]
        except ImportError:
            PdfReader = None  # type: ignore[misc, assignment]
    else:
        try:
            reader = PdfReader(io.BytesIO(raw_bytes))
            parts: list[str] = []
            for page in reader.pages[:20]:
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                if text.strip():
                    parts.append(text.strip())
            joined = "\n\n".join(parts).strip()
            if joined:
                return joined
        except Exception:
            pass

    return _extract_pdf_outline_titles(raw_bytes)


def _extract_pdf_outline_titles(raw_bytes: bytes) -> str:
    latin = raw_bytes.decode("latin-1", errors="ignore")
    titles: list[str] = []
    for match in re.finditer(r"/Title\(([^)]*)\)", latin):
        title = _decode_pdf_literal(match.group(1)).strip()
        if title and title not in titles:
            titles.append(title)
    if not titles:
        return ""
    return "\n".join(f"- {title}" for title in titles)


def _decode_pdf_literal(value: str) -> str:
    text = value.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
    try:
        return bytes(text, "utf-8").decode("unicode_escape")
    except Exception:
        return text


def _persist_attachment_bytes(issue_key: str, name: str, raw_bytes: bytes) -> Path:
    safe_name = _safe_filename(name)
    target_dir = get_livingcolor_home() / "jira-attachments" / _safe_filename(issue_key)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / safe_name
    target_path.write_bytes(raw_bytes)
    return target_path


def _run_async(coro: Any) -> Any:
    """Run a coroutine from sync code, even when an event loop is already active."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    def _run_in_thread() -> Any:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_run_in_thread).result()


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w.\-()+ ]+", "_", str(name or "attachment").strip())
    return cleaned[:180] or "attachment"


def _describe_image_attachment(local_path: Path) -> str:
    from tools.vision_tools import vision_analyze_tool

    try:
        raw_result = _run_async(
            vision_analyze_tool(
                str(local_path),
                VISION_PROMPT,
            )
        )
    except Exception as exc:
        logger.warning("Vision analysis failed for %s: %s", local_path, exc)
        return f"(Vision analysis failed: {exc})"

    text = str(raw_result or "").strip()
    if not text:
        return "(Vision analysis returned empty content)"

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text[:MAX_TEXT_CHARS]

    if isinstance(parsed, dict):
        for key in ("description", "analysis", "summary", "content", "text", "result"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:MAX_TEXT_CHARS]
        return json.dumps(parsed, ensure_ascii=False)[:MAX_TEXT_CHARS]
    if isinstance(parsed, str):
        return parsed[:MAX_TEXT_CHARS]
    return text[:MAX_TEXT_CHARS]


__all__ = [
    "enrich_snapshot_with_attachment_extracts",
    "extract_jira_attachment_context",
    "merge_attachment_context_into_pack",
]
