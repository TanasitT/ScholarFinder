from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from reviewerfinder.api.deps import get_scholar_repository
from reviewerfinder.db.repository import ScholarRepository
from reviewerfinder.models import Scholar

router = APIRouter(prefix="/api/scholars", tags=["scholars"])


@router.get("/{scholar_id}", response_model=Scholar)
def get_scholar(
    scholar_id: str,
    scholar_repo: ScholarRepository = Depends(get_scholar_repository),
) -> Scholar:
    scholar = scholar_repo.get(scholar_id)
    if scholar is None:
        raise HTTPException(status_code=404, detail=f"No scholar with id {scholar_id}")
    return scholar
