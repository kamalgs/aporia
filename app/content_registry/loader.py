from pathlib import Path

import frontmatter

from app.domain.content import CoachProfile, GuardianProfile, Program, Skill


def _slug(path: Path) -> str:
    return path.stem


def load_skills(content_dir: Path) -> list[Skill]:
    skills = []
    for path in sorted((content_dir / "skills").glob("*.md")):
        post = frontmatter.load(str(path))
        meta = dict(post.metadata)
        skills.append(Skill(
            id=meta.get("id", _slug(path)),
            title=meta.get("title", _slug(path)),
            objective=meta.get("objective", ""),
            mastery_description=meta.get("mastery_description", ""),
            common_mistakes=meta.get("common_mistakes", []),
            sample_exchanges=meta.get("sample_exchanges", []),
            tags=meta.get("tags", []),
            raw_md=post.content,
        ))
    return skills


def load_programs(content_dir: Path) -> list[Program]:
    programs = []
    for path in sorted((content_dir / "programs").glob("*.md")):
        post = frontmatter.load(str(path))
        meta = dict(post.metadata)
        programs.append(Program(
            id=meta.get("id", _slug(path)),
            title=meta.get("title", _slug(path)),
            description=meta.get("description", ""),
            skill_ids=meta.get("skill_ids", []),
            mandatory_skill_ids=meta.get("mandatory_skill_ids", []),
            assessment_criteria=meta.get("assessment_criteria", ""),
            coach_profile_id=meta.get("coach_profile_id", ""),
            raw_md=post.content,
        ))
    return programs


def load_coach_profiles(content_dir: Path) -> list[CoachProfile]:
    profiles = []
    for path in sorted((content_dir / "coach_profiles").glob("*.md")):
        post = frontmatter.load(str(path))
        meta = dict(post.metadata)
        profiles.append(CoachProfile(
            id=meta.get("id", _slug(path)),
            title=meta.get("title", _slug(path)),
            tone=meta.get("tone", ""),
            pacing=meta.get("pacing", ""),
            raw_md=post.content,
        ))
    return profiles


def load_guardian_profiles(content_dir: Path) -> list[GuardianProfile]:
    profiles = []
    for path in sorted((content_dir / "guardian_profiles").glob("*.md")):
        post = frontmatter.load(str(path))
        meta = dict(post.metadata)
        profiles.append(GuardianProfile(
            id=meta.get("id", _slug(path)),
            title=meta.get("title", _slug(path)),
            cohort_description=meta.get("cohort_description", ""),
            defaults=meta.get("defaults", {}),
            raw_md=post.content,
        ))
    return profiles
