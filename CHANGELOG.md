# Changelog

## [Unreleased]
### Changed
- Scope corrected to a global platform: any country, region, bbox or polygon worldwide;
  full MODIS/VIIRS history. Andhra Pradesh is only an optional example preset.
- Storage design: SQLite metadata + partitioned Parquet/DuckDB observation store (ADR-0001).

### Added
- `docs/architecture/ARCHITECTURE.md` (global ingestion, coverage registry, storage, AOI model).
- `docs/IMPLEMENTATION_PLAN.md` (45-hour plan with a global synthetic test matrix).
- Repository structure, `.gitignore`, `.env.example`, progress log and README.
