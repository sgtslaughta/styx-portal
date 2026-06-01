import pytest
from fastapi import HTTPException
from app.security.deps import require_owner_or_admin
from app.models import User


def _user(role="user", uid="u1"):
    return User(id=uid, username="x", password_hash="h", role=role)


def test_owner_allowed():
    require_owner_or_admin("u1", _user(uid="u1"))  # no raise


def test_admin_allowed():
    require_owner_or_admin("someone-else", _user(role="admin", uid="u2"))


def test_other_user_denied():
    with pytest.raises(HTTPException) as e:
        require_owner_or_admin("owner-x", _user(uid="u9"))
    assert e.value.status_code == 403
