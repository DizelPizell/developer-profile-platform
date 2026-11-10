"""
Database constraint tests for profile_contacts (ADR-020).

Each test runs inside a transaction rolled back at teardown by db_session;
a violation is checked inside a SAVEPOINT so the test can go on.
"""

import itertools

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError

from app.models.identity import Profile, ProfileContact, User

_ids = itertools.count(950_001)


@pytest.fixture
def profile(db_session) -> Profile:
    n = next(_ids)
    user = User(github_user_id=n, github_login=f"contact{n}")
    db_session.add(user)
    db_session.flush()
    row = Profile(user_id=user.id, slug=f"contact{n}", status="PRIVATE")
    db_session.add(row)
    db_session.flush()
    return row


def _add(db_session, profile, **fields):
    values = {"type": "TELEGRAM", "value": "ann_dev", "label": None, "position": 1, **fields}
    db_session.execute(insert(ProfileContact).values(profile_id=profile.id, **values))


def _rejected(db_session, profile, constraint: str, **fields):
    with pytest.raises(IntegrityError) as exc, db_session.begin_nested():
        _add(db_session, profile, **fields)
    assert constraint in str(exc.value)


def test_valid_rows(db_session, profile):
    _add(db_session, profile, type="EMAIL", value="a@example.com", position=1)
    _add(db_session, profile, type="PHONE", value="+79123456789", position=2)
    for n in range(3, 8):
        _add(db_session, profile, type="OTHER", value="https://e.xa", label="x", position=n)
    count = db_session.execute(
        select(ProfileContact.id).where(ProfileContact.profile_id == profile.id)
    ).all()
    assert len(count) == 7


def test_type_check(db_session, profile):
    _rejected(db_session, profile, "ck_profile_contacts_type", type="SKYPE")
    _rejected(db_session, profile, "ck_profile_contacts_type", type="email")


@pytest.mark.parametrize(
    ("contact_type", "value"),
    [
        ("EMAIL", "a" * 255),
        ("TELEGRAM", "abcd"),
        ("TELEGRAM", "a" * 33),
        ("LINKEDIN", "ab"),
        ("LINKEDIN", "a" * 101),
        ("PHONE", "+1234567"),
        ("PHONE", "+" + "1" * 16),
        ("OTHER", "h" * 2049),
        ("EMAIL", "   "),
        ("PHONE", " " * 10),
    ],
)
def test_value_length_by_type(db_session, profile, contact_type, value):
    label = "x" if contact_type == "OTHER" else None
    _rejected(
        db_session,
        profile,
        "ck_profile_contacts_value",
        type=contact_type,
        value=value,
        label=label,
    )


def test_label_only_for_other(db_session, profile):
    presence = "ck_profile_contacts_label_presence"
    _rejected(db_session, profile, presence, type="OTHER", value="https://e.xa", label=None)
    _rejected(db_session, profile, presence, label="Telegram")


def test_label_length_and_blank(db_session, profile):
    other = {"type": "OTHER", "value": "https://e.xa"}
    _rejected(db_session, profile, "ck_profile_contacts_label", **other, label="a" * 41)
    _rejected(db_session, profile, "ck_profile_contacts_label", **other, label="  ")


def test_position_range_and_uniqueness(db_session, profile):
    _rejected(db_session, profile, "ck_profile_contacts_position", position=0)
    _rejected(db_session, profile, "ck_profile_contacts_position", position=8)
    _add(db_session, profile, position=1)
    _rejected(db_session, profile, "uq_profile_contacts_position", type="EMAIL", value="a@b.cc")


def test_one_standard_contact_per_type_but_many_other(db_session, profile):
    _add(db_session, profile, position=1)
    _rejected(db_session, profile, "uq_profile_contacts_type", value="other_name", position=2)
    for n in (3, 4, 5, 6):
        # The database does not hold the limit of 3 OTHER: a domain rule.
        _add(db_session, profile, type="OTHER", value="https://e.xa", label="x", position=n)


def test_cascade_on_profile_delete(db_session, profile):
    _add(db_session, profile)
    db_session.execute(text("DELETE FROM profiles WHERE id = :id"), {"id": profile.id})
    remaining = db_session.execute(text("SELECT count(*) FROM profile_contacts")).scalar_one()
    assert remaining == 0
