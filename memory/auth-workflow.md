# Auth workflow

## Auth strategy

Django's built-in session-based authentication. No third-party auth library (no JWT, no OAuth, no NextAuth). Login/logout handled by Django's built-in `django.contrib.auth.views.LoginView` and `LogoutView`. Sessions stored in PostgreSQL via Django's session framework (`django.contrib.sessions`).

## Login flow

1. User visits any protected URL → redirected to `/auth/login/` (configured via `LOGIN_URL = "/auth/login/"` in settings).
2. User submits credentials (username + password) via Django's built-in login form.
3. `LoginView` validates credentials against `auth_user` table.
4. On success: Django creates a session cookie (`sessionid`), stores session data in `django_session` table, and redirects to `LOGIN_REDIRECT_URL = "/"` (dashboard).
5. On failure: form re-renders with error.

## Token / session handling

- **Session storage**: Server-side sessions in the PostgreSQL `django_session` table (Django default).
- **Cookie**: `sessionid` httpOnly cookie set by Django's `SessionMiddleware`.
- **TTL**: Django's default session TTL applies (2 weeks if `SESSION_EXPIRE_AT_BROWSER_CLOSE` is not set).
- No JWT tokens. No refresh token logic. Standard Django session behavior throughout.

## Logout flow

1. User visits `/auth/logout/` (GET or POST accepted by Django's `LogoutView`).
2. Django flushes the session from the DB and clears the `sessionid` cookie.
3. User is redirected to `LOGOUT_REDIRECT_URL = "/auth/login/"`.

## Protected routes

**Backend — primary decorator:**
All views that require authentication use `@login_required` (from `django.contrib.auth.decorators`). This checks for a valid session and redirects to `LOGIN_URL` if the user is not authenticated.

**Backend — RBAC decorators** (`core/permissions.py`):
- `@role_required(*allowed_roles)` — checks `request.user.profile.role` against an allowlist. Raises `PermissionDenied` (→ 403) if not matched.
- `@clearance_required(min_level)` — checks `request.user.profile.clearance_level` against a 4-level hierarchy. Raises `PermissionDenied` if insufficient.
- `@organisation_access_required` — injects `request.user_organisation` and ensures the user has an organisation assigned.
- `@log_view_access(ModelClass)` — wraps a view to auto-create an `AuditLog` entry (and `DocumentView` for documents) after the view returns.

**Backend — helper function** (`core/permissions.py`):
- `can_approve_workflow(user, workflow_type)` — checks boolean flags on `UserProfile` (`can_approve_jorc`, `can_approve_valmin`) or role membership for GENERAL workflows.

**Backend — queryset scoping** (`core/views.py`):
- `_org_qs_filter(request)` — returns a Django `Q` object that limits querysets to the user's organisation. Superusers see everything; users with no organisation see nothing.

**Frontend:**
No client-side route guards. All protection is enforced server-side. Templates do not render sensitive controls for users without appropriate roles/clearance (checked with `{% if request.user.profile.role == ... %}`).

## User roles and permissions

Roles stored in `UserProfile.role` (VARCHAR, 9 choices):

| Role value | Display name | Category |
|---|---|---|
| `GEOLOGIST_EXPL` | Geologist (Exploration) | Exploration |
| `FIELD_LEAD` | Field Lead | Exploration |
| `DATA_MANAGER` | Data Manager | Exploration |
| `GEOLOGIST_MINE` | Mine Geologist | Mining |
| `METALLURGIST` | Metallurgist | Mining |
| `OPS_MANAGER` | Operations Manager | Mining |
| `ADMIN` | Administrator | Admin |
| `VIEWER` | Viewer Only | Admin |
| `COMPETENT_PERSON` | Competent Person | Governance |

Clearance levels (hierarchical, stored in `UserProfile.clearance_level`):

| Level | Integer rank |
|---|---|
| `PUBLIC` | 0 |
| `INTERNAL` | 1 (default for new users) |
| `CONFIDENTIAL` | 2 |
| `JORC_APPROVED` | 3 |

Approval permissions (boolean flags on `UserProfile`):
- `can_approve_jorc` — required to approve JORC compliance workflows
- `can_approve_valmin` — required to approve VALMIN compliance workflows

Document access check (`UserProfile.can_access_document(document)`):
1. User's `organisation` must match `document.organisation` (or document has no org).
2. User's clearance level must be ≥ document's `confidentiality` level.

New users default to: role=`VIEWER`, clearance=`INTERNAL`, no approval permissions.

## OAuth / social login

Not implemented. Standard username/password only.

## Edge cases and gotchas

- `UserProfile` is auto-created via Django signal on `User` creation (raw=False only, so fixture loading doesn't double-create). Views always check `hasattr(request.user, 'profile')` before accessing `request.user.profile`.
- The `@log_view_access` decorator logs AFTER the view returns, not before. If the view raises a 404, no audit log is written for that access attempt.
- Upload view (`/upload/`) uses `@role_required` with an explicit allowlist of 7 roles — `VIEWER` cannot upload documents.
- Session data is stored in PostgreSQL, not Redis. Redis is only used for object/query caching.
- `ALLOWED_HOSTS = ["*"]` in settings — this is a dev-only setting and must be tightened before any production deployment.
