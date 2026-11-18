"""The media sweep (ADR-0022, step 4.2b): only old files without a row go."""

import os
import uuid

import pytest

from app.media import sweep as sweep_module
from app.media.sweep import MIN_AGE_SECONDS, sweep
from app.models.identity import User
from app.models.projects import Project, ProjectScreenshot

NOW = 2_000_000_000.0
OLD = NOW - MIN_AGE_SECONDS - 1
YOUNG = NOW - MIN_AGE_SECONDS + 60


def _file(root, key: str, mtime: float):
    path = root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"webp")
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def project(db_session) -> Project:
    user = User(github_user_id=930_001, github_login="sweeper")
    db_session.add(user)
    db_session.flush()
    project = Project(owner_id=user.id)
    db_session.add(project)
    db_session.flush()
    return project


def _key(project_id) -> str:
    return f"projects/{project_id}/{uuid.uuid4()}.webp"


def _row(db_session, project, key, position=1):
    db_session.add(
        ProjectScreenshot(
            project_id=project.id, position=position, storage_key=key, width=1, height=1
        )
    )
    db_session.flush()


def test_removes_only_old_files_without_a_row(db_session, tmp_path, project):
    kept_key = _key(project.id)
    _row(db_session, project, kept_key)
    kept = _file(tmp_path, kept_key, OLD)
    young = _file(tmp_path, _key(project.id), YOUNG)
    orphan = _file(tmp_path, _key(project.id), OLD)
    temporary = _file(tmp_path, f"projects/{project.id}/.{uuid.uuid4()}.webp.tmp", OLD)

    found = sweep(db_session, tmp_path, NOW, dry_run=False)

    assert sorted(found) == sorted([orphan, temporary])
    assert kept.exists() and young.exists()
    assert not orphan.exists() and not temporary.exists()


def test_dry_run_removes_nothing(db_session, tmp_path, project):
    orphan = _file(tmp_path, _key(project.id), OLD)
    assert sweep(db_session, tmp_path, NOW, dry_run=True) == [orphan]
    assert orphan.exists()


def test_emptied_project_directory_is_removed(db_session, tmp_path):
    gone = uuid.uuid4()
    _file(tmp_path, _key(gone), OLD)
    sweep(db_session, tmp_path, NOW, dry_run=False)
    assert not (tmp_path / "projects" / str(gone)).exists()
    assert (tmp_path / "projects").is_dir()


def test_files_outside_projects_are_not_touched(db_session, tmp_path):
    other = _file(tmp_path, "other/file.webp", OLD)
    assert sweep(db_session, tmp_path, NOW, dry_run=False) == []
    assert other.exists()


def test_missing_root_is_an_error(db_session, tmp_path):
    with pytest.raises(FileNotFoundError):
        sweep(db_session, tmp_path / "absent", NOW, dry_run=False)


def test_command_rejects_unknown_arguments(capsys):
    assert sweep_module.main(["--force"]) == 2
    assert "unknown: --force" in capsys.readouterr().out
