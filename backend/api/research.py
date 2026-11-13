from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.database import get_db
from backend.models.schemas import ResearchRequest, ResearchResponse
from backend.security.content import isolate_untrusted_content, record_scan
from backend.services.ollama import OllamaClient, OllamaUnavailable
from backend.services.research import ResearchUnavailable, WikipediaResearch

router = APIRouter(prefix="/research", tags=["research"])
Database = Annotated[Session, Depends(get_db)]


@router.post("", response_model=ResearchResponse)
async def research(payload: ResearchRequest, db: Database) -> ResearchResponse:
    try:
        sources = await WikipediaResearch().collect(payload.query, payload.max_sources)
        safe_sources = []
        for item in sources:
            result = record_scan(db, item["excerpt"], item["url"])
            if result.safe:
                safe_sources.append(item)
        if not safe_sources:
            raise HTTPException(
                status_code=422,
                detail="All retrieved sources were quarantined by prompt-injection protection.",
            )
        sources = safe_sources
        source_text = "\n\n".join(
            f"SOURCE {index}: {item['title']}\nURL: {item['url']}\n"
            f"{isolate_untrusted_content(item['excerpt'], item['url'])}"
            for index, item in enumerate(sources, start=1)
        )
        prompt = (
            f"Prepare a concise, factual research report about: {payload.query}\n\n"
            "Use only the source material below. Cite factual claims with [Source N]. "
            "Separate verified facts from any inference and end with a short conclusion.\n\n"
            f"{source_text}"
        )
        report = await OllamaClient(get_settings()).chat(
            [{"role": "user", "content": prompt}], memories=[]
        )
    except ResearchUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except OllamaUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ResearchResponse(query=payload.query, report=report, sources=sources)
