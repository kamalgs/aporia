from fastapi import APIRouter, HTTPException

from app.domain.learner import Learner, LearnerCreate
from app.store import learners as learners_store

router = APIRouter(prefix="/learners", tags=["learners"])


@router.post("", response_model=Learner, status_code=201)
async def create_learner(body: LearnerCreate) -> Learner:
    return await learners_store.insert(body)


@router.get("/{learner_id}", response_model=Learner)
async def get_learner(learner_id: str) -> Learner:
    learner = await learners_store.get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    return learner
