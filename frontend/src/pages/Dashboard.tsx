import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Album,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FolderInput,
  HardDrive,
  ListChecks,
  Music4,
  RefreshCw,
  Sparkles,
  Users,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Badge,
  Button,
  Card,
  Cover,
  EmptyState,
  PageHeader,
  ProgressBar,
  SectionTitle,
  Skeleton,
} from "../components/ui";
import { apiClient } from "../lib/api";
import {
  displayArtist,
  formatBytes,
  formatRelative,
  percent,
  pluralize,
  stateLabel,
  stateTone,
} from "../lib/utils";

function Stat({
  label,
  value,
  hint,
  icon,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon: React.ReactNode;
  tone?: "neutral" | "accent" | "warning";
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</p>
          <p className="mt-2 text-2xl font-semibold tracking-tight text-fg">{value}</p>
          {hint && <p className="mt-0.5 text-[11px] text-muted">{hint}</p>}
        </div>
        <div
          className={
            "flex h-9 w-9 items-center justify-center rounded-xl " +
            (tone === "accent"
              ? "bg-accent-soft text-accent"
              : tone === "warning"
                ? "bg-warning-soft text-warning"
                : "bg-surface-2 text-muted")
          }
        >
          {icon}
        </div>
      </div>
    </Card>
  );
}

export function Dashboard() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const stats = useQuery({ queryKey: ["libraryStats"], queryFn: apiClient.libraryStats });
  const jobStats = useQuery({ queryKey: ["jobStats"], queryFn: apiClient.jobStats });
  const origins = useQuery({ queryKey: ["origins"], queryFn: apiClient.origins });
  const review = useQuery({
    queryKey: ["jobs", "review-preview"],
    queryFn: () => apiClient.jobs({ state: "review", per_page: 4 }),
  });
  const activity = useQuery({
    queryKey: ["activity", "preview"],
    queryFn: () => apiClient.activity({ limit: 6 }),
  });
  const info = useQuery({ queryKey: ["systemInfo"], queryFn: apiClient.info, staleTime: 60_000 });

  const scanAll = useMutation({
    mutationFn: async () => {
      const list = origins.data?.origins ?? [];
      await Promise.all(list.filter((origin) => origin.enabled).map((origin) => apiClient.scanOrigin(origin.id)));
    },
    onSuccess: () => {
      toast.success("Scan started");
      void queryClient.invalidateQueries();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Scan failed"),
  });

  const scanOne = useMutation({
    mutationFn: (id: string) => apiClient.scanOrigin(id),
    onSuccess: () => {
      toast.success("Scan queued");
      void queryClient.invalidateQueries();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Scan failed"),
  });

  const enabledOrigins = origins.data?.origins.filter((origin) => origin.enabled) ?? [];
  const reviewTotal = jobStats.data?.review ?? 0;
  const disk = info.data?.disk;

  return (
    <div className="animate-in">
      <PageHeader
        title="Dashboard"
        description="Your library at a glance, and everything waiting for a decision."
        actions={
          <>
            <Button
              variant="outline"
              icon={<RefreshCw className="h-4 w-4" />}
              loading={scanAll.isPending}
              onClick={() => scanAll.mutate()}
            >
              Scan all origins
            </Button>
            {reviewTotal > 0 && (
              <Button onClick={() => navigate("/review")} icon={<ListChecks className="h-4 w-4" />}>
                Review {reviewTotal} {pluralize(reviewTotal, "album")}
              </Button>
            )}
          </>
        }
      />

      {reviewTotal > 0 && (
        <Card className="surface-gradient mb-6 overflow-hidden border-accent/20 p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-4">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-accent text-white">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-semibold text-fg">
                  {reviewTotal} {pluralize(reviewTotal, "album")} waiting for confirmation
                </p>
                <p className="mt-1 text-xs text-muted">
                  Beetser auto-tags confident matches. Everything else lands here for a quick check.
                </p>
              </div>
            </div>
            <Link
              to="/review"
              className="inline-flex items-center gap-1.5 rounded-xl bg-accent px-4 py-2 text-xs font-semibold text-white transition hover:brightness-110"
            >
              Open review queue
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Albums"
          value={stats.data?.albums ?? "–"}
          hint={stats.data ? `${stats.data.tracks} tracks` : undefined}
          icon={<Album className="h-4 w-4" />}
          tone="accent"
        />
        <Stat
          label="Artists"
          value={stats.data?.artists ?? "–"}
          hint="in the central library"
          icon={<Users className="h-4 w-4" />}
        />
        <Stat
          label="Needs review"
          value={jobStats.data?.review ?? "–"}
          hint={`${jobStats.data?.active ?? 0} in progress`}
          icon={<AlertTriangle className="h-4 w-4" />}
          tone={reviewTotal > 0 ? "warning" : "neutral"}
        />
        <Stat
          label="Imported"
          value={jobStats.data?.counts?.imported ?? 0}
          hint="total jobs completed"
          icon={<CheckCircle2 className="h-4 w-4" />}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="min-w-0 lg:col-span-2">
          <SectionTitle
            title="Needs your attention"
            description="Uncertain matches and duplicate warnings"
            action={
              <Link to="/review" className="text-xs font-medium text-accent hover:underline">
                View all
              </Link>
            }
          />
          <div className="space-y-2">
            {review.isLoading && (
              <>
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
              </>
            )}
            {!review.isLoading && (review.data?.jobs.length ?? 0) === 0 && (
              <Card>
                <EmptyState
                  icon={<CheckCircle2 className="h-5 w-5 text-success" />}
                  title="Inbox zero"
                  description="Nothing is waiting for review. New albums will show up here automatically."
                />
              </Card>
            )}
            {review.data?.jobs.map((job) => (
              <Link key={job.id} to={`/review/${job.id}`} className="block">
                <Card className="group p-3 transition hover:border-accent/40">
                  <div className="flex items-center gap-3">
                    <Cover src={job.cover_url} alt={job.album ?? job.source_name} className="h-14 w-14 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="truncate text-sm font-medium text-fg">
                          {job.artist ? `${displayArtist(job.artist)} – ${job.album || job.source_name}` : job.source_name}
                        </p>
                        <Badge tone={stateTone(job.state)}>{stateLabel(job.state)}</Badge>
                      </div>
                      <p className="mt-0.5 truncate text-[11px] text-muted">
                        {job.origin_name} · {job.track_count} {pluralize(job.track_count, "track")} ·{" "}
                        {formatRelative(job.created_at)}
                      </p>
                      {job.best_similarity !== null && (
                        <div className="mt-2 flex items-center gap-2">
                          <ProgressBar
                            value={job.best_similarity}
                            tone={
                              job.best_similarity >= 0.85
                                ? "success"
                                : job.best_similarity >= 0.6
                                  ? "warning"
                                  : "danger"
                            }
                            className="max-w-[160px]"
                          />
                          <span className="text-[10px] text-muted">{percent(job.best_similarity)} match</span>
                        </div>
                      )}
                    </div>
                    <ArrowRight className="h-4 w-4 shrink-0 text-muted transition group-hover:translate-x-0.5 group-hover:text-accent" />
                  </div>
                </Card>
              </Link>
            ))}
          </div>

          <SectionTitle
            title="Origins"
            description="Folders Beetser watches for new music"
            action={
              <Link to="/origins" className="text-xs font-medium text-accent hover:underline">
                Manage
              </Link>
            }
          />
          <div className="grid gap-2 sm:grid-cols-2">
            {origins.isLoading && <Skeleton className="h-28 w-full" />}
            {enabledOrigins.map((origin) => (
              <Card key={origin.id} className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <FolderInput className="h-4 w-4 shrink-0 text-accent" />
                    <p className="truncate text-sm font-medium text-fg">{origin.name}</p>
                  </div>
                  <Badge tone={origin.watch ? "success" : "neutral"}>
                    {origin.watch ? "watching" : "polling"}
                  </Badge>
                </div>
                <p className="mt-2 truncate font-mono text-[11px] text-muted" title={origin.path}>
                  {origin.path}
                </p>
                <div className="mt-3 flex items-center justify-between">
                  <p className="text-[11px] text-muted">
                    {origin.job_counts.needs_review
                      ? `${origin.job_counts.needs_review} to review`
                      : `scanned ${formatRelative(origin.last_scan_at)}`}
                  </p>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => scanOne.mutate(origin.id)}
                    loading={scanOne.isPending && scanOne.variables === origin.id}
                    icon={<RefreshCw className="h-3.5 w-3.5" />}
                  >
                    Scan
                  </Button>
                </div>
              </Card>
            ))}
            {!origins.isLoading && enabledOrigins.length === 0 && (
              <Card className="sm:col-span-2">
                <EmptyState
                  icon={<FolderInput className="h-5 w-5" />}
                  title="No origins yet"
                  description="Add a folder that receives music from your download clients."
                  action={
                    <Link
                      to="/origins"
                      className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white"
                    >
                      Add an origin
                    </Link>
                  }
                />
              </Card>
            )}
          </div>
        </div>

        <div className="min-w-0">
          <SectionTitle title="Recent activity" />
          <Card className="divide-y divide-line">
            {(activity.data?.activity ?? []).map((item) => (
              <div key={item.id} className="flex gap-3 p-3">
                <span
                  className={
                    "mt-1 h-1.5 w-1.5 shrink-0 rounded-full " +
                    (item.level === "error"
                      ? "bg-danger"
                      : item.level === "warning"
                        ? "bg-warning"
                        : item.level === "success"
                          ? "bg-success"
                          : "bg-accent")
                  }
                />
                <div className="min-w-0">
                  <p className="text-xs leading-snug text-fg">{item.message}</p>
                  <p className="mt-0.5 text-[10px] text-muted">
                    {formatRelative(item.ts)}
                    {item.origin_name ? ` · ${item.origin_name}` : ""}
                  </p>
                </div>
              </div>
            ))}
            {!activity.isLoading && (activity.data?.activity.length ?? 0) === 0 && (
              <EmptyState icon={<Music4 className="h-5 w-5" />} title="Nothing yet" />
            )}
          </Card>

          <SectionTitle title="Storage" />
          <Card className="p-4">
            <div className="flex items-center gap-2 text-xs text-muted">
              <HardDrive className="h-4 w-4" />
              <span className="truncate font-mono">{info.data?.data_dir ?? "…"}</span>
            </div>
            {disk ? (
              <>
                <div className="mt-3 flex items-baseline justify-between text-xs">
                  <span className="text-muted">{formatBytes(disk.free)} free</span>
                  <span className="font-medium text-fg">{formatBytes(disk.total)}</span>
                </div>
                <ProgressBar className="mt-2" value={disk.used / disk.total} />
              </>
            ) : (
              <Skeleton className="mt-3 h-2 w-full" />
            )}
            <div className="mt-4 grid grid-cols-2 gap-2 text-[11px] text-muted">
              <div>
                <p className="uppercase tracking-wide">Queued jobs</p>
                <p className="mt-0.5 text-sm font-medium text-fg">{info.data?.queues.jobs ?? 0}</p>
              </div>
              <div>
                <p className="uppercase tracking-wide">Queued scans</p>
                <p className="mt-0.5 text-sm font-medium text-fg">{info.data?.queues.scans ?? 0}</p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
