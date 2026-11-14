import type { HealthResponse } from "../types/api";

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch("/api/health", { signal });
  if (!response.ok) {
    throw new Error(`Backend health check failed: HTTP ${response.status}`);
  }
  return (await response.json()) as HealthResponse;
}
