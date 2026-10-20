# Matrix-Card 2FA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Password logins of users with an active matrix card must also answer 3 fixed-until-correct grid cells; cards are enrolled, downloaded/printed and revoked from the UI.

**Architecture:** Pure card logic in `backend/app/services/matrix_card.py`; all new endpoints in a new router `backend/app/routers/matrix.py` (auth.py is at 494 lines — it only gets a ~10-line branch in `login`). Card cells are Fernet-encrypted JSON on the `users` row. The browser draws the card image (canvas → PNG, print view).

**Tech Stack:** FastAPI + SQLModel (SQLite, hand-rolled ALTER migrations), pyjwt, cryptography (Fernet), React + TypeScript (Vite, vitest).

**Spec:** `docs/superpowers/specs/2026-10-19-matrix-card-2fa-design.md`

## Global Constraints
- Grid: columns `A B C D E`, rows `1..10`; cell ids like `"C7"` (column letter + row number).
- Alphabet: `ACDEFGHJKLMNPQRTUVWXY34679`; 3 chars per cell; values generated with `secrets.choice`.
- Challenge size: 3 distinct cells, picked with `secrets`.
- `styx_mfa` cookie: httponly, samesite strict, `secure=COOKIE_SECURE`, path `/api/auth`, max_age 300; JWT `type="mfa"`, exp 300 s.
- Answer comparison: `strip().upper()`, constant-time (`hmac.compare_digest`) per cell, all 3 must match.
- Matrix failure = password failure: `login_lockout.record_fail(...)` + `fail_tracker.record(ip)` exactly as `login` does.
- Audit actions (exact): `auth.matrix_challenge`, `auth.matrix_failed`, `auth.login` (detail `{"method": "matrix"}`), `matrix.generated`, `matrix.activated`, `matrix.removed`, `matrix.admin_reset`.
- Files stay under 500 lines; ruff clean; `npm run build` + vitest green; semantic commits ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus
1. Answer submitted after the 5-min `styx_mfa` expired or after the card was regenerated → 401, no session, user must sign in again (Task 3 test).
2. Repeated logins before answering → the same 3 cells every time (Task 3 test).
3. Lowercase / padded answers (`" c7x "`) accepted; one wrong cell rejects all (Task 1 test).
4. Locked-out user who knows the password still cannot reach the matrix step (Task 3 test).
5. Refresh of a matrix session keeps cookies session-only (Task 3 test).

---

### Task 1: Card core + schema

**Files:**
- Create: `backend/app/services/matrix_card.py`
- Modify: `backend/app/models.py` (User, RefreshToken), `backend/app/database.py` (`_run_migrations` list)
- Test: `backend/tests/test_matrix_card.py`

**Interfaces:**
- Produces: `COLUMNS = "ABCDE"`, `ROWS = range(1, 11)`, `ALPHABET`, `CELLS: list[str]` (50 ids, A1..E10 row-major), `generate_card() -> dict[str, str]`, `pick_challenge(n: int = 3) -> list[str]`, `verify(card: dict[str, str], challenge: list[str], answers: list[str]) -> bool`, `seal(obj) -> str` / `unseal(token: str)` (JSON + `encrypt_secret`/`decrypt_secret`).
- Produces model fields: `User.matrix_card: str | None`, `User.matrix_pending: str | None`, `User.matrix_challenge: str | None` (JSON list), `User.matrix_serial: int = 0`; `RefreshToken.session_only: bool = False`.

- [ ] **Step 1: failing tests** — `test_generate_card_shape` (50 keys == CELLS, each value len 3, chars ⊂ ALPHABET), `test_pick_challenge_distinct` (3 distinct, all in CELLS), `test_verify_case_and_space` (`verify(card, ["A1","B2","C3"], [" "+card["A1"].lower()+" ", card["B2"], card["C3"]]) is True`), `test_verify_one_wrong` (False), `test_verify_wrong_length` (2 answers → False), `test_seal_roundtrip`. Add to `tests/test_database_migrations.py`: users table has the 4 new columns and refresh_tokens has `session_only` after `init_db` on an old schema (follow the existing test pattern there).
- [ ] **Step 2:** `cd backend && .venv/bin/python -m pytest tests/test_matrix_card.py -q` → FAIL (module missing).
- [ ] **Step 3:** implement; migrations entries: `("users","matrix_card","TEXT")`, `("users","matrix_pending","TEXT")`, `("users","matrix_challenge","TEXT")`, `("users","matrix_serial","INTEGER NOT NULL DEFAULT 0")`, `("refresh_tokens","session_only","INTEGER NOT NULL DEFAULT 0")`.
- [ ] **Step 4:** full `pytest -q` + ruff → green.
- [ ] **Step 5:** commit `feat(auth): matrix card core and schema`.

### Task 2: Enrollment API

**Files:**
- Create: `backend/app/routers/matrix.py` (register in `backend/app/main.py` next to the auth router, same prefix style)
- Modify: `backend/app/routers/users.py` (admin reset), `backend/app/middleware/rate_limit.py` (`_STRICT_AUTH_PATHS` += `/api/auth/matrix/generate`, `/api/auth/login/matrix`)
- Test: `backend/tests/test_matrix_enroll.py`

**Interfaces:**
- Consumes: Task 1.
- Produces endpoints (all need an authenticated user + CSRF like other mutating routes):
  - `GET /api/auth/matrix` → `{"enabled": bool}`
  - `POST /api/auth/matrix/generate` body `{"password": str}` → `{"cells": {id: value}, "confirm_cell": "C7"}`; stores `seal({"cells":..., "confirm": cell})` in `matrix_pending`; wrong password → 401 (no lockout change needed beyond audit). Audit `matrix.generated`.
  - `POST /api/auth/matrix/activate` body `{"answer": str}` → 200 `{"enabled": true}`; on match: `matrix_card = seal(cells)`, `matrix_pending = None`, `matrix_challenge = None`, `matrix_serial += 1`; mismatch or no pending → 400. Audit `matrix.activated`.
  - `DELETE /api/auth/matrix` body `{"password": str}` → 200; clears card/pending/challenge, `matrix_serial += 1`. Audit `matrix.removed`.
  - `DELETE /api/users/{user_id}/matrix` (admin) → same clear. Audit `matrix.admin_reset`.
- Test names: `test_generate_requires_password`, `test_generate_then_activate_enables`, `test_activate_wrong_answer_400_and_not_enabled`, `test_regenerate_keeps_old_until_activated`, `test_remove_requires_password`, `test_admin_reset`, `test_member_cannot_admin_reset` (403).
- [ ] Steps: failing tests → run (FAIL) → implement → full pytest + ruff → commit `feat(auth): matrix card enrollment API`.

### Task 3: Login second step + session-only cookies

**Files:**
- Modify: `backend/app/routers/auth.py` (`login` branch; `_issue_session(..., session_only: bool = False)`; `refresh` passes `stored.session_only`), `backend/app/security/cookies.py` (`set_auth_cookies(..., persistent: bool = True)` → `max_age=None` for all four cookies when False; `set_mfa_cookie`, `clear_mfa_cookie`), `backend/app/security/tokens.py` (`create_mfa_token(user_id: str, tv: int, serial: int) -> str`)
- Modify: `backend/app/routers/matrix.py` (`POST /api/auth/login/matrix`)
- Test: `backend/tests/test_matrix_login.py`

**Interfaces:**
- `login`: after password + lockout checks pass and BEFORE `_issue_session`: if `user.matrix_card`: reuse `user.matrix_challenge` or set `json.dumps(pick_challenge())`, commit, `set_mfa_cookie(response, create_mfa_token(user.id, user.token_version, user.matrix_serial))`, audit `auth.matrix_challenge`, return `{"mfa_required": True, "challenge": [...]}`. Do NOT clear lockout counters or set the device cookie yet.
- `POST /api/auth/login/matrix` body `{"answers": [str, str, str]}`: decode `styx_mfa` (type `mfa`); load user; reject (401 `"Sign-in expired"`) if missing/expired/inactive, `tv`/`serial` mismatch, or no `matrix_challenge`; check `login_lockout.is_locked(...)` like `login`; on wrong answers do the failure path (Global Constraints) + audit `auth.matrix_failed`, 401 `"Invalid code"`, challenge unchanged; on success clear `matrix_challenge`, the lockout clears that `login` does on success, `_issue_session(..., session_only=True)`, device cookie, `clear_mfa_cookie`, audit `auth.login` `{"method":"matrix"}`, return the same shape as `login` (`id, username, role, must_change_pw`).
- Test names: `test_password_login_without_card_unchanged`, `test_card_user_gets_challenge_no_session` (no `access_token` cookie set), `test_challenge_stable_across_logins`, `test_matrix_success_issues_session_only_cookies` (Set-Cookie for access_token has no `Max-Age`), `test_matrix_wrong_counts_toward_lockout` (LOCKOUT_THRESHOLD wrong answers → locked), `test_matrix_expired_token_401`, `test_matrix_after_regenerate_401` (serial bump), `test_locked_user_never_gets_challenge`, `test_refresh_keeps_session_only`, `test_oauth_login_ignores_card` (call `_issue_session` path via existing oauth test helper or assert oauth callback code path unchanged — follow `tests/test_oauth_router.py`).
- [ ] Steps: failing tests → run (FAIL) → implement → full pytest + ruff → commit `feat(auth): require matrix card on password login`.

### Task 4: Login page second step

**Files:**
- Modify: `frontend/src/api/client.ts` (`login` return type gains `mfa_required?: boolean; challenge?: string[]`; add `loginMatrix(answers: string[])` → POST `/auth/login/matrix`, same return type as `login`), `frontend/src/pages/LoginPage.tsx`
- Test: `frontend/src/pages/__tests__/login-matrix.test.tsx`

- [ ] In `submit`: if `result.mfa_required`, switch to a step showing the 3 cell ids as labels with one text input each (`autoComplete="off"`, `maxLength={3}`, autofocus first, uppercase display), submit → `api.loginMatrix(answers)` → then the existing success path (must_change_pw / next / `/`). Error → `#login-error` text "Wrong code — check the cells and try again." (inputs cleared, same cells). A "Back" link returns to the password step.
- Tests: `shows three cell inputs when mfa_required`, `submits answers and navigates on success`, `shows error and keeps cells on failure`. Mock `@/api/client` with `withRetry: (fn) => fn()` like the existing login tests.
- [ ] `npm run build` + `npx vitest run` green → commit `feat(ui): matrix card step on login`.

### Task 5: Card settings + image download/print + docs

**Files:**
- Create: `frontend/src/components/settings/matrix-card.tsx`, `frontend/src/lib/matrix-image.ts`
- Modify: `frontend/src/components/settings/nav-config.tsx` (add section `{ id: "signin-card", label: "Sign-in card", Component: MatrixCard }` to category `account`), `frontend/src/api/client.ts` (`matrixStatus`, `matrixGenerate(password)`, `matrixActivate(answer)`, `matrixRemove(password)`), `docs/ADMIN.md` (section "Sign-in card (2FA)": enroll, lost card → regenerate or admin reset, kubectl recovery: `kubectl -n styx exec deploy/backend -- python -c "import sqlite3;c=sqlite3.connect('/app/data/styx-portal.db');c.execute(\"update users set matrix_card=NULL,matrix_pending=NULL,matrix_challenge=NULL,matrix_serial=matrix_serial+1 where username='<name>'\");c.commit()"`)
- Test: `frontend/src/components/settings/__tests__/matrix-card.test.tsx`, `frontend/src/lib/__tests__/matrix-image.test.ts`

**Interfaces:**
- `drawCard(canvas: HTMLCanvasElement, cells: Record<string,string>, title: string): void` and `cardPngBlob(cells, title): Promise<Blob>` in `matrix-image.ts` (grid with column header A–E, row header 1–10, monospace values, title "Styx sign-in card", generated date).
- Component flow: status → "Generate card" (password prompt) → shows card canvas + **Download PNG** (`URL.createObjectURL` + `<a download="styx-sign-in-card.png">`) + **Print** (`window.print()` on a print-only container) + "Enter cell C7 to activate" input → activate → "Active". Enabled state shows "Regenerate" and "Remove" (password prompt). Warning copy: "This card is shown once. Save or print it now."
- Tests: `matrix-image` draws 50 values (mock canvas context `fillText` calls include every value); component: generate → shows confirm cell → activate calls API; remove asks password.
- [ ] build + vitest green → commit `feat(ui): sign-in card enrollment with download and print`.
