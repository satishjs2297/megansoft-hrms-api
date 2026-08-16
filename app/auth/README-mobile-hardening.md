# Mobile Auth/Session Hardening

Implemented backend additions for mobile production:

- `POST /auth/login` now returns `access_token`, `refresh_token`, and `session_id`.
- `POST /auth/refresh` rotates refresh tokens.
- `GET /auth/sessions` lists current user sessions.
- `POST /auth/revoke` revokes a specific session or all sessions.

Security/reliability enhancements:

- Access/refresh token separation with token type checks.
- Server-side session persistence and revocation.
- Login and heavy endpoint rate limiting.
- Request-id correlation via `X-Request-Id`.
- Standardized error envelope from global exception handlers.
