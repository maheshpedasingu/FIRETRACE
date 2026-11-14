# FIRETRACE — Project Progress

Each checkpoint lists what was verified and the commit hash. A phase is only marked
complete after its tests and checks have actually run.

## Scope

FIRETRACE is a **global** satellite fire intelligence platform (scope correction,
2026-11-14). It has no geographic restriction or default region. Andhra Pradesh, India
is at most an optional example preset. Coverage claims are limited to data actually
imported and verified. See `docs/architecture/ARCHITECTURE.md`.

## Data coverage (verified)

| Platform | Product | Areas | Date range | Source files | Verified |
|---|---|---|---|---|---|
| — | — | — | — | — | No real NASA data imported yet |

Automated tests use only fixtures labelled SYNTHETIC TEST DATA until real FIRMS data is
imported on the user's Windows PC (MAP_KEY and/or official archive downloads).

## Environment assessment (2026-11-14, build sandbox)

| Item | Found | Spec requirement | Status |
|---|---|---|---|
| Python | 3.13.18 | 3.12 preferred | OK (3.12 targeted for Windows) |
| Node / npm | 22.23.4 / 10.9.9 | installed compatible | OK |
| Git | 2.43.0 | required | OK |
| pandas / numpy / scipy | 3.0.5 / 2.5.3 / 1.18.1 | required | Available |
| pydantic / pytest / uvicorn | 2.13.5 / 9.1.1 / 0.54.0 | required | Available |
| ruff | present | required | Available |
| FastAPI, SQLAlchemy, httpx | missing | required | **BLOCKED — package installs refused** |
| GeoPandas, Shapely, PyProj | missing | required | **BLOCKED — package installs refused** |
| pyarrow, DuckDB | missing | required for global storage (ADR-0001) | **BLOCKED — package installs refused** |
| Vite, React-Leaflet, Leaflet, Recharts, Vitest, Testing Library | missing | required | **BLOCKED — npm registry unreachable** |
| NASA FIRMS (API + archive) | unreachable from build shell | real data required | **BLOCKED — no outbound access to FIRMS** |

Decision (2026-11-14): development continues in a new session with package installs
enabled. Real data is imported later on the user's Windows PC.

## Architecture decisions

| ID | Decision | Reason |
|---|---|---|
| ADR-0001 | SQLite for metadata; partitioned Parquet + DuckDB for observations and aggregates | Global 2000–present archive is too large for interactive SQLite row queries on 16 GB CPU-only hardware |
| ADR-0002 | Coverage registry records the spatial/temporal extent of every ingestion | Separates missing data from valid zero activity worldwide |
| ADR-0003 | Area API max DAY_RANGE is configurable, default 5 | NASA's page shows 1–10, third-party docs say 1–5; verify against the live service |

## Development workflow

Code is written in the Claude chat sandbox (no package installs, no network) and
delivered as a git bundle on a feature branch. Verification happens on the Windows
target: tests, lint, type check, build and startup. Only verified work is merged into
`main` and tagged.

## Checkpoints

| Phase | Status | Verification | Commit |
|---|---|---|---|
| 0. Repository structure and config templates | Done | Structure and secret exclusions inspected | 525e76c |
| 0. Global scope — architecture, plan, docs | Done (documentation only) | Docs reviewed | b3d71f9 |
| 1. Foundation — FastAPI `/api/health`, React/Vite/Tailwind shell | **Done — verified 2026-11-14 on Windows** | See Phase 1 results below | c153be8, 30134a9, merge 682cad9, tag `v0.1-foundation` |

### Phase 1 verification results (Windows 11 PC, 2026-11-14)

Environment: Python 3.12.7 (venv), Node v24.22.1, npm 11.19.1, Git 2.56.0.windows.2.

| Check | Result |
|---|---|
| `pytest` (backend) | 4 passed, 1 warning |
| `ruff check` | All checks passed |
| `vitest run` (Vitest 5.1.0) | 2 passed |
| `tsc --noEmit` + `vite build` (Vite 8.3.8) | Succeeded (17 modules, JS 221.74 kB / 69.43 kB gzip) |
| Backend startup + `GET /api/health` | `status: ok` (reported by user) |
| Frontend dev server shows backend status | Reported OK by user |

Open item: pytest warning — Starlette reports that using `httpx` with its test client is
deprecated and suggests `httpx2`. To be investigated before changing test dependencies.

Pinned versions: `backend/requirements.txt` (pip freeze of the verified environment) and
`frontend/package-lock.json`.
