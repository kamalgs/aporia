from pathlib import Path

from app.content_registry.loader import (
    load_coach_profiles,
    load_guardian_profiles,
    load_programs,
    load_skills,
)
from app.domain.content import CoachProfile, GuardianProfile, Program, Skill


class ContentRegistry:
    def __init__(self, content_dir: Path) -> None:
        self._skills: dict[str, Skill] = {}
        self._programs: dict[str, Program] = {}
        self._coach_profiles: dict[str, CoachProfile] = {}
        self._guardian_profiles: dict[str, GuardianProfile] = {}
        self.load(content_dir)

    def load(self, content_dir: Path) -> None:
        self._skills = {s.id: s for s in load_skills(content_dir)}
        self._programs = {p.id: p for p in load_programs(content_dir)}
        self._coach_profiles = {c.id: c for c in load_coach_profiles(content_dir)}
        self._guardian_profiles = {g.id: g for g in load_guardian_profiles(content_dir)}

    def skills(self) -> list[Skill]:
        return list(self._skills.values())

    def skill(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def programs(self) -> list[Program]:
        return list(self._programs.values())

    def program(self, program_id: str) -> Program | None:
        return self._programs.get(program_id)

    def coach_profiles(self) -> list[CoachProfile]:
        return list(self._coach_profiles.values())

    def coach_profile(self, profile_id: str) -> CoachProfile | None:
        return self._coach_profiles.get(profile_id)

    def guardian_profiles(self) -> list[GuardianProfile]:
        return list(self._guardian_profiles.values())

    def guardian_profile(self, profile_id: str) -> GuardianProfile | None:
        return self._guardian_profiles.get(profile_id)

    def find_guardian_profile(self, learner_tags: list[str]) -> "GuardianProfile | None":
        """Return the first profile whose cohort_tags overlap with the learner's tags."""
        for profile in self._guardian_profiles.values():
            if any(tag in profile.cohort_tags for tag in learner_tags):
                return profile
        return None


_registry: ContentRegistry | None = None


def init_registry(content_dir: Path) -> ContentRegistry:
    global _registry
    _registry = ContentRegistry(content_dir)
    return _registry


def registry() -> ContentRegistry:
    if _registry is None:
        raise RuntimeError("Content registry not initialised; call init_registry() first")
    return _registry
