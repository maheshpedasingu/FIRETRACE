# FIRETRACE — Project Progress

Each checkpoint lists what was verified and the commit hash. A phase is only marked
complete after its tests and checks have actually run.

## Environment assessment (2026-11-14, build sandbox)

| Item | Found | Spec requirement | Status |
|---|---|---|---|
| Python | 3.13.18 | 3.12 preferred | OK (3.12 targeted for Windows target) |
| Node / npm | 22.23.4 / 10.9.9 | installed compatible | OK |
| Git | 2.43.0 | required | OK |
| pandas / numpy / scipy | 3.0.5 / 2.5.3 / 1.18.1 | required | Available |
| pydantic / pytest / uvicorn | 2.13.5 / 9.1.1 / 0.54.0 | required | Available |
| ruff | present | required | Available |
| FastAPI, SQLAlchemy, httpx | missing | required | **BLOCKED — package installs refused** |
| GeoPandas, Shapely, PyProj | missing | required | **BLOCKED — package installs refused** |
| Vite, React-Leaflet, Leaflet, Recharts, Vitest, Testing Library | missing | required | **BLOCKED — npm registry unreachable** |
| NASA FIRMS (API + archive) | unreachable from build shell | real data required | **BLOCKED — no outbound access to FIRMS** |

Consequences:
- No real FIRMS observations can be obtained inside this sandbox. Per rule 1 and 3,
  no observations or API responses will be fabricated; real data must come from a
  user-supplied FIRMS archive CSV or a run on a networked machine.
- Frontend/backend startup cannot be verified here until dependencies are installable.

## Checkpoints

| Phase | Status | Verification | Commit |
|---|---|---|---|
| 0. Foundation — repo, structure, config templates | In progress | Structure created; startup NOT yet verified (blocked) | see git log |
