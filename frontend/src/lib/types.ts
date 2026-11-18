export interface AuthStatus {
  authenticated: boolean;
  setup_required: boolean;
}

export type ImportMode = "inherit" | "move" | "copy";
export type AutoTagMode = "inherit" | "enabled" | "disabled";

export interface Origin {
  id: string;
  name: string;
  path: string;
  destination: string;
  destination_is_default: boolean;
  import_mode: ImportMode;
  effective_import_mode: "move" | "copy";
  path_format: string | null;
  singleton_path_format: string | null;
  auto_tag: AutoTagMode;
  auto_tag_threshold: number | null;
  effective_auto_tag_threshold: number;
  settled_seconds: number | null;
  watch: boolean;
  enabled: boolean;
  include_singletons: boolean;
  notes: string | null;
  path_exists: boolean;
  created_at: string | null;
  updated_at: string | null;
  last_scan_at: string | null;
  last_scan_status: string | null;
  last_error: string | null;
  job_counts: Record<string, number>;
}

export interface OriginInput {
  name: string;
  path: string;
  destination?: string | null;
  import_mode?: ImportMode;
  path_format?: string | null;
  singleton_path_format?: string | null;
  auto_tag?: AutoTagMode;
  auto_tag_threshold?: number | null;
  settled_seconds?: number | null;
  watch?: boolean;
  enabled?: boolean;
  include_singletons?: boolean;
  notes?: string | null;
}

export type JobState =
  | "discovered"
  | "analyzing"
  | "needs_review"
  | "ready"
  | "importing"
  | "imported"
  | "duplicate"
  | "skipped"
  | "failed";

export interface JobFile {
  path: string;
  name: string;
  size: number;
  mtime: number;
  sha256?: string | null;
  artist?: string;
  album?: string;
  albumartist?: string;
  title?: string;
  track?: number;
  disc?: number;
  length?: number;
  year?: number;
  format?: string;
}

export interface CandidateTrack {
  index: number;
  title: string;
  artist: string;
  length: number;
  medium: number;
  medium_index: number;
  track_id: string | null;
}

export interface Candidate {
  source: string;
  album_id: string | null;
  album: string;
  albumartist: string;
  year: number | null;
  month: number | null;
  day: number | null;
  country: string | null;
  label: string | null;
  catalognum: string | null;
  barcode: string | null;
  media: string | null;
  albumtype: string | null;
  albumstatus: string | null;
  albumdisambig: string | null;
  similarity: number;
  missing_tracks: number;
  extra_items: number;
  art_url: string | null;
  tracks: CandidateTrack[];
  mapping: Record<string, { index: number; medium_index: number; medium: number; title: string }>;
}

export interface DuplicateEntry {
  kind: string;
  message?: string;
  incoming_path?: string;
  library_path?: string;
  album?: string;
  albumartist?: string;
  album_id?: number;
  year?: number | null;
  title?: string;
  artist?: string;
  sha256?: string;
  track_count?: number;
  title_overlap?: number;
  reason?: string;
}

export interface DuplicateReport {
  exact: DuplicateEntry[];
  tracks: DuplicateEntry[];
  albums: DuplicateEntry[];
  blocking: boolean;
  summary: string | null;
}

export interface Job {
  id: string;
  origin_id: string;
  origin_name: string | null;
  kind: "album" | "singleton";
  source_dir: string;
  source_name: string;
  state: JobState;
  artist: string | null;
  album: string | null;
  year: number | null;
  track_count: number;
  best_similarity: number | null;
  recommendation: string | null;
  auto: boolean;
  files: JobFile[];
  candidates: Candidate[];
  candidate_count: number;
  cover_url: string | null;
  duplicates: DuplicateReport | null;
  duplicate_summary: string | null;
  chosen_release_id: string | null;
  chosen_source: string | null;
  applied_fields: Record<string, string>;
  applied_tracks: Record<string, Record<string, unknown>>;
  library_album_id: number | null;
  library_item_ids: number[];
  error: string | null;
  log_tail: string | null;
  created_at: string | null;
  updated_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobStats {
  counts: Record<string, number>;
  review: number;
  active: number;
  total: number;
}

export interface ActivityItem {
  id: number;
  ts: string;
  level: string;
  category: string;
  origin_id: string | null;
  origin_name: string | null;
  job_id: string | null;
  message: string;
  detail: unknown;
}

export interface LibraryStats {
  albums: number;
  tracks: number;
  artists: number;
  last_added: string | null;
  library_path: string;
}

export interface AlbumSummary {
  id: number;
  album: string;
  albumartist: string;
  year: number | null;
  artpath: string | null;
  art_mtime?: number | null;
  track_count: number;
  path: string | null;
  mb_albumid: string | null;
  added: string | null;
}

export interface AlbumTrack {
  id: number;
  path: string;
  title: string;
  artist: string;
  track: number;
  disc: number;
  length: number;
  genres: string;
  mb_trackid: string | null;
  bitrate: number | null;
  format: string;
  mtime: number;
}

export interface AlbumDetail extends AlbumSummary {
  label: string | null;
  catalognum: string | null;
  country: string | null;
  albumtype: string | null;
  albumdisambig: string | null;
  genres: string;
  barcode: string | null;
  asin: string | null;
  media: string | null;
  tracks: AlbumTrack[];
}

export interface AlbumUpdate {
  fields: Record<string, string>;
  tracks: Record<number, Record<string, string>>;
  write_tags: boolean;
  move_files: boolean;
}

export interface AlbumUpdateResponse {
  ok: boolean;
  output: string;
  warnings: string[];
  album: AlbumDetail;
}

export interface AlbumArtResponse {
  ok: boolean;
  artpath: string;
  warnings: string[];
  album: AlbumDetail;
}

export interface SingleTrack {
  id: number;
  path: string;
  title: string;
  artist: string;
  album: string;
  albumartist: string;
  length: number;
  year: number | null;
  genres: string;
  format: string;
  mtime: number;
}

export interface AppSettings {
  import_mode: "move" | "copy";
  path_format: string;
  comp_path_format: string;
  singleton_path_format: string;
  write_tags: boolean;
  delete_empty_dirs: boolean;
  auto_tag_enabled: boolean;
  auto_tag_threshold: number;
  auto_tag_min_gap: number;
  fetch_art: boolean;
  embed_art: boolean;
  settle_seconds: number;
  scan_interval_seconds: number;
  include_singletons: boolean;
  notify_webhook_url: string;
  notify_on_review: boolean;
  notify_on_import: boolean;
  notify_on_error: boolean;
  ignore_globs: string[];
  ignore_dirs: string[];
}

export interface SystemInfo {
  beetser_version: string;
  beets_version: string;
  python_version: string;
  library_path: string;
  data_dir: string;
  library_exists: boolean;
  disk: { total: number; used: number; free: number };
  scan_interval: number;
  queues: { jobs: number; scans: number };
  setup_required: boolean;
}

export interface LogEntry {
  id: number;
  ts: string;
  level: string;
  logger: string;
  message: string;
}

export interface BrowseEntry {
  name: string;
  path: string;
  type: "dir" | "file";
}

export interface BrowseResult {
  path: string;
  parent: string | null;
  entries: BrowseEntry[];
  truncated: boolean;
}

export interface ApplyRequest {
  mode: "candidate" | "asis" | "manual" | "reanalyze" | "retry" | "skip";
  release_id?: string | null;
  fields?: Record<string, string>;
  tracks?: Record<string, Record<string, unknown>>;
  force?: boolean;
}

export interface OriginTestResult {
  path: string;
  exists: boolean;
  readable: boolean;
  destination: string;
  destination_writable: boolean;
  audio_files: number;
  error: string | null;
}
