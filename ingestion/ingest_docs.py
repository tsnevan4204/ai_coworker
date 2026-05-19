"""CLI: Google Drive folder → Unstructured → embed → Qdrant company_docs."""

from __future__ import annotations

import argparse
import asyncio
import io
import logging
import re
import uuid
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from unstructured.partition.auto import partition

from backend import embeddings, qdrant_search
from backend.config import get_settings

logger = logging.getLogger(__name__)

EXPORT_MIME = {
    "application/vnd.google-apps.document": "application/pdf",
    "application/vnd.google-apps.presentation": "application/pdf",
    "application/vnd.google-apps.spreadsheet": "text/csv",
}

SKIP_MIME = frozenset(
    {
        "application/vnd.google-apps.folder",
        "application/vnd.google-apps.form",
        "application/vnd.google-apps.map",
    }
)


def _google_creds() -> Credentials:
    settings = get_settings()
    return Credentials(
        token=None,
        refresh_token=settings.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )


def _list_files_recursive(drive, folder_id: str) -> list[dict]:
    files: list[dict] = []
    page_token = None
    query = f"'{folder_id}' in parents and trashed = false"
    while True:
        resp = (
            drive.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, webViewLink)",
                pageToken=page_token,
            )
            .execute()
        )
        for f in resp.get("files", []):
            if f["mimeType"] == "application/vnd.google-apps.folder":
                files.extend(_list_files_recursive(drive, f["id"]))
            else:
                files.append(f)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def _download_file(drive, file_meta: dict) -> tuple[bytes, str]:
    mime = file_meta["mimeType"]
    file_id = file_meta["id"]
    buf = io.BytesIO()

    if mime in EXPORT_MIME:
        export_mime = EXPORT_MIME[mime]
        request = drive.files().export_media(fileId=file_id, mimeType=export_mime)
        ext = ".pdf" if "pdf" in export_mime else ".csv"
    elif mime in SKIP_MIME:
        raise ValueError(f"skip {mime}")
    else:
        request = drive.files().get_media(fileId=file_id)
        ext = Path(file_meta["name"]).suffix or ".bin"
        export_mime = mime

    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue(), ext


def _chunk_text(elements, max_chars: int = 2000, overlap: int = 200) -> list[str]:
    full = "\n\n".join(getattr(el, "text", str(el)) for el in elements if getattr(el, "text", None))
    full = re.sub(r"\n{3,}", "\n\n", full).strip()
    if not full:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(full):
        end = start + max_chars
        chunks.append(full[start:end])
        start = end - overlap
    return chunks


async def ingest_folder(folder_id: str) -> None:
    await qdrant_search.ensure_collections()
    creds = _google_creds()
    drive = build("drive", "v3", credentials=creds)
    files = _list_files_recursive(drive, folder_id)
    logger.info("Found %d files in folder %s", len(files), folder_id)

    for f in files:
        mime = f["mimeType"]
        if mime in SKIP_MIME:
            continue
        try:
            content, ext = _download_file(drive, f)
        except ValueError:
            continue
        except Exception:
            logger.warning("Skip download %s (%s)", f.get("name"), mime, exc_info=True)
            continue

        tmp = Path(f"/tmp/yaco_{f['id']}{ext}")
        tmp.write_bytes(content)
        try:
            elements = partition(filename=str(tmp))
        except Exception:
            logger.warning("Skip parse %s", f.get("name"), exc_info=True)
            tmp.unlink(missing_ok=True)
            continue
        tmp.unlink(missing_ok=True)

        doc_id = str(uuid.uuid4())
        chunks = _chunk_text(elements)
        for i, text in enumerate(chunks):
            vector = await embeddings.embed(text)
            await qdrant_search.upsert_company_doc_chunk(
                vector,
                {
                    "title": f.get("name", ""),
                    "source": "google_drive",
                    "drive_url": f.get("webViewLink", ""),
                    "file_type": ext.lstrip("."),
                    "chunk_index": i,
                    "full_doc_id": doc_id,
                    "text": text[:500],
                },
            )
        logger.info("Ingested %s (%d chunks)", f.get("name"), len(chunks))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder-id", required=True)
    args = parser.parse_args()
    asyncio.run(ingest_folder(args.folder_id))


if __name__ == "__main__":
    main()
