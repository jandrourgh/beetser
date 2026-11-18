import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowUp,
  ChevronRight,
  Folder,
  FolderInput,
  FolderOpen,
  HardDrive,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  Watch,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Modal,
  PageHeader,
  Select,
  Skeleton,
  Switch,
  Tag,
  TextInput,
  Textarea,
} from "../components/ui";
import { apiClient } from "../lib/api";
import type { Origin, OriginInput } from "../lib/types";
import { cn, formatRelative } from "../lib/utils";

interface FormState {
  name: string;
  path: string;
  destination: string;
  sameDestination: boolean;
  import_mode: "inherit" | "move" | "copy";
  auto_tag: "inherit" | "enabled" | "disabled";
  auto_tag_threshold: string;
  settled_seconds: string;
  path_format: string;
  singleton_path_format: string;
  watch: boolean;
  enabled: boolean;
  include_singletons: boolean;
  notes: string;
}

function emptyForm(): FormState {
  return {
    name: "",
    path: "",
    destination: "",
    sameDestination: true,
    import_mode: "inherit",
    auto_tag: "inherit",
    auto_tag_threshold: "",
    settled_seconds: "",
    path_format: "",
    singleton_path_format: "",
    watch: true,
    enabled: true,
    include_singletons: true,
    notes: "",
  };
}

function formFromOrigin(origin: Origin): FormState {
  return {
    name: origin.name,
    path: origin.path,
    destination: origin.destination,
    sameDestination: origin.destination_is_default,
    import_mode: origin.import_mode,
    auto_tag: origin.auto_tag,
    auto_tag_threshold: origin.auto_tag_threshold !== null ? String(origin.auto_tag_threshold) : "",
    settled_seconds: origin.settled_seconds !== null ? String(origin.settled_seconds) : "",
    path_format: origin.path_format ?? "",
    singleton_path_format: origin.singleton_path_format ?? "",
    watch: origin.watch,
    enabled: origin.enabled,
    include_singletons: origin.include_singletons,
    notes: origin.notes ?? "",
  };
}

export function OriginsPage() {
  const queryClient = useQueryClient();
  const origins = useQuery({ queryKey: ["origins"], queryFn: apiClient.origins });
  const [editing, setEditing] = useState<Origin | "new" | null>(null);
  const [deleting, setDeleting] = useState<Origin | null>(null);

  const scan = useMutation({
    mutationFn: (id: string) => apiClient.scanOrigin(id),
    onSuccess: () => {
      toast.success("Scan queued");
      void queryClient.invalidateQueries();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Scan failed"),
  });

  const test = useMutation({
    mutationFn: (origin: Origin) => apiClient.testOrigin(origin.id),
    onSuccess: (result) => {
      if (result.error) toast.error(result.error);
      else
        toast.success(
          `${result.audio_files} audio files found · destination ${result.destination_writable ? "writable" : "not writable"}`,
        );
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Test failed"),
  });

  const remove = useMutation({
    mutationFn: (id: string) => apiClient.deleteOrigin(id),
    onSuccess: () => {
      toast.success("Origin removed");
      setDeleting(null);
      void queryClient.invalidateQueries();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not delete"),
  });

  return (
    <div className="animate-in">
      <PageHeader
        title="Origins"
        description="Folders watched for incoming music. Each origin keeps its own destination and import policy."
        actions={
          <Button onClick={() => setEditing("new")} icon={<Plus className="h-4 w-4" />}>
            Add origin
          </Button>
        }
      />

      <div className="grid gap-3 lg:grid-cols-2">
        {origins.isLoading && (
          <>
            <Skeleton className="h-44 w-full" />
            <Skeleton className="h-44 w-full" />
          </>
        )}

        {origins.data?.origins.map((origin) => (
          <Card key={origin.id} className="flex flex-col p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
                  <FolderInput className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-fg">{origin.name}</p>
                  <p className="truncate font-mono text-[11px] text-muted" title={origin.path}>
                    {origin.path}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {!origin.enabled && <Badge>disabled</Badge>}
                {origin.enabled && !origin.watch && <Badge tone="warning">poll only</Badge>}
                {origin.path_exists === false && (
                  <Badge tone="danger">
                    <AlertCircle className="h-3 w-3" /> missing
                  </Badge>
                )}
              </div>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3 text-[11px]">
              <div>
                <p className="text-muted">Destination</p>
                <p className="mt-0.5 truncate font-mono text-fg" title={origin.destination}>
                  {origin.destination_is_default ? "same as origin" : origin.destination}
                </p>
              </div>
              <div>
                <p className="text-muted">Import mode</p>
                <p className="mt-0.5 flex items-center gap-1.5 text-fg">
                  <Tag>{origin.effective_import_mode}</Tag>
                  {origin.import_mode === "inherit" && <span className="text-muted">(global)</span>}
                </p>
              </div>
              <div>
                <p className="text-muted">Auto-tag</p>
                <p className="mt-0.5 flex items-center gap-1.5 text-fg">
                  <Tag>
                    {origin.auto_tag === "inherit" ? "global" : origin.auto_tag}
                  </Tag>
                  <span className="text-muted">{Math.round(origin.effective_auto_tag_threshold * 100)}% min</span>
                </p>
              </div>
              <div>
                <p className="text-muted">Last scan</p>
                <p className="mt-0.5 flex items-center gap-1.5 text-fg">
                  <Watch className="h-3 w-3 text-muted" />
                  {formatRelative(origin.last_scan_at)}
                  {origin.last_scan_status && origin.last_scan_status !== "ok" && (
                    <span className="text-danger">({origin.last_scan_status})</span>
                  )}
                </p>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-1.5">
              {(["needs_review", "duplicate", "failed", "imported"] as const).map((state) => {
                const count = origin.job_counts[state];
                if (!count) return null;
                return (
                  <Badge
                    key={state}
                    tone={
                      state === "needs_review"
                        ? "accent"
                        : state === "duplicate"
                          ? "warning"
                          : state === "failed"
                            ? "danger"
                            : "success"
                    }
                  >
                    {count} {state.replace("_", " ")}
                  </Badge>
                );
              })}
            </div>

            {origin.last_error && (
              <p className="mt-3 rounded-lg bg-danger-soft px-2.5 py-1.5 text-[11px] text-danger">
                {origin.last_error}
              </p>
            )}

            <div className="mt-4 flex flex-wrap items-center gap-1.5 border-t border-line pt-3">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => scan.mutate(origin.id)}
                loading={scan.isPending && scan.variables === origin.id}
                icon={<RefreshCw className="h-3.5 w-3.5" />}
              >
                Scan now
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => test.mutate(origin)}
                loading={test.isPending && test.variables?.id === origin.id}
                icon={<HardDrive className="h-3.5 w-3.5" />}
              >
                Test
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEditing(origin)} icon={<Pencil className="h-3.5 w-3.5" />}>
                Edit
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="ml-auto text-danger hover:bg-danger-soft"
                onClick={() => setDeleting(origin)}
                icon={<Trash2 className="h-3.5 w-3.5" />}
              >
                Delete
              </Button>
            </div>
          </Card>
        ))}

        {!origins.isLoading && (origins.data?.origins.length ?? 0) === 0 && (
          <Card className="lg:col-span-2">
            <EmptyState
              icon={<FolderInput className="h-5 w-5" />}
              title="No origins configured"
              description="Origins are the folders that receive music (from a download client, a NAS share, Syncthing…). Beetser watches them, and each one keeps its own destination."
              action={
                <Button onClick={() => setEditing("new")} icon={<Plus className="h-4 w-4" />}>
                  Add your first origin
                </Button>
              }
            />
          </Card>
        )}
      </div>

      <OriginModal
        open={editing !== null}
        origin={editing === "new" ? null : editing}
        onClose={() => setEditing(null)}
      />

      <Modal
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        title="Delete origin?"
        description="The origin and its job history are removed. Files and the music library are untouched."
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              onClick={() => deleting && remove.mutate(deleting.id)}
            >
              Delete origin
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">
          {deleting?.name} <span className="font-mono text-[11px]">({deleting?.path})</span>
        </p>
      </Modal>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function OriginModal({
  open,
  origin,
  onClose,
}: {
  open: boolean;
  origin: Origin | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(emptyForm);
  const [advanced, setAdvanced] = useState(false);
  const [picker, setPicker] = useState<"path" | "destination" | null>(null);

  useEffect(() => {
    if (!open) return;
    setForm(origin ? formFromOrigin(origin) : emptyForm());
    setAdvanced(false);
  }, [open, origin?.id]);

  const save = useMutation({
    mutationFn: async () => {
      const payload: OriginInput = {
        name: form.name.trim(),
        path: form.path.trim(),
        destination: form.sameDestination ? null : form.destination.trim() || null,
        import_mode: form.import_mode,
        auto_tag: form.auto_tag,
        auto_tag_threshold: form.auto_tag_threshold ? Number(form.auto_tag_threshold) : null,
        settled_seconds: form.settled_seconds ? Number(form.settled_seconds) : null,
        path_format: form.path_format.trim() || null,
        singleton_path_format: form.singleton_path_format.trim() || null,
        watch: form.watch,
        enabled: form.enabled,
        include_singletons: form.include_singletons,
        notes: form.notes.trim() || null,
      };
      if (origin) return apiClient.updateOrigin(origin.id, payload);
      return apiClient.createOrigin(payload);
    },
    onSuccess: () => {
      toast.success(origin ? "Origin updated" : "Origin added — scanning now");
      void queryClient.invalidateQueries();
      onClose();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not save origin"),
  });

  const set = <K extends keyof FormState>(field: K, value: FormState[K]) =>
    setForm((current) => ({ ...current, [field]: value }));

  const valid = form.name.trim().length > 0 && form.path.trim().startsWith("/");

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={origin ? `Edit ${origin.name}` : "Add origin"}
        description="A folder to watch, plus where imported music should live."
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!valid}>
              {origin ? "Save changes" : "Add origin"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name">
              <TextInput
                value={form.name}
                placeholder="Downloads"
                onChange={(event) => set("name", event.target.value)}
              />
            </Field>
            <Field label="Watch mode" hint="inotify + periodic fallback">
              <div className="-mt-1 rounded-xl border border-line bg-surface-2/40 px-3">
                <Switch label="Watch for changes" checked={form.watch} onChange={(value) => set("watch", value)} />
              </div>
            </Field>
          </div>

          <Field label="Source path" hint="absolute path inside the container">
            <div className="flex gap-2">
              <TextInput
                className="flex-1 font-mono text-xs"
                value={form.path}
                placeholder="/media/downloads"
                onChange={(event) => {
                  const value = event.target.value;
                  set("path", value);
                  if (form.sameDestination) set("destination", value);
                  if (!form.name) set("name", value.split("/").filter(Boolean).pop() ?? "");
                }}
              />
              <Button variant="secondary" onClick={() => setPicker("path")} icon={<FolderOpen className="h-4 w-4" />}>
                Browse
              </Button>
            </div>
          </Field>

          <div className="rounded-xl border border-line bg-surface-2/30 p-3">
            <Switch
              label="Organize inside the origin folder"
              description="When enabled, music is sorted in place (by artist and album). Turn off to send it to a separate destination."
              checked={form.sameDestination}
              onChange={(value) => {
                set("sameDestination", value);
                if (value) set("destination", form.path);
              }}
            />
            {!form.sameDestination && (
              <div className="mt-2 flex gap-2">
                <TextInput
                  className="flex-1 font-mono text-xs"
                  value={form.destination}
                  placeholder="/media/music"
                  onChange={(event) => set("destination", event.target.value)}
                />
                <Button variant="secondary" onClick={() => setPicker("destination")} icon={<FolderOpen className="h-4 w-4" />}>
                  Browse
                </Button>
              </div>
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Import mode" hint="defaults to the global setting">
              <Select value={form.import_mode} onChange={(event) => set("import_mode", event.target.value as FormState["import_mode"])}>
                <option value="inherit">Use global default</option>
                <option value="move">Move files</option>
                <option value="copy">Copy files</option>
              </Select>
            </Field>
            <Field label="Auto-tag" hint="confident matches import without review">
              <Select value={form.auto_tag} onChange={(event) => set("auto_tag", event.target.value as FormState["auto_tag"])}>
                <option value="inherit">Use global default</option>
                <option value="enabled">Enabled</option>
                <option value="disabled">Always ask</option>
              </Select>
            </Field>
            <Field label="Confidence threshold" hint="0–1, empty = global">
              <TextInput
                inputMode="decimal"
                placeholder="0.85"
                value={form.auto_tag_threshold}
                onChange={(event) => set("auto_tag_threshold", event.target.value)}
              />
            </Field>
            <Field label="Settle time (seconds)" hint="wait for downloads to finish">
              <TextInput
                inputMode="numeric"
                placeholder="30"
                value={form.settled_seconds}
                onChange={(event) => set("settled_seconds", event.target.value)}
              />
            </Field>
          </div>

          <div className="rounded-xl border border-line bg-surface-2/30 px-3">
            <Switch
              label="Import loose files as singles"
              description="Files directly in the origin root are imported individually instead of as an album."
              checked={form.include_singletons}
              onChange={(value) => set("include_singletons", value)}
            />
            <Switch
              label="Enabled"
              description="Disabled origins are neither watched nor scanned."
              checked={form.enabled}
              onChange={(value) => set("enabled", value)}
            />
          </div>

          <button
            type="button"
            onClick={() => setAdvanced((value) => !value)}
            className="flex items-center gap-1.5 text-xs font-medium text-accent"
          >
            <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", advanced && "rotate-90")} />
            Advanced: custom path formats
          </button>

          {advanced && (
            <div className="grid gap-3">
              <Field label="Album path format" hint="beets template; empty = global">
                <TextInput
                  className="font-mono text-xs"
                  placeholder="$albumartist/$album%aunique{}/$track $title"
                  value={form.path_format}
                  onChange={(event) => set("path_format", event.target.value)}
                />
              </Field>
              <Field label="Singleton path format" hint="beets template; empty = global">
                <TextInput
                  className="font-mono text-xs"
                  placeholder="Singletons/$artist/$title"
                  value={form.singleton_path_format}
                  onChange={(event) => set("singleton_path_format", event.target.value)}
                />
              </Field>
            </div>
          )}

          <Field label="Notes" hint="optional">
            <Textarea
              value={form.notes}
              placeholder="Where these files come from, or anything to remember."
              onChange={(event) => set("notes", event.target.value)}
            />
          </Field>
        </div>
      </Modal>

      <PathPicker
        open={picker !== null}
        initial={picker === "destination" ? form.destination || form.path || "/" : form.path || "/"}
        onClose={() => setPicker(null)}
        onSelect={(value) => {
          if (picker === "destination") set("destination", value);
          else {
            set("path", value);
            if (form.sameDestination) set("destination", value);
            if (!form.name) set("name", value.split("/").filter(Boolean).pop() ?? "");
          }
          setPicker(null);
        }}
      />
    </>
  );
}

/* ------------------------------------------------------------------ */

function PathPicker({
  open,
  initial,
  onClose,
  onSelect,
}: {
  open: boolean;
  initial: string;
  onClose: () => void;
  onSelect: (path: string) => void;
}) {
  const [path, setPath] = useState(initial);
  const [manual, setManual] = useState(initial);

  useEffect(() => {
    if (!open) return;
    setPath(initial);
    setManual(initial);
  }, [open, initial]);

  const browse = useQuery({
    queryKey: ["browse", path],
    queryFn: () => apiClient.browse(path),
    enabled: open,
    retry: false,
  });

  const navigateTo = (next: string) => {
    setPath(next);
    setManual(next);
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Choose a folder"
      description="Browse the container filesystem."
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => onSelect(path)} icon={<Folder className="h-4 w-4" />}>
            Use this folder
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="icon"
            onClick={() => browse.data?.parent && navigateTo(browse.data.parent)}
            disabled={!browse.data?.parent}
            aria-label="Parent folder"
          >
            <ArrowUp className="h-4 w-4" />
          </Button>
          <TextInput
            className="flex-1 font-mono text-xs"
            value={manual}
            onChange={(event) => setManual(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") navigateTo(manual);
            }}
          />
          <Button variant="secondary" onClick={() => navigateTo(manual)}>
            Go
          </Button>
        </div>

        <div className="min-h-[260px] overflow-hidden rounded-xl border border-line">
          {browse.isLoading && <div className="p-4 text-xs text-muted">Loading…</div>}
          {browse.isError && (
            <div className="p-4 text-xs text-danger">
              {browse.error instanceof Error ? browse.error.message : "Cannot read folder"}
            </div>
          )}
          <div className="divide-y divide-line">
            {browse.data?.entries.map((entry) => (
              <button
                key={entry.path}
                type="button"
                disabled={entry.type !== "dir"}
                onClick={() => navigateTo(entry.path)}
                className={cn(
                  "flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs",
                  entry.type === "dir" ? "hover:bg-surface-2" : "cursor-default opacity-50",
                )}
              >
                {entry.type === "dir" ? (
                  <Folder className="h-4 w-4 shrink-0 text-accent" />
                ) : (
                  <Folder className="h-4 w-4 shrink-0 text-muted" />
                )}
                <span className="truncate text-fg">{entry.name}</span>
                {entry.type === "dir" && <ChevronRight className="ml-auto h-3.5 w-3.5 text-muted" />}
              </button>
            ))}
            {!browse.isLoading && (browse.data?.entries.length ?? 0) === 0 && (
              <div className="p-4 text-xs text-muted">This folder is empty.</div>
            )}
          </div>
        </div>
        <p className="text-[10px] text-muted">
          Showing directories only. Type a path and press Enter to jump anywhere.
        </p>
      </div>
    </Modal>
  );
}
