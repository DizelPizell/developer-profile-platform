import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Response, UploadFile
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.github import service as github_service
from app.github.budget import UserRequestBudget
from app.github.client import GitHubApiClient
from app.github.dependencies import get_github_api_client, get_now, get_user_request_budget
from app.github.schemas import RepositoryLinkRequest
from app.media import storage
from app.media.images import MAX_UPLOAD_BYTES, ImageRejected, reencode
from app.models.identity import User
from app.models.projects import Project
from app.projects import screenshots, service
from app.projects.schemas import (
    FeaturedProject,
    FeaturedProjectsResponse,
    FeaturedReorderRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectSummary,
    ProjectVisibilityUpdate,
    ProjectWrite,
    Screenshot,
    ScreenshotCaption,
    ScreenshotCaptionUpdate,
    ScreenshotListResponse,
    ScreenshotReorderRequest,
)

router = APIRouter(prefix="/projects", tags=["projects"])
featured_router = APIRouter(prefix="/profile/featured-projects", tags=["projects"])
# Import creates a project, so it lives with the project routes (ADR-017).
import_router = APIRouter(prefix="/integrations/github/repositories", tags=["github"])


def _project_response(db: Session, project: Project, now: datetime) -> ProjectResponse:
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
        demo_url=project.demo_url,
        technologies=names,
        featured_position=position,
        github=github_service.project_github(db, project.id, now),
        screenshots=_screenshot_items(db, project.id),
    )


def _screenshot_items(db: Session, project_id: uuid.UUID) -> list[Screenshot]:
    return [
        Screenshot(
            id=s.id,
            url=storage.url(s.storage_key),
            caption=s.caption,
            width=s.width,
            height=s.height,
        )
        for s in screenshots.list_screenshots(db, project_id)
    ]


def _screenshot_list(db: Session, project_id: uuid.UUID) -> ScreenshotListResponse:
    return ScreenshotListResponse(items=_screenshot_items(db, project_id))


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
    repositories = github_service.linked_repositories(db, user.id, ids)
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
                github=repositories.get(project.id),
            )
            for project in projects
        ]
    )


@router.post("", status_code=201)
def create_project(
    payload: ProjectWrite,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    now: datetime = Depends(get_now),
) -> ProjectResponse:
    service.lock_owner_profile(db, user)
    changes, technologies = _split(payload)
    project = service.create_project(db, user, changes, technologies)
    db.commit()
    return _project_response(db, project, now)


@router.get("/{project_id}")
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    now: datetime = Depends(get_now),
) -> ProjectResponse:
    return _project_response(db, service.get_own_project(db, user, project_id), now)


@router.patch("/{project_id}")
def update_project(
    project_id: str,
    payload: ProjectWrite,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    now: datetime = Depends(get_now),
) -> ProjectResponse:
    project = service.get_own_project(db, user, project_id, for_update=True)
    changes, technologies = _split(payload)
    service.update_project(db, project, changes, technologies)
    db.commit()
    return _project_response(db, project, now)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    service.lock_owner_profile(db, user)
    project = service.get_own_project(db, user, project_id, for_update=True)
    keys = screenshots.storage_keys(db, project.id)
    service.delete_project(db, project)
    db.commit()
    # Files go only after the rows are gone (ADR-0022).
    storage.delete(keys)
    return Response(status_code=204)


@router.post("/{project_id}/screenshots", status_code=201)
def upload_screenshot(
    project_id: str,
    file: UploadFile,
    caption: Annotated[ScreenshotCaption, Form()] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScreenshotListResponse:
    project = service.get_own_project(db, user, project_id)
    project_uuid = project.id
    screenshots.check_limit(db, project_uuid)
    # No transaction stays open while the image is re-encoded.
    db.rollback()
    # shortcut: without Nginx (development) the request body has no size limit;
    # Nginx caps this path at 6 MB in production (step 4.2b).
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    try:
        image = reencode(data)
    except ImageRejected as exc:
        raise screenshots.rejected(exc) from None

    key = storage.screenshot_key(project_uuid)
    storage.save(key, image.data)
    try:
        project = service.get_own_project(db, user, project_id, for_update=True)
        screenshots.add(db, project, key, image, caption)
        db.commit()
    except BaseException:
        db.rollback()
        storage.delete([key])
        raise
    return _screenshot_list(db, project_uuid)


@router.patch("/{project_id}/screenshots/{screenshot_id}")
def update_screenshot(
    project_id: str,
    screenshot_id: str,
    payload: ScreenshotCaptionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScreenshotListResponse:
    project = service.get_own_project(db, user, project_id, for_update=True)
    screenshots.get(db, project, screenshot_id).caption = payload.caption
    db.commit()
    return _screenshot_list(db, project.id)


@router.delete("/{project_id}/screenshots/{screenshot_id}")
def delete_screenshot(
    project_id: str,
    screenshot_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScreenshotListResponse:
    project = service.get_own_project(db, user, project_id, for_update=True)
    project_uuid = project.id
    key = screenshots.remove(db, screenshots.get(db, project, screenshot_id))
    db.commit()
    storage.delete([key])
    return _screenshot_list(db, project_uuid)


@router.post("/{project_id}/screenshots/reorder")
def reorder_screenshots(
    project_id: str,
    payload: ScreenshotReorderRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScreenshotListResponse:
    project = service.get_own_project(db, user, project_id, for_update=True)
    screenshots.reorder(db, project, payload.screenshot_ids)
    db.commit()
    return _screenshot_list(db, project.id)


@router.post("/{project_id}/publish")
def publish_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    now: datetime = Depends(get_now),
) -> ProjectResponse:
    project = service.get_own_project(db, user, project_id, for_update=True)
    service.publish(db, project)
    db.commit()
    return _project_response(db, project, now)


@router.post("/{project_id}/archive")
def archive_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    now: datetime = Depends(get_now),
) -> ProjectResponse:
    service.lock_owner_profile(db, user)
    project = service.get_own_project(db, user, project_id, for_update=True)
    service.archive(db, project)
    db.commit()
    return _project_response(db, project, now)


@router.post("/{project_id}/visibility")
def change_project_visibility(
    project_id: str,
    payload: ProjectVisibilityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    now: datetime = Depends(get_now),
) -> ProjectResponse:
    service.lock_owner_profile(db, user)
    project = service.get_own_project(db, user, project_id, for_update=True)
    service.change_visibility(db, project, payload.visibility)
    db.commit()
    return _project_response(db, project, now)


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
    db.commit()
    return _project_response(db, project, now)


@router.delete("/{project_id}/repository")
def unlink_repository(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    now: datetime = Depends(get_now),
) -> ProjectResponse:
    project = service.get_own_project(db, user, project_id, for_update=True)
    github_service.unlink(db, project)
    db.commit()
    return _project_response(db, project, now)


@import_router.post("/{repository_id}/import", status_code=201)
def import_repository(
    repository_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    client: GitHubApiClient = Depends(get_github_api_client),
    budget: UserRequestBudget = Depends(get_user_request_budget),
    now: datetime = Depends(get_now),
) -> ProjectResponse:
    github_repo_id = github_service.parse_github_repo_id(repository_id)
    # Early checks that spare the user's GitHub budget; the write transaction
    # below repeats them under the profile lock and the database's constraint.
    service.check_project_limit(db, user)
    linked = github_service.linked_project_id(db, user.id, github_repo_id)
    if linked is not None:
        raise github_service.already_linked(linked)
    user_id, github_user_id = user.id, user.github_user_id
    # Ends the read transaction: no transaction stays open while GitHub answers (ADR-010).
    db.rollback()
    checked = github_service.check_import(
        github_repo_id, user_id, github_user_id, client=client, budget=budget, now=now
    )

    project = service.create_imported_project(db, user, checked, now)
    db.commit()
    return _project_response(db, project, now)


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
