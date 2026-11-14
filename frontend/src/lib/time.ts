// Timestamps from the API are ISO 8601 with an offset (UTC). Show them unambiguously.

/** "2026-11-14T07:19:51.5+00:00" → "2026-11-14 07:19 UTC". Unparseable → "—". */
export function formatUtc(iso: string | null | undefined): string {
  if (!iso) return "—";
  // A timestamp without an offset is treated as UTC (FIRETRACE stores UTC only).
  const hasOffset = /([zZ]|[+-]\d{2}:?\d{2})$/.test(iso);
  const date = new Date(hasOffset ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return "—";
  return `${date.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}
