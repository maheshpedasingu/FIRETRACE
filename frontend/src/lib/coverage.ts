/** Count display that never turns missing data into zero. */

export interface PlatformCoverage {
  detections: number | null | undefined;
  months_complete: number;
  months_partial: number;
}

/**
 * A count is a real number when the platform had some imported coverage of the area
 * (complete or partial months) or when detections exist (then it is a lower bound).
 * With neither, nothing is known: return null so the UI shows "—", not 0.
 */
export function coveredCount(
  value: number | null | undefined,
  p: PlatformCoverage,
): number | null {
  const covered = p.months_complete + p.months_partial > 0;
  const detected = (p.detections ?? 0) > 0;
  if (!covered && !detected) return null;
  return value ?? null;
}
