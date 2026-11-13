"""Search the workspace by meaning, using a local Ollama embedding model.

Files are split into overlapping chunks; each chunk is embedded once and stored
as a unit-length float32 vector. A search embeds the query and ranks chunks by
cosine similarity (a dot product, since vectors are normalized). Before every
search the index is synced with the folder: new and changed files are embedded,
deleted files are dropped, unchanged files cost only a stat() call.

Everything stays on this machine; no new Python dependency is needed.
"""

import hashlib
import heapq
import math
from array import array
from dataclasses import dataclass

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.database import SessionLocal
from backend.models.entities import DocumentChunk, IndexedFile, now_utc
from backend.services.http import tls_context
from backend.services.tools import ToolError, ToolResult, _workspace

CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150
MAX_CHUNKS_PER_FILE = 200
EMBED_BATCH = 16
# nomic-embed-text was trained with these task prefixes; they improve ranking.
DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


class EmbeddingUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class SearchHit:
    path: str
    snippet: str
    score: float


@dataclass(frozen=True)
class IndexStats:
    files: int
    chunks: int
    embedded_files: int
    removed_files: int


class Embedder:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self.settings.embedding_model
        vectors: list[list[float]] = []
        try:
            with httpx.Client(timeout=120, transport=self.transport, verify=tls_context()) as client:
                for start in range(0, len(texts), EMBED_BATCH):
                    batch = texts[start:start + EMBED_BATCH]
                    response = client.post(
                        f"{self.settings.ollama_url}/api/embed", json={"model": model, "input": batch}
                    )
                    if response.status_code == 404:
                        raise EmbeddingUnavailable(
                            f"The embedding model “{model}” isn’t installed. Run: ollama pull {model}"
                        )
                    response.raise_for_status()
                    vectors.extend(response.json()["embeddings"])
        except (httpx.HTTPError, OSError, KeyError, ValueError) as exc:
            raise EmbeddingUnavailable(
                "Ollama isn’t reachable, so files can’t be searched. Start Ollama and try again."
            ) from exc
        if len(vectors) != len(texts):
            raise EmbeddingUnavailable("Ollama returned the wrong number of embeddings.")
        return vectors


def _pack(vector: list[float]) -> bytes:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return array("f", (value / norm for value in vector)).tobytes()


def _unpack(blob: bytes) -> array:
    vector = array("f")
    vector.frombytes(blob)
    return vector


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks, preferring to break at a newline or space."""
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text) and len(chunks) < MAX_CHUNKS_PER_FILE:
        end = min(start + CHUNK_CHARS, len(text))
        if end < len(text):
            window = text[start:end]
            cut = max(window.rfind("\n"), window.rfind(" "))
            if cut > CHUNK_CHARS // 2:
                end = start + cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def sync_index(db: Session, settings: Settings, embedder: Embedder) -> IndexStats:
    root = _workspace(settings)
    on_disk = {}
    for item in root.rglob("*"):
        if item.is_file() and not item.is_symlink():
            on_disk[item.relative_to(root).as_posix()] = item

    indexed = {row.path: row for row in db.scalars(select(IndexedFile)).all()}
    embedded = removed = 0

    for path in set(indexed) - set(on_disk):
        db.execute(delete(DocumentChunk).where(DocumentChunk.path == path))
        db.delete(indexed.pop(path))
        removed += 1

    for path, file in sorted(on_disk.items()):
        stat = file.stat()
        row = indexed.get(path)
        if row and row.model == settings.embedding_model and row.size == stat.st_size and row.modified_at == stat.st_mtime:
            continue
        if stat.st_size > settings.max_file_bytes:
            continue
        raw = file.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if row and row.model == settings.embedding_model and row.content_hash == digest:
            row.size, row.modified_at = stat.st_size, stat.st_mtime  # touched, not changed
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue  # binary files aren't searchable
        chunks = chunk_text(text)
        vectors = embedder.embed([DOCUMENT_PREFIX + chunk for chunk in chunks]) if chunks else []
        db.execute(delete(DocumentChunk).where(DocumentChunk.path == path))
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            db.add(DocumentChunk(path=path, chunk_index=index, content=chunk, embedding=_pack(vector)))
        if row is None:
            row = IndexedFile(path=path, content_hash=digest, model=settings.embedding_model)
            db.add(row)
            indexed[path] = row
        row.size, row.modified_at, row.content_hash = stat.st_size, stat.st_mtime, digest
        row.model, row.indexed_at = settings.embedding_model, now_utc()
        embedded += 1

    db.commit()
    chunks = int(db.scalar(select(func.count()).select_from(DocumentChunk)) or 0)
    return IndexStats(files=len(indexed), chunks=chunks, embedded_files=embedded, removed_files=removed)


def search(
    db: Session, settings: Settings, embedder: Embedder, query: str, limit: int = 5
) -> tuple[list[SearchHit], IndexStats]:
    """Best-matching chunk per file, highest score first."""
    stats = sync_index(db, settings, embedder)
    if not stats.chunks or not query.strip():
        return [], stats
    query_vector = _unpack(_pack(embedder.embed([QUERY_PREFIX + query.strip()])[0]))
    best: dict[str, tuple[float, str]] = {}
    for path, content, blob in db.execute(select(DocumentChunk.path, DocumentChunk.content, DocumentChunk.embedding)):
        vector = _unpack(blob)
        if len(vector) != len(query_vector):
            continue
        score = sum(a * b for a, b in zip(query_vector, vector, strict=True))
        if path not in best or score > best[path][0]:
            best[path] = (score, content)
    top = heapq.nlargest(limit, best.items(), key=lambda item: item[1][0])
    hits = [SearchHit(path, content[:400], round(score, 4)) for path, (score, content) in top]
    return hits, stats


def search_workspace(settings: Settings, arguments: dict, embedder: Embedder | None = None) -> ToolResult:
    """The search_files tool: same search, opened in its own database session."""
    query = str(arguments.get("query", "")).strip()
    if not query:
        raise ToolError("A search query is required.")
    with SessionLocal() as db:
        try:
            hits, _ = search(db, settings, embedder or Embedder(settings), query, limit=5)
        except EmbeddingUnavailable as exc:
            raise ToolError(str(exc)) from exc
    return ToolResult(
        f"Found {len(hits)} results, closest first.",
        [{"path": hit.path, "snippet": hit.snippet, "score": hit.score} for hit in hits],
    )
