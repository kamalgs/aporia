from fastapi import APIRouter, HTTPException

from app.content_registry.registry import registry as get_registry
from app.domain.content import CoachProfile, GuardianProfile, Program, Skill

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/skills", response_model=list[Skill])
async def list_skills() -> list[Skill]:
    return get_registry().skills()


@router.get("/skills/{artifact_id}", response_model=Skill)
async def get_skill(artifact_id: str) -> Skill:
    item = get_registry().skill(artifact_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return item


@router.get("/programs", response_model=list[Program])
async def list_programs() -> list[Program]:
    return get_registry().programs()


@router.get("/programs/{artifact_id}", response_model=Program)
async def get_program(artifact_id: str) -> Program:
    item = get_registry().program(artifact_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return item


@router.get("/coach_profiles", response_model=list[CoachProfile])
async def list_coach_profiles() -> list[CoachProfile]:
    return get_registry().coach_profiles()


@router.get("/coach_profiles/{artifact_id}", response_model=CoachProfile)
async def get_coach_profile(artifact_id: str) -> CoachProfile:
    item = get_registry().coach_profile(artifact_id)
    if item is None:
        raise HTTPException(status_code=404, detail="CoachProfile not found")
    return item


@router.get("/guardian_profiles", response_model=list[GuardianProfile])
async def list_guardian_profiles() -> list[GuardianProfile]:
    return get_registry().guardian_profiles()


@router.get("/guardian_profiles/{artifact_id}", response_model=GuardianProfile)
async def get_guardian_profile(artifact_id: str) -> GuardianProfile:
    item = get_registry().guardian_profile(artifact_id)
    if item is None:
        raise HTTPException(status_code=404, detail="GuardianProfile not found")
    return item
