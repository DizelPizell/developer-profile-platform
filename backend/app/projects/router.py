import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.github import service as github_service
from app.github.budget import UserRequestBudget
from app.github.client import GitHubApiClient
from app.github.dependencies import get_github_api_client, get_now, get_user_request_budget
from app.github.schemas import RepositoryLinkRequest
from app.models.identity import User
from app.models.projects import Project
from app.projects import service
from app.projects.schemas import (
    FeaturedProject,
    FeaturedProjectsResponse,
    FeaturedReorderRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectSummary,
    ProjectVisibilityUpdate,
    ProjectWrite,
)

router = APIRouter(prefix="/projects", tags=["projects"])
featured_router = APIRouter(prefix="/profile/featured-projects", tags=["projects"])


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
        github=github_service.project_github(db, project.id),
    )


def _featured_response(db: Session, profile_id: uuid.UUID) -> FeaturedProjectsResponse:
    return FeaturedProjectsResponse(
        items=[
            FeaturedProject(project_id=project_id, position=position)
            for project_id, position in service.featured_projects(db, profile_id)
        ]
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


@router.post("/{project_id}/showcase")
def feature_project(
    project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> FeaturedProjectsResponse:
    profile = service.lock_owner_profile(db, user)
    profile_id = profile.id
    project = service.get_own_project(db, user, project_id, for_update=True)
    service.feature(db, profile, project)
    db.commit()
    return _featured_response(db, profile_id)


@router.delete("/{project_id}/showcase")
def unfeature_project(
    project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> FeaturedProjectsResponse:
    profile = service.lock_owner_profile(db, user)
    profile_id = profile.id
    project = service.get_own_project(db, user, project_id, for_update=True)
    service.unfeature(db, project)
    db.commit()
    return _featured_response(db, profile_id)


@router.post("/{project_id}/repository")
def link_repository(
    project_id: str,
    payload: RepositoryLinkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    client: GitHubApiClient = Depends(get_github_api_client),
    budget: UserRequestBudget = Depends(get_user_request_budget),
    now: datetime = Depends(get_now),
) -> ProjectResponse:
    # A missing or foreign project is 404 before GitHub is called.
    service.get_own_project(db, user, project_id)
    user_id, github_user_id = user.id, user.github_user_id
    # Ends the read transaction: no transaction stays open while GitHub answers (ADR-010).
    db.rollback()
    checked = github_service.check_repository(
        payload.full_name, user_id, github_user_id, client=client, budget=budget, now=now
    )

    project = service.get_own_project(db, user, project_id, for_update=True)
    github_service.store_link(db, project, checked, now)
    # Step 6.2: queue a sync job here, in this transaction (ADR-018).
    db.commit()
    return _project_response(db, project)


@router.delete("/{project_id}/repository")
def unlink_repository(
    project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ProjectResponse:
    project = service.get_own_project(db, user, project_id, for_update=True)
    github_service.unlink(db, project)
    db.commit()
    return _project_response(db, project)


@featured_router.post("/reorder")
def reorder_featured_projects(
    payload: FeaturedReorderRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FeaturedProjectsResponse:
    profile = service.lock_owner_profile(db, user)
    profile_id = profile.id
    service.reorder_featured(db, profile, payload.project_ids)
    db.commit()
    return _featured_response(db, profile_id)
