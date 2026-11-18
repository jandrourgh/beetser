import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronUp,
  Disc3,
  FileAudio,
  FolderOpen,
  ListChecks,
  Pencil,
  RotateCcw,
  ShieldAlert,
  SkipForward,
  Sparkles,
  Wand2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  Badge,
  Button,
  Card,
  Cover,
  EmptyState,
  Field,
  Modal,
  PageHeader,
  ProgressBar,
  Segmented,
  Select,
  Skeleton,
  Tag,
  TextInput,
} from "../components/ui";
import { apiClient } from "../lib/api";
import type { ApplyRequest, Candidate, Job, JobState } from "../lib/types";
import {
  cn,
  confidenceTone,
  displayArtist,
  formatBytes,
  formatDuration,
  formatRelative,
  percent,
  pluralize,
  stateLabel,
  stateTone,
  toneText,
} from "../lib/utils";

type Filter = "review" | "duplicate" | "failed" | "all";

const filters: { value: Filter; label: string }[] = [
  { value: "review", label: "Needs review" },
  { value: "duplicate", label: "Duplicates" },
  { value: "failed", label: "Failed" },
  { value: "all", label: "All" },
];

const activeStates: JobState[] = ["discovered", "analyzing", "ready", "importing"];

export function ReviewPage() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [filter, setFilter] = useState<Filter>("review");
  const [originFilter, setOriginFilter] = useState("");

  const jobs = useQuery({
    queryKey: ["jobs", filter, originFilter],
    queryFn: () =>
      apiClient.jobs({
        state: filter === "all" ? undefined : filter,
        origin_id: originFilter || undefined,
        per_page: 100,
      }),
  });

  const origins = useQuery({ queryKey: ["origins"], queryFn: apiClient.origins });
  const stats = useQuery({ queryKey: ["jobStats"], queryFn: apiClient.jobStats });

  const selectedId = jobId ?? jobs.data?.jobs[0]?.id;

  useEffect(() => {
    if (!jobId && selectedId) {
      navigate(`/review/${selectedId}`, { replace: true });
    }
  }, [jobId, selectedId, navigate]);

  return (
    <div className="animate-in">
      <PageHeader
        title="Review queue"
        description="Confirm uncertain matches, resolve duplicates, and retry failed imports."
        actions={
          <div className="flex items-center gap-2">
            <Select value={originFilter} onChange={(event) => setOriginFilter(event.target.value)} className="w-44">
              <option value="">All origins</option>
              {origins.data?.origins.map((origin) => (
                <option key={origin.id} value={origin.id}>
                  {origin.name}
                </option>
              ))}
            </Select>
          </div>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Segmented
          value={filter}
          onChange={(value) => setFilter(value)}
          options={filters.map((item) => ({
            ...item,
            count:
              item.value === "review"
                ? stats.data?.review
                : item.value === "duplicate"
                  ? stats.data?.counts?.duplicate
                  : item.value === "failed"
                    ? stats.data?.counts?.failed
                    : stats.data?.total,
          }))}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-2 lg:max-h-[calc(100vh-14rem)] lg:overflow-y-auto lg:pr-1">
          {jobs.isLoading && (
            <>
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
            </>
          )}
          {jobs.data?.jobs.map((job) => (
            <button
              key={job.id}
              type="button"
              onClick={() => navigate(`/review/${job.id}`)}
              className={cn(
                "w-full rounded-2xl border p-3 text-left transition",
                job.id === selectedId
                  ? "border-accent/50 bg-accent-soft/40"
                  : "border-line bg-surface hover:border-accent/30",
              )}
            >
              <div className="flex items-center gap-3">
                <Cover src={job.cover_url} alt={job.album ?? job.source_name} className="h-12 w-12 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-fg">
                    {job.artist ? `${job.artist} – ${job.album || job.source_name}` : job.source_name}
                  </p>
                  <div className="mt-1 flex items-center gap-1.5">
                    <Badge tone={stateTone(job.state)}>{stateLabel(job.state)}</Badge>
                    {job.best_similarity !== null && (
                      <span className={cn("text-[10px]", toneText(confidenceTone(job.best_similarity)))}>
                        {percent(job.best_similarity)}
                      </span>
                    )}
                    <span className="text-[10px] text-muted">· {formatRelative(job.created_at)}</span>
                  </div>
                </div>
              </div>
            </button>
          ))}
          {!jobs.isLoading && (jobs.data?.jobs.length ?? 0) === 0 && (
            <Card>
              <EmptyState
                icon={<Check className="h-5 w-5 text-success" />}
                title="All clear"
                description="No jobs match this filter."
              />
            </Card>
          )}
        </div>

        <div className="min-w-0">
          {selectedId ? (
            <JobDetail key={selectedId} jobId={selectedId} />
          ) : (
            <Card>
              <EmptyState
                icon={<ListChecks className="h-5 w-5" />}
                title="Select a job"
                description="Pick an item from the queue to see its candidates and files."
              />
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function JobDetail({ jobId }: { jobId: string }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [tab, setTab] = useState<"candidates" | "files" | "duplicates" | "log">("candidates");
  const [manualOpen, setManualOpen] = useState(false);
  const [forceOpen, setForceOpen] = useState<{ releaseId?: string; asis?: boolean } | null>(null);

  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => apiClient.job(jobId),
    refetchInterval: (query) => {
      const data = query.state.data as Job | undefined;
      return data && activeStates.includes(data.state) ? 1500 : false;
    },
  });

  useEffect(() => {
    if (jobQuery.data) {
      const state = jobQuery.data.state;
      if (state === "needs_review" || state === "duplicate" || state === "failed") setTab("candidates");
    }
  }, [jobQuery.data?.id]);

  const apply = useMutation({
    mutationFn: (payload: ApplyRequest) => apiClient.applyJob(jobId, payload),
    onSuccess: (job) => {
      toast.success(
        job.state === "ready" || job.state === "importing" ? "Import started" : `Job ${stateLabel(job.state).toLowerCase()}`,
      );
      setForceOpen(null);
      void queryClient.invalidateQueries();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Action failed"),
  });

  const skip = useMutation({
    mutationFn: () => apiClient.skipJob(jobId),
    onSuccess: () => {
      toast.success("Job skipped");
      void queryClient.invalidateQueries();
      navigate("/review");
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not skip"),
  });

  const forget = useMutation({
    mutationFn: () => apiClient.forgetJob(jobId),
    onSuccess: () => {
      toast.success("Job removed");
      void queryClient.invalidateQueries();
      navigate("/review");
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not remove job"),
  });

  const job = jobQuery.data;

  if (jobQuery.isLoading || !job) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const best = job.candidates[0];
  const actionable = ["needs_review", "duplicate", "failed"].includes(job.state);
  const busy = apply.isPending || skip.isPending;

  const applyCandidate = (candidate: Candidate) => {
    if (job.state === "duplicate") {
      setForceOpen({ releaseId: candidate.album_id ?? undefined });
      return;
    }
    apply.mutate({ mode: "candidate", release_id: candidate.album_id });
  };

  const importAsIs = () => {
    if (job.state === "duplicate") {
      setForceOpen({ asis: true });
      return;
    }
    apply.mutate({ mode: "asis" });
  };

  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        <div className="surface-gradient flex flex-col gap-5 p-5 sm:flex-row">
          <Cover
            src={job.cover_url}
            alt={job.album ?? job.source_name}
            className="h-32 w-32 shrink-0 shadow-lg sm:h-36 sm:w-36"
            rounded="rounded-2xl"
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={stateTone(job.state)}>{stateLabel(job.state)}</Badge>
              {job.kind === "singleton" && <Badge>singleton</Badge>}
              {job.auto && <Badge tone="accent">auto</Badge>}
              {job.origin_name && <span className="text-[11px] text-muted">from {job.origin_name}</span>}
            </div>
            <h2 className="mt-2 truncate text-xl font-semibold tracking-tight text-fg">
              {job.album || job.source_name}
            </h2>
            <p className="mt-0.5 text-sm text-muted">
              {displayArtist(job.artist)}
              {job.year ? ` · ${job.year}` : ""}
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] text-muted">
              <span className="inline-flex items-center gap-1.5">
                <FileAudio className="h-3.5 w-3.5" />
                {job.track_count} {pluralize(job.track_count, "track")}
              </span>
              <span className="inline-flex min-w-0 items-center gap-1.5">
                <FolderOpen className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate font-mono" title={job.source_dir}>
                  {job.source_dir}
                </span>
              </span>
              <span>{formatRelative(job.created_at)}</span>
            </div>

            {job.best_similarity !== null && (
              <div className="mt-4 max-w-sm">
                <div className="mb-1 flex items-center justify-between text-[11px]">
                  <span className="text-muted">Best match confidence</span>
                  <span className={cn("font-semibold", toneText(confidenceTone(job.best_similarity)))}>
                    {percent(job.best_similarity)}
                  </span>
                </div>
                <ProgressBar value={job.best_similarity} tone={confidenceTone(job.best_similarity)} />
              </div>
            )}

            {job.error && (
              <p className="mt-3 rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger">{job.error}</p>
            )}
          </div>
        </div>

        {actionable && (
          <div className="flex flex-wrap items-center gap-2 border-t border-line px-5 py-3">
            {best && (
              <Button
                icon={<Wand2 className="h-4 w-4" />}
                loading={apply.isPending}
                onClick={() => applyCandidate(best)}
              >
                Apply best match
              </Button>
            )}
            <Button variant="secondary" onClick={importAsIs} disabled={busy} icon={<Check className="h-4 w-4" />}>
              Import as-is
            </Button>
            <Button variant="outline" onClick={() => setManualOpen(true)} disabled={busy} icon={<Pencil className="h-4 w-4" />}>
              Edit tags
            </Button>
            <Button
              variant="ghost"
              onClick={() => apply.mutate({ mode: "reanalyze" })}
              disabled={busy}
              icon={<RotateCcw className="h-4 w-4" />}
            >
              Re-analyze
            </Button>
            <div className="ml-auto flex items-center gap-2">
              <Button variant="ghost" onClick={() => skip.mutate()} loading={skip.isPending} icon={<SkipForward className="h-4 w-4" />}>
                Skip
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  if (window.confirm("Remove this job? The files stay on disk and will be discovered again.")) {
                    forget.mutate();
                  }
                }}
                icon={<X className="h-4 w-4" />}
              >
                Remove
              </Button>
            </div>
          </div>
        )}
      </Card>

      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        <Segmented
          value={tab}
          onChange={setTab}
          options={[
            { value: "candidates", label: "Candidates", count: job.candidate_count },
            { value: "files", label: "Files", count: job.files.length },
            ...(job.duplicates && job.duplicates.blocking
              ? [{ value: "duplicates" as const, label: "Duplicates" }]
              : []),
            { value: "log", label: "Log" },
          ]}
        />
      </div>

      {tab === "candidates" && (
        <div className="space-y-3">
          {job.candidates.length === 0 && (
            <Card>
              <EmptyState
                icon={<Sparkles className="h-5 w-5" />}
                title="No candidates found"
                description={
                  job.error
                    ? job.error
                    : "MusicBrainz returned nothing useful. Import the files as-is, or edit the tags manually."
                }
                action={
                  <Button variant="secondary" onClick={() => setManualOpen(true)} icon={<Pencil className="h-4 w-4" />}>
                    Edit tags manually
                  </Button>
                }
              />
            </Card>
          )}
          {job.candidates.map((candidate, index) => (
            <CandidateCard
              key={`${candidate.source}-${candidate.album_id}-${index}`}
              candidate={candidate}
              job={job}
              index={index}
              onApply={() => applyCandidate(candidate)}
              disabled={!actionable || busy}
            />
          ))}
        </div>
      )}

      {tab === "files" && <FilesTable job={job} />}
      {tab === "duplicates" && job.duplicates && <DuplicatesPanel job={job} onForce={importAsIs} />}

      {tab === "log" && (
        <Card className="p-4">
          <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-all rounded-lg bg-surface-2 p-3 font-mono text-[11px] leading-relaxed text-muted">
            {job.log_tail || job.error || "No log output yet."}
          </pre>
        </Card>
      )}

      <ManualEditModal
        job={job}
        open={manualOpen}
        onClose={() => setManualOpen(false)}
        onSubmit={(fields, tracks) => {
          apply.mutate({ mode: "manual", fields, tracks });
          setManualOpen(false);
        }}
      />

      <Modal
        open={forceOpen !== null}
        onClose={() => setForceOpen(null)}
        title="Import despite duplicate?"
        description="Beetser thinks this music is already in your library."
        footer={
          <>
            <Button variant="ghost" onClick={() => setForceOpen(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={apply.isPending}
              onClick={() => {
                if (!forceOpen) return;
                if (forceOpen.releaseId) {
                  apply.mutate({ mode: "candidate", release_id: forceOpen.releaseId, force: true });
                } else {
                  apply.mutate({ mode: "asis", force: true });
                }
              }}
            >
              Import anyway
            </Button>
          </>
        }
      >
        <div className="space-y-3 text-sm">
          {job.duplicate_summary && (
            <p className="rounded-lg bg-warning-soft px-3 py-2 text-xs text-warning">{job.duplicate_summary}</p>
          )}
          <p className="text-xs text-muted">
            This will add another copy to the central library. Use this when the recording is genuinely different
            (for example a remaster or a different edition).
          </p>
        </div>
      </Modal>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function CandidateCard({
  candidate,
  job,
  index,
  onApply,
  disabled,
}: {
  candidate: Candidate;
  job: Job;
  index: number;
  onApply: () => void;
  disabled: boolean;
}) {
  const [expanded, setExpanded] = useState(index === 0);
  const mapped = Object.keys(candidate.mapping ?? {}).length;

  return (
    <Card className={cn("overflow-hidden transition", index === 0 && "border-accent/30")}>
      <div className="flex flex-col gap-4 p-4 sm:flex-row">
        <Cover
          src={apiClient.jobCover(job.id, index)}
          alt={candidate.album}
          className="h-24 w-24 shrink-0"
          rounded="rounded-xl"
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={index === 0 ? "accent" : "neutral"}>{index === 0 ? "Best match" : `#${index + 1}`}</Badge>
            <Badge>{candidate.source}</Badge>
            {candidate.albumtype && <Badge>{candidate.albumtype}</Badge>}
            {candidate.media && <Tag>{candidate.media}</Tag>}
          </div>
          <h3 className="mt-1.5 truncate text-sm font-semibold text-fg">
            {displayArtist(candidate.albumartist)} – {candidate.album || "Unknown album"}
          </h3>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
            {candidate.year && <span>{candidate.year}</span>}
            {candidate.country && <span>{candidate.country}</span>}
            {candidate.label && <span className="truncate">{candidate.label}</span>}
            {candidate.catalognum && <span className="font-mono">{candidate.catalognum}</span>}
            <span>
              {candidate.tracks.length} {pluralize(candidate.tracks.length, "track")}
            </span>
            {candidate.missing_tracks > 0 && (
              <span className="text-warning">
                {candidate.missing_tracks} {pluralize(candidate.missing_tracks, "track")} missing
              </span>
            )}
            {candidate.extra_items > 0 && <span className="text-warning">{candidate.extra_items} unmatched</span>}
          </div>

          <div className="mt-3 flex items-center gap-2">
            <ProgressBar
              value={candidate.similarity}
              tone={confidenceTone(candidate.similarity)}
              className="max-w-[220px]"
            />
            <span className={cn("text-[11px] font-medium", toneText(confidenceTone(candidate.similarity)))}>
              {percent(candidate.similarity)}
            </span>
            <span className="text-[10px] text-muted">
              {mapped}/{job.files.length} files mapped
            </span>
          </div>
        </div>

        <div className="flex shrink-0 flex-col gap-2">
          <Button size="sm" onClick={onApply} disabled={disabled} loading={false} icon={<Wand2 className="h-3.5 w-3.5" />}>
            Use this release
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setExpanded((value) => !value)}
            icon={expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          >
            Tracklist
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-line bg-surface-2/30 px-4 py-3">
          <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
            {candidate.tracks.map((track) => (
              <div key={`${track.medium}-${track.index}-${track.title}`} className="flex items-baseline gap-2 py-0.5">
                <span className="w-6 shrink-0 text-right font-mono text-[10px] text-muted">
                  {track.medium_index || track.index}
                </span>
                <span className="min-w-0 flex-1 truncate text-xs text-fg">{track.title}</span>
                <span className="text-[10px] text-muted">{formatDuration(track.length)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ */

function FilesTable({ job }: { job: Job }) {
  const best = job.candidates[0];
  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-line bg-surface-2/50 text-[11px] uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-2.5 font-medium">File</th>
              <th className="px-4 py-2.5 font-medium">Current tags</th>
              <th className="px-4 py-2.5 font-medium">Proposed</th>
              <th className="px-4 py-2.5 text-right font-medium">Length</th>
              <th className="px-4 py-2.5 text-right font-medium">Size</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {job.files.map((file) => {
              const mapping = best?.mapping?.[file.path];
              return (
                <tr key={file.path} className="hover:bg-surface-2/40">
                  <td className="max-w-[240px] px-4 py-2.5">
                    <p className="truncate font-mono text-[11px] text-fg" title={file.path}>
                      {file.name}
                    </p>
                    <p className="truncate text-[10px] text-muted">{file.format || "audio"}</p>
                  </td>
                  <td className="px-4 py-2.5">
                    <p className="truncate text-fg">{file.title || "—"}</p>
                    <p className="truncate text-[10px] text-muted">
                      {[file.artist, file.album].filter(Boolean).join(" · ") || "no tags"}
                    </p>
                  </td>
                  <td className="px-4 py-2.5">
                    {mapping ? (
                      <>
                        <p className="truncate text-fg">{mapping.title}</p>
                        <p className="text-[10px] text-muted">
                          track {mapping.medium_index || mapping.index}
                        </p>
                      </>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right text-muted">{formatDuration(file.length)}</td>
                  <td className="px-4 py-2.5 text-right text-muted">{formatBytes(file.size)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ */

function DuplicatesPanel({ job, onForce }: { job: Job; onForce: () => void }) {
  const duplicate = job.duplicates!;
  const sections = [
    { key: "exact", label: "Identical files", icon: <ShieldAlert className="h-4 w-4" />, items: duplicate.exact },
    { key: "albums", label: "Albums in library", icon: <Disc3 className="h-4 w-4" />, items: duplicate.albums },
    { key: "tracks", label: "Matching tracks", icon: <FileAudio className="h-4 w-4" />, items: duplicate.tracks },
  ].filter((section) => section.items.length > 0);

  return (
    <div className="space-y-3">
      <Card className="border-warning/30 bg-warning-soft/40 p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-fg">Possible duplicate</p>
            <p className="mt-0.5 text-xs text-muted">
              {duplicate.summary ?? "This music appears to exist in the library already."}
            </p>
          </div>
          <Button variant="outline" size="sm" className="ml-auto shrink-0" onClick={onForce}>
            Import anyway
          </Button>
        </div>
      </Card>

      {sections.map((section) => (
        <Card key={section.key} className="overflow-hidden">
          <div className="flex items-center gap-2 border-b border-line px-4 py-2.5 text-xs font-medium text-fg">
            <span className="text-muted">{section.icon}</span>
            {section.label}
            <Badge className="ml-auto">{section.items.length}</Badge>
          </div>
          <div className="divide-y divide-line">
            {section.items.map((item, index) => (
              <div key={index} className="px-4 py-3 text-xs">
                <p className="font-medium text-fg">
                  {item.album ? `${item.albumartist} – ${item.album}` : item.title || item.incoming_path}
                </p>
                <p className="mt-0.5 text-muted">{item.message || item.reason}</p>
                {item.library_path && (
                  <p className="mt-1 truncate font-mono text-[10px] text-muted" title={item.library_path}>
                    {item.library_path}
                  </p>
                )}
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function ManualEditModal({
  job,
  open,
  onClose,
  onSubmit,
}: {
  job: Job;
  open: boolean;
  onClose: () => void;
  onSubmit: (fields: Record<string, string>, tracks: Record<string, Record<string, unknown>>) => void;
}) {
  const best = job.candidates[0];
  const reference = best && best.similarity >= 0.6 ? best : null;
  const initial = useMemo(() => {
    const first = job.files[0];
    return {
      albumartist: reference?.albumartist || first?.albumartist || first?.artist || "",
      album: reference?.album || first?.album || "",
      year: reference?.year ? String(reference.year) : first?.year ? String(first.year) : "",
      genre: "",
      label: reference?.label ?? "",
      catalognum: reference?.catalognum ?? "",
      country: reference?.country ?? "",
      albumdisambig: reference?.albumdisambig ?? "",
    };
  }, [job.id, reference?.album_id]);

  const [fields, setFields] = useState<Record<string, string>>(initial);
  const [titles, setTitles] = useState<Record<string, { title: string; track: string }>>({});

  useEffect(() => {
    if (!open) return;
    setFields(initial);
    const next: Record<string, { title: string; track: string }> = {};
    job.files.forEach((file, index) => {
      const mapping = reference?.mapping?.[file.path];
      next[file.path] = {
        title: mapping?.title || file.title || file.name.replace(/\.[^.]+$/, ""),
        track: String(mapping?.medium_index || mapping?.index || file.track || index + 1),
      };
    });
    setTitles(next);
  }, [open, job.id]);

  const update = (key: string, value: string) => setFields((current) => ({ ...current, [key]: value }));

  const submit = () => {
    const cleaned: Record<string, string> = {};
    Object.entries(fields).forEach(([key, value]) => {
      if (value.trim()) cleaned[key] = value.trim();
    });
    const tracks: Record<string, Record<string, unknown>> = {};
    Object.entries(titles).forEach(([path, value]) => {
      tracks[path] = {
        title: value.title,
        ...(Number(value.track) ? { track: Number(value.track) } : {}),
      };
    });
    onSubmit(cleaned, tracks);
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Edit tags before importing"
      description="These values are written to the files, then beets organizes them using your path format."
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} icon={<Check className="h-4 w-4" />}>
            Save &amp; import
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Album artist">
            <TextInput value={fields.albumartist} onChange={(event) => update("albumartist", event.target.value)} />
          </Field>
          <Field label="Album">
            <TextInput value={fields.album} onChange={(event) => update("album", event.target.value)} />
          </Field>
          <Field label="Year">
            <TextInput inputMode="numeric" value={fields.year} onChange={(event) => update("year", event.target.value)} />
          </Field>
          <Field label="Genre">
            <TextInput value={fields.genre} onChange={(event) => update("genre", event.target.value)} />
          </Field>
          <Field label="Label">
            <TextInput value={fields.label} onChange={(event) => update("label", event.target.value)} />
          </Field>
          <Field label="Catalogue number">
            <TextInput value={fields.catalognum} onChange={(event) => update("catalognum", event.target.value)} />
          </Field>
        </div>

        <div>
          <p className="mb-2 text-xs font-medium text-fg">Tracks</p>
          <div className="space-y-2">
            {job.files.map((file) => (
              <div key={file.path} className="flex items-center gap-2 rounded-xl border border-line bg-surface-2/40 p-2">
                <TextInput
                  className="w-16"
                  inputMode="numeric"
                  value={titles[file.path]?.track ?? ""}
                  onChange={(event) =>
                    setTitles((current) => ({
                      ...current,
                      [file.path]: { ...current[file.path], track: event.target.value },
                    }))
                  }
                />
                <TextInput
                  className="flex-1"
                  value={titles[file.path]?.title ?? ""}
                  onChange={(event) =>
                    setTitles((current) => ({
                      ...current,
                      [file.path]: { ...current[file.path], title: event.target.value },
                    }))
                  }
                />
                <span className="hidden w-32 shrink-0 truncate text-[10px] text-muted sm:block" title={file.path}>
                  {file.name}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Modal>
  );
}
