from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.database import get_db
from backend.services.search import Embedder, EmbeddingUnavailable, search

router = APIRouter(prefix="/search", tags=["search"])
Database = Annotated[Session, Depends(get_db)]


class SearchResult(BaseModel):
    path: str
    snippet: str
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    indexed_files: int
    indexed_chunks: int
    newly_indexed: int


# A plain (sync) endpoint: FastAPI runs it in a worker thread, so embedding
# files never blocks other requests on the event loop.
@router.get("", response_model=SearchResponse)
def search_files(
    db: Database,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> SearchResponse:
    settings = get_settings()
    try:
        hits, stats = search(db, settings, Embedder(settings), q, limit)
    except EmbeddingUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return SearchResponse(
        query=q,
        results=[SearchResult(path=hit.path, snippet=hit.snippet, score=hit.score) for hit in hits],
        indexed_files=stats.files,
        indexed_chunks=stats.chunks,
        newly_indexed=stats.embedded_files,
    )
