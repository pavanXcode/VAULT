"""
Role-Based Demo Authentication and Data Scoping Service for VAULT.
Enforces backend authorization and data access boundaries.
Note: Configured for localhost hackathon demonstration. Enterprise SSO/LDAP is future work.
"""

from typing import Dict, List, Optional
from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

API_KEY_HEADER = APIKeyHeader(name="X-VAULT-API-Key", auto_error=False)


class UserSession(BaseModel):
    username: str
    role: str  # "researcher" or "admin"
    authorized_scopes: List[str]  # Record prefixes or tags allowed to view
    is_demo: bool = True


DEMO_USERS: Dict[str, UserSession] = {
    "vault-researcher-token-2026": UserSession(
        username="Dr. Pawan Kumar",
        role="researcher",
        authorized_scopes=["REC-", "EXP-", "DOC-", "MTH-"],
    ),
    "vault-admin-token-2026": UserSession(
        username="Governance Officer",
        role="admin",
        authorized_scopes=["*"],
    ),
}

DEFAULT_ANONYMOUS_USER = UserSession(
    username="Dr. Pawan Kumar",
    role="researcher",
    authorized_scopes=["REC-", "EXP-", "DOC-", "MTH-"],
    is_demo=True,
)


def get_current_user(
    api_key: Optional[str] = Security(API_KEY_HEADER),
) -> UserSession:
    """
    Validates token and returns current user session.
    Defaults to researcher demo session if no token is provided for localhost web UI convenience.
    """
    if not api_key:
        return DEFAULT_ANONYMOUS_USER

    user = DEMO_USERS.get(api_key.strip())
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unrecognized X-VAULT-API-Key demo credential.",
        )
    return user


def require_role(required_role: str):
    """Dependency enforcing minimum role requirement (e.g. 'admin')."""
    def role_checker(user: UserSession = Security(get_current_user)) -> UserSession:
        if required_role == "admin" and user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Action requires '{required_role}' authorization. Current role: '{user.role}'.",
            )
        return user
    return role_checker


def check_record_scope(record_id: str, user: UserSession) -> bool:
    """Backend scope enforcement: verifies caller is authorized to view record."""
    if "*" in user.authorized_scopes:
        return True
    return any(record_id.startswith(scope) for scope in user.authorized_scopes)
