export interface HealthResponse {
  status: "ok";
  app: string;
  version: string;
  server_time_utc: string;
  firms_map_key_configured: boolean;
}
