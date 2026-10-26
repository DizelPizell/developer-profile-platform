from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.identity import User
from app.models.projects import Project
from app.projects import service
from app.projects.schemas import (
    ProjectListResponse,
    ProjectResponse,
    ProjectSummary,
    ProjectVisibilityUpdate,
    ProjectWrite,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_response(db: Session, project: Project) -> ProjectResponse:
    names = service.technology_names(db, [project.id])[project.id]
    position = service.featured_positions(db, [project.id]).get(project.id)
    return ProjectResponse(
        id=project.id,
        status=project.status,
        visibility=project.visibility,
        title=project.title,
        summary=project.summary,
        description=project.description,
        problem=project.problem,
        results=project.results,
        role=project.role,
        contribution=project.contribution,
        technologies=names,
        featured_position=position,
    )


def _split(payload: ProjectWrite) -> tuple[dict[str, str | None], list[str] | None]:
    """Text fields present in the request (an explicit null is a change too) and the
    technology list, or None when it was not sent."""
    present = payload.model_fields_set
    changes = payload.model_dump(include=present - {"technologies"})
    return changes, payload.technologies if "technologies" in present else None


@router.get("")
def list_projects(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ProjectListResponse:
    projects = service.list_own_projects(db, user)
    ids = [project.id for project in projects]
    names = service.technology_names(db, ids)
    positions = service.featured_positions(db, ids)
    return ProjectListResponse(
        items=[
            ProjectSummary(
                id=project.id,
                status=project.status,
                visibility=project.visibility,
                title=project.title,
                summary=project.summary,
                technologies=names[project.id],
                featured_position=positions.get(project.id),
            )
            for project in projects
        ]
    )


@router.post("", status_code=201)
def create_project(
    payload: ProjectWrite,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectResponse:
    service.lock_owner_profile(db, user)
    changes, technologies = _split(payload)
    project = service.create_project(db, user, changes, technologies)
    db.commit()
    return _project_response(db, project)


@router.get("/{project_id}")
def get_project(
    project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ProjectResponse:
    return _project_response(db, service.get_own_project(db, user, project_id))


@router.patch("/{project_id}")
def update_project(
    project_id: str,
    payload: ProjectWrite,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectResponse:
    project = service.get_own_project(db, user, project_id, for_update=True)
    changes, technologies = _split(payload)
    service.update_project(db, project, changes, technologies)
    db.commit()
    return _project_response(db, project)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    service.lock_owner_profile(db, user)
    project = service.get_own_project(db, user, project_id, for_update=True)
    service.delete_project(db, project)
    db.commit()
    return Response(status_code=204)


@router.post("/{project_id}/publish")
def publish_project(
    project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ProjectResponse:
    project = service.get_own_project(db, user, project_id, for_update=True)
    service.publish(db, project)
    db.commit()
    return _project_response(db, project)


@router.post("/{project_id}/archive")
def archive_project(
    project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ProjectResponse:
    service.lock_owner_profile(db, user)
    project = service.get_own_project(db, user, project_id, for_update=True)
    service.archive(db, project)
    db.commit()
    return _project_response(db, project)


@router.post("/{project_id}/visibility")
def change_project_visibility(
    project_id: str,
    payload: ProjectVisibilityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectResponse:
    service.lock_owner_profile(db, user)
    project = service.get_own_project(db, user, project_id, for_update=True)
    service.change_visibility(db, project, payload.visibility)
    db.commit()
    return _project_response(db, project)
