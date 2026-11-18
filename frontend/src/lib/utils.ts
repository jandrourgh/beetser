import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / Math.pow(1024, index)).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return "–";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "never";
  const date = new Date(iso);
  const diff = Date.now() - date.getTime();
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diff < minute) return "just now";
  if (diff < hour) return `${Math.floor(diff / minute)}m ago`;
  if (diff < day) return `${Math.floor(diff / hour)}h ago`;
  if (diff < 30 * day) return `${Math.floor(diff / day)}d ago`;
  return date.toLocaleDateString();
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "–";
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  return `${Math.round(value * 100)}%`;
}

export function stateLabel(state: string): string {
  const labels: Record<string, string> = {
    discovered: "Queued",
    analyzing: "Analyzing",
    needs_review: "Needs review",
    ready: "Ready",
    importing: "Importing",
    imported: "Imported",
    duplicate: "Duplicate",
    skipped: "Skipped",
    failed: "Failed",
  };
  return labels[state] ?? state;
}

export function stateTone(state: string): "neutral" | "accent" | "success" | "warning" | "danger" {
  switch (state) {
    case "imported":
      return "success";
    case "needs_review":
    case "ready":
    case "analyzing":
    case "importing":
      return "accent";
    case "duplicate":
    case "discovered":
      return "warning";
    case "failed":
      return "danger";
    default:
      return "neutral";
  }
}

const toneTextClasses = {
  neutral: "text-muted",
  accent: "text-accent",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
} as const;

export function toneText(tone: keyof typeof toneTextClasses): string {
  return toneTextClasses[tone];
}

export function confidenceTone(value: number | null | undefined): "success" | "warning" | "danger" {
  if (value === null || value === undefined) return "danger";
  if (value >= 0.85) return "success";
  if (value >= 0.6) return "warning";
  return "danger";
}

export function displayArtist(value: string | null | undefined): string {
  if (!value) return "Unknown artist";
  const trimmed = value.trim();
  if (/^\[?(unknown|anonymous|various)\]?$/i.test(trimmed)) return "Unknown artist";
  return trimmed;
}

export function titleCase(value: string): string {
  return value.replace(/(^|\s)\S/g, (match) => match.toUpperCase());
}

export function pluralize(count: number, singular: string, plural?: string): string {
  return count === 1 ? singular : plural ?? `${singular}s`;
}

export function triggerDownload(url: string) {
  const link = document.createElement("a");
  link.href = url;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
}
