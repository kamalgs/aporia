from fastapi import APIRouter, HTTPException

from app.domain.tutor import Tutor, TutorCreate
from app.store import tutors as tutors_store

router = APIRouter(prefix="/tutors", tags=["tutors"])


@router.post("", response_model=Tutor, status_code=201)
async def create_tutor(body: TutorCreate) -> Tutor:
    return await tutors_store.insert(body)


@router.get("/{tutor_id}", response_model=Tutor)
async def get_tutor(tutor_id: str) -> Tutor:
    tutor = await tutors_store.get(tutor_id)
    if tutor is None:
        raise HTTPException(status_code=404, detail="Tutor not found")
    return tutor
