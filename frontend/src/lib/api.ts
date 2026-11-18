import type {
  ActivityItem,
  AlbumArtResponse,
  AlbumDetail,
  AlbumSummary,
  AlbumUpdate,
  AlbumUpdateResponse,
  AppSettings,
  ApplyRequest,
  AuthStatus,
  BrowseResult,
  Job,
  JobStats,
  LibraryStats,
  LogEntry,
  Origin,
  OriginInput,
  OriginTestResult,
  SingleTrack,
  SystemInfo,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (response.status === 401 && !path.startsWith("/api/auth/")) {
    window.dispatchEvent(new Event("beetser:unauthorized"));
  }

  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(data, response.status));
  }
  return data as T;
}

async function apiForm<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(path, {
    method: "PUT",
    credentials: "same-origin",
    body: form,
  });
  if (response.status === 401) {
    window.dispatchEvent(new Event("beetser:unauthorized"));
  }
  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(data, response.status));
  }
  return data as T;
}

function errorMessage(data: unknown, status: number): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      return String((detail as { message: unknown }).message);
    }
    return String(detail);
  }
  return `Request failed (${status})`;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  body: JSON.stringify(body),
});

export const apiClient = {
  authStatus: () => api<AuthStatus>("/api/auth/status"),
  login: (password: string) => api<{ ok: boolean }>("/api/auth/login", json("POST", { password })),
  setup: (password: string) => api<{ ok: boolean }>("/api/auth/setup", json("POST", { password })),
  logout: () => api<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  changePassword: (current_password: string, new_password: string) =>
    api<{ ok: boolean }>("/api/auth/password", json("POST", { current_password, new_password })),

  origins: () => api<{ origins: Origin[] }>("/api/origins"),
  createOrigin: (input: OriginInput) => api<Origin>("/api/origins", json("POST", input)),
  updateOrigin: (id: string, input: Partial<OriginInput>) =>
    api<Origin>(`/api/origins/${id}`, json("PATCH", input)),
  deleteOrigin: (id: string) => api<void>(`/api/origins/${id}`, { method: "DELETE" }),
  scanOrigin: (id: string) => api<{ queued: boolean }>(`/api/origins/${id}/scan`, { method: "POST" }),
  testOrigin: (id: string, path?: string, destination?: string) =>
    api<OriginTestResult>(`/api/origins/${id}/test`, json("POST", { path, destination })),

  jobs: (params: { state?: string; origin_id?: string; q?: string; page?: number; per_page?: number } = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
    });
    return api<{ jobs: Job[]; total: number; page: number; per_page: number }>(`/api/jobs?${search}`);
  },
  job: (id: string) => api<Job>(`/api/jobs/${id}`),
  jobStats: () => api<JobStats>("/api/jobs/stats"),
  applyJob: (id: string, payload: ApplyRequest) => api<Job>(`/api/jobs/${id}/apply`, json("POST", payload)),
  skipJob: (id: string) => api<{ ok: boolean }>(`/api/jobs/${id}/skip`, { method: "POST" }),
  forgetJob: (id: string) => api<void>(`/api/jobs/${id}`, { method: "DELETE" }),

  libraryStats: () => api<LibraryStats>("/api/library/stats"),
  albums: (params: { q?: string; page?: number; per_page?: number } = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
    });
    return api<{ albums: AlbumSummary[]; total: number; page: number; per_page: number }>(
      `/api/library/albums?${search}`,
    );
  },
  album: (id: number) => api<AlbumDetail>(`/api/library/albums/${id}`),
  singles: (params: { q?: string; page?: number; per_page?: number } = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
    });
    return api<{ tracks: SingleTrack[]; total: number; page: number; per_page: number }>(
      `/api/library/singles?${search}`,
    );
  },
  coverUrl: (albumId: number, version?: number | null) =>
    `/api/library/albums/${albumId}/cover${version ? `?v=${version}` : ""}`,
  jobCover: (jobId: string, index: number) => `/api/jobs/${jobId}/candidates/${index}/cover`,
  updateAlbum: (albumId: number, payload: AlbumUpdate) =>
    api<AlbumUpdateResponse>(`/api/library/albums/${albumId}`, json("PATCH", payload)),
  uploadAlbumCover: (albumId: number, file: File, embed?: boolean) => {
    const form = new FormData();
    form.append("file", file);
    if (embed !== undefined) form.append("embed", String(embed));
    return apiForm<AlbumArtResponse>(`/api/library/albums/${albumId}/cover`, form);
  },
  deleteAlbumCover: (albumId: number) =>
    api<AlbumArtResponse>(`/api/library/albums/${albumId}/cover`, { method: "DELETE" }),
  fetchAlbumCover: (albumId: number) =>
    api<AlbumArtResponse>(`/api/library/albums/${albumId}/cover/fetch`, { method: "POST" }),

  activity: (params: { limit?: number; before_id?: number; level?: string; category?: string; origin_id?: string } = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
    });
    return api<{ activity: ActivityItem[]; next_before_id: number | null }>(`/api/activity?${search}`);
  },
  clearActivity: () => api<void>("/api/activity", { method: "DELETE" }),

  settings: () => api<AppSettings>("/api/settings"),
  updateSettings: (values: Partial<AppSettings>) =>
    api<AppSettings>("/api/settings", json("PATCH", { values })),
  resetSettings: () => api<AppSettings>("/api/settings/reset", { method: "POST" }),

  info: () => api<SystemInfo>("/api/system/info"),
  logs: (afterId = 0) => api<{ logs: LogEntry[]; last_id: number }>(`/api/system/logs?after_id=${afterId}`),
  browse: (path: string) => api<BrowseResult>(`/api/system/browse?path=${encodeURIComponent(path)}`),
};
