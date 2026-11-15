// Types mirroring the FIRETRACE REST API (docs/api/README.md).
// Missing values are null, never 0.

export type Platform = "Terra" | "Aqua" | "Suomi-NPP" | "NOAA-20" | "NOAA-21";
export type Sensor = "MODIS" | "VIIRS";
export type CoverageStatus = "complete" | "partial" | "missing";
export type CellState = "value" | "zero" | "partial" | "uncovered" | "missing";
export type Metric = "detections" | "unique_cells" | "cell_days";

export interface HealthResponse {
  status: "ok";
  app: string;
  version: string;
  server_time_utc: string;
  firms_map_key_configured: boolean;
}

export interface SensorInfo {
  platform: Platform;
  sensor: Sensor;
  product: string;
  collection: string;
  nominal_pixel: string;
  firms_sources: string[];
}

export interface Hotspot {
  observation_id: string;
  latitude: number;
  longitude: number;
  acquisition_date: string;
  acquisition_time_utc: string;
  acquisition_datetime_utc: string;
  sensor: Sensor;
  platform: Platform;
  product: string;
  collection: string;
  collection_version: string;
  processing_status: string;
  confidence_raw: string | null;
  confidence_class: "low" | "nominal" | "high" | null;
  frp_mw: number | null;
  brightness_temperature: number | null;
  brightness_temperature_secondary: number | null;
  day_night: "D" | "N" | null;
  scan: number | null;
  track: number | null;
  hotspot_type: number | null;
  source_file: string;
  source_member: string | null;
  source_row_number: number;
  source_checksum: string;
  ingestion_timestamp: string;
  source_attributes?: string;
}

export interface Page<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export interface PlatformSummary {
  platform: Platform;
  detections: number;
  unique_cells: number;
  months_complete: number;
  months_partial: number;
  months_missing: number;
}

export interface Distribution {
  platform: Platform;
  detections: number;
  frp_values: number;
  frp_missing: number;
  frp_sum_mw: number | null;
  frp_mean_mw: number | null;
  frp_median_mw: number | null;
  frp_p90_mw: number | null;
  frp_p99_mw: number | null;
  frp_max_mw: number | null;
  confidence_low: number;
  confidence_nominal: number;
  confidence_high: number;
  confidence_missing: number;
  day: number;
  night: number;
  daynight_unknown: number;
}

export interface Summary {
  area: { west: number; south: number; east: number; north: number; country: string | null };
  period: { start: string; end: string };
  total_detections: number;
  first_detection_date: string | null;
  last_detection_date: string | null;
  platforms: PlatformSummary[];
  distributions: Distribution[];
  /** Period whose individual detections give the FRP median / percentiles. */
  frp_percentile_period?: { start: string; end: string };
  note: string;
}

export interface MonthRow {
  platform: Platform;
  year: number;
  month: number;
  days_in_range: number;
  days_covered: number;
  coverage_status: CoverageStatus;
  detections: number | null;
  cell_days: number | null;
  unique_cells: number | null;
  day_detections: number | null;
  night_detections: number | null;
  frp_sum_mw: number | null;
  frp_max_mw: number | null;
  processing_status_used: string;
}

export interface CalendarCell {
  platform: Platform;
  year: number;
  month: number;
  state: CellState;
  value: number | null;
  coverage_status: CoverageStatus;
  days_covered: number;
  days_in_range: number;
  modified_z: number | null;
  anomaly: string | null;
  anomaly_status: string | null;
}

export type HarmonizedReference = "modis" | "viirs";

export interface HarmonizedCell {
  platform: "Harmonized";
  year: number;
  month: number;
  state: CellState;
  value: number | null;
  coverage_status: CoverageStatus;
  days_covered: number;
  days_in_range: number;
  source: string | null;
  source_value: number | null;
  factor: number | null;
  relative_uncertainty: number | null;
  converted: boolean;
  note: string;
  modified_z: number | null;
  anomaly: string | null;
  anomaly_status: string | null;
}

export interface ConversionFit {
  source: string;
  reference: string;
  status: "reference" | "estimated" | "rejected" | "unavailable";
  reason: string;
  factor: number | null;
  n_train: number;
  n_validation: number;
  train_years: string;
  validation_years: string;
  bias: number | null;
  mae: number | null;
  rmse: number | null;
  relative_rmse: number | null;
  log_correlation: number | null;
}

export interface HarmonizedCalendar {
  status: string;
  reference: HarmonizedReference;
  reference_source: string;
  unit: string;
  metric: Metric;
  priority: string[];
  fits: ConversionFit[];
  cells: HarmonizedCell[];
}

export interface YearRow {
  platform: Platform;
  year: number;
  complete_months: number;
  months_with_values: number;
  total: number | null;
  complete_year: boolean;
  yoy_change: number | null;
  yoy_change_pct: number | null;
  yoy_note: string;
}

export interface Assessment {
  platform: Platform;
  year: number;
  month: number;
  metric: Metric;
  value: number | null;
  coverage_status: string;
  history_years: number;
  median: number | null;
  mad: number | null;
  modified_z: number | null;
  percentile_rank: number | null;
  status: string;
  label: string;
}

export interface Anomalies {
  status: string;
  target: string;
  metric: Metric;
  assessments: Assessment[];
  harmonized_index: {
    year: number;
    month: number;
    hai: number | null;
    sensors: string;
    platforms: string;
    status: string;
  }[];
}

export interface SavedAOI {
  id: number;
  name: string;
  kind: "bbox" | "polygon";
  bbox: [number, number, number, number];
  geojson: GeoJSONPolygon | null;
  country: string | null;
  created_utc: string;
}

export interface GeoJSONPolygon {
  type: "Polygon" | "MultiPolygon";
  coordinates: number[][][] | number[][][][];
}

export interface IngestRun {
  run_id: string;
  status: string;
  file: string;
  sha256: string;
  started_utc: string;
  finished_utc: string | null;
  rows_read: number;
  rows_valid: number;
  rows_invalid: number;
  rows_duplicate_in_file: number;
  rows_already_stored: number;
  rows_written: number;
  error: string | null;
}

export interface Availability {
  firms: {
    available: boolean;
    error?: string;
    products?: { data_id: string; min_date: string; max_date: string }[];
  };
  imported_coverage: {
    platform: string | null;
    processing_status: string | null;
    extent_type: string;
    first_date: string | null;
    last_date: string | null;
    coverage_records: number;
  }[];
  latest_completed_import_utc: string | null;
  note: string;
}
