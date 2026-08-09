from fastapi import APIRouter, Depends

from accounts.auth import require_platform_admin
from bookclub import crud, schemas
from dependencies import DatabaseSession

# Platform-admin-only visibility into self-serve clubs, which have no
# BookClubAccess rows and are otherwise invisible to the staff /bookclub
# tool — support/abuse triage only, no management actions in v1. Mounted on
# the main `app` (libtools.app), not bookclub_public_app, since it's a
# staff-facing feature gated by the ordinary LibtoolsUser admin role.
router = APIRouter(
    prefix="/api/admin/bookclub",
    tags=["bookclub-admin"],
    dependencies=[Depends(require_platform_admin)],
)


@router.get("/self-serve-clubs", response_model=list[schemas.SelfServeClubSummary])
def list_self_serve_clubs(db: DatabaseSession):
    return [
        schemas.SelfServeClubSummary(
            id=club.id,
            name=club.name,
            slug=club.slug,
            facilitator_name=owner.name if owner else None,
            facilitator_email=owner.email if owner else None,
            participant_count=count,
            # The owner ParticipantAccount is created in the same
            # transaction as the club itself (see participant_routes.py's
            # create_club), so its created_at is an accurate proxy for
            # "when this club was created" without needing a separate
            # created_at column on BookClub.
            created_at=owner.created_at if owner else None,
        )
        for club, owner, count in crud.list_self_serve_clubs(db)
    ]
