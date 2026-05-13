from pydantic import BaseModel


class Skill(BaseModel):
    id: str
    title: str
    objective: str
    mastery_description: str = ""
    common_mistakes: list[str] = []
    sample_exchanges: list[dict] = []
    tags: list[str] = []
    raw_md: str = ""


class Program(BaseModel):
    id: str
    title: str
    description: str = ""
    skill_ids: list[str] = []
    mandatory_skill_ids: list[str] = []
    assessment_criteria: str = ""
    coach_profile_id: str = ""
    raw_md: str = ""


class CoachProfile(BaseModel):
    id: str
    title: str
    tone: str = ""
    pacing: str = ""
    raw_md: str = ""


class GuardianProfile(BaseModel):
    id: str
    title: str
    cohort_description: str = ""
    cohort_tags: list[str] = []
    defaults: dict = {}
    raw_md: str = ""
