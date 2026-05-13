import textwrap
from pathlib import Path

import pytest

from app.content_registry.loader import (
    load_coach_profiles,
    load_guardian_profiles,
    load_programs,
    load_skills,
)
from app.content_registry.registry import ContentRegistry


@pytest.fixture
def content_dir(tmp_path: Path) -> Path:
    (tmp_path / "skills").mkdir()
    (tmp_path / "programs").mkdir()
    (tmp_path / "coach_profiles").mkdir()
    (tmp_path / "guardian_profiles").mkdir()

    (tmp_path / "skills" / "add-carry.md").write_text(textwrap.dedent("""
        ---
        id: add-carry
        title: Addition with carry
        objective: Add two numbers with carry.
        tags:
          - math
        ---
        Body text here.
    """).strip())

    (tmp_path / "programs" / "math-101.md").write_text(textwrap.dedent("""
        ---
        id: math-101
        title: Math 101
        skill_ids:
          - add-carry
        mandatory_skill_ids:
          - add-carry
        coach_profile_id: encouraging
        ---
        Program body.
    """).strip())

    (tmp_path / "coach_profiles" / "encouraging.md").write_text(textwrap.dedent("""
        ---
        id: encouraging
        title: Encouraging Coach
        tone: Warm and positive
        ---
        Profile body.
    """).strip())

    (tmp_path / "guardian_profiles" / "child-8.md").write_text(textwrap.dedent("""
        ---
        id: child-8
        title: Child aged 8
        cohort_description: Eight-year-olds
        defaults:
          session_length_minutes: 10
        ---
        Guardian body.
    """).strip())

    return tmp_path


def test_load_skills(content_dir: Path) -> None:
    skills = load_skills(content_dir)
    assert len(skills) == 1
    assert skills[0].id == "add-carry"
    assert skills[0].tags == ["math"]
    assert "Body text" in skills[0].raw_md


def test_load_programs(content_dir: Path) -> None:
    programs = load_programs(content_dir)
    assert len(programs) == 1
    assert programs[0].id == "math-101"
    assert programs[0].mandatory_skill_ids == ["add-carry"]
    assert programs[0].coach_profile_id == "encouraging"


def test_load_coach_profiles(content_dir: Path) -> None:
    profiles = load_coach_profiles(content_dir)
    assert len(profiles) == 1
    assert profiles[0].id == "encouraging"
    assert profiles[0].tone == "Warm and positive"


def test_load_guardian_profiles(content_dir: Path) -> None:
    profiles = load_guardian_profiles(content_dir)
    assert len(profiles) == 1
    assert profiles[0].id == "child-8"
    assert profiles[0].defaults == {"session_length_minutes": 10}


def test_registry_lookup(content_dir: Path) -> None:
    reg = ContentRegistry(content_dir)
    assert reg.skill("add-carry") is not None
    assert reg.skill("unknown") is None
    assert reg.program("math-101") is not None
    assert len(reg.skills()) == 1
    assert len(reg.programs()) == 1


def test_empty_content_dir(tmp_path: Path) -> None:
    for sub in ("skills", "programs", "coach_profiles", "guardian_profiles"):
        (tmp_path / sub).mkdir()
    reg = ContentRegistry(tmp_path)
    assert reg.skills() == []
    assert reg.programs() == []


def test_guardian_profile_cohort_tags(content_dir: Path) -> None:
    profiles = load_guardian_profiles(content_dir)
    assert profiles[0].cohort_tags == []  # tmp fixture has no cohort_tags


def test_find_guardian_profile_by_tag(tmp_path: Path) -> None:
    for sub in ("skills", "programs", "coach_profiles", "guardian_profiles"):
        (tmp_path / sub).mkdir()
    (tmp_path / "guardian_profiles" / "child.md").write_text(textwrap.dedent("""
        ---
        id: child
        title: Child
        cohort_tags:
          - child
          - elementary
        ---
        Body.
    """).strip())
    reg = ContentRegistry(tmp_path)
    assert reg.find_guardian_profile(["child"]) is not None
    assert reg.find_guardian_profile(["adult"]) is None
    assert reg.find_guardian_profile([]) is None
