# Frontend

React 19 + TypeScript + Vite, Tailwind CSS 4, Radix UI primitives, TanStack
Query for server state, React Router 7. Lives in `frontend/`.

## Structure

```
frontend/
  index.html, shell.html      two entry documents (main app, shell)
  vite.config.ts              main build + vitest config
  vite.shell.config.ts        shell build (base /_styx/app/)
  nginx.conf                  production server (serves dist, proxies /api)
  src/
    main.tsx                  providers + routes (main app)
    App.tsx                   authenticated home (tabs: instances, templates, settings, ...)
    api/client.ts             typed fetch wrapper + api object
    auth/                     AuthContext, ProtectedRoute
    pages/                    Login, Setup, ChangePassword, AcceptInvite, Connecting, Desktop
    components/               feature folders + ui/ (shadcn-style primitives)
    hooks/                    TanStack Query hooks (use-instances, use-templates, ...)
    lib/                      pure helpers and shared types
    theme/                    ThemeProvider, resolve.ts
    styles/                   globals.css, tokens.ts
    shell/                    the Styx shell (second build)
    test/setup.ts             vitest setup
```

Routes (`main.tsx`): `/login`, `/change-password`, `/setup`,
`/accept-invite/:token`, `/connecting` are public; `/desktop/:sub` and `/*` are
wrapped in `ProtectedRoute`.

## API client

`src/api/client.ts` exports an `api` object of typed methods over a private
`request<T>()`:

* Base path `/api`, cookies included. Unsafe methods read the `csrf_token` cookie and send it as `X-CSRF-Token` (the backend does a double-submit compare). Every call sends `X-Styx-Client: 1`.
* On `401` (not under `/auth/`) it performs **one silent refresh** and retries, and only bounces to `/login` if the refresh fails. Concurrent 401s share a single refresh (`single-flight.ts`).
* Inside the shell (`/_styx/app/...`) the login redirect carries the shell path so sign-in returns there.

To add an endpoint: add the response type, add an `api.<name>` method, wrap it
in a hook under `hooks/` (TanStack Query), and consume the hook in a component.

## Shell build

The *shell* is a second SPA: a framed app with an edge tab and dock used when
you open a proxied service, so you can switch apps without leaving the page.

| | Main | Shell |
|---|---|---|
| Entry | `index.html` -> `src/main.tsx` | `shell.html` -> `src/shell/main.tsx` |
| Config | `vite.config.ts` | `vite.shell.config.ts` (merges the base) |
| Base path | `/` | `/_styx/app/` |
| Output | `dist/` | `dist/_styx/app/` |
| Why separate | | `/assets/*` belongs to the focused app; shell assets must not collide |

`npm run build` runs `tsc -b && vite build && vite build -c vite.shell.config.ts`.
nginx serves `/_styx/app/` with `shell.html` as the fallback. Shell files:
`frame.tsx` (the iframe), `dock.tsx`, `edge-tab.tsx`, `dock-workspaces.tsx`,
`url.ts` (shell path parsing), `use-frame-sync.ts`, `use-hotkey.ts`,
`ferry-pos.ts` (persisted edge position).

!!! note "Same-origin framing"
    The backend serves its own notice pages with `frame-ancestors 'self'` and
    `X-Frame-Options: SAMEORIGIN` so they can show inside the shell frame; every
    other response is `DENY`. See [Security](security.md).

## Theming

* `styles/tokens.ts` defines the Styx palette (light and dark); `globals.css` must use exactly those values.
* `theme/ThemeProvider.tsx` is the single owner of the `.dark` class. Public routes (`/login`, `/setup`, `/accept-invite`) follow the OS; authenticated routes honour the stored preference (`resolve.ts`, unit tested).
* Theme flips suppress CSS transitions for two frames (`no-transitions`).
* Reduced motion is applied at startup (`lib/motion.ts`) and through `MotionConfig`.

## Testing and the build gate

* Unit and component tests: **vitest** + Testing Library (`jsdom`, `globals: true`). Tests sit next to code in `__tests__/` folders or as `*.test.ts(x)`.
* `npm test` runs `vitest run`; `npm run test:watch` for TDD.
* **Build gate: `npm run build`.** `tsc -b` is stricter than `npx tsc --noEmit` (project references, `lint` script). CI runs `npm run build` as the blocking frontend check, so run it before every commit that touches `frontend/`.

```bash
cd frontend
npm ci
npm run dev        # Vite on :5173, proxies /api to localhost:8000
npm test
npm run build
```

For dev against the backend set `DEV_CORS=true` and `COOKIE_SECURE=false`
on the backend (see [Contributing](contributing.md)).
