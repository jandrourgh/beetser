import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Database, FolderCog, RotateCcw, Save, ScanLine, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Badge,
  Button,
  Card,
  Field,
  KeyValue,
  PageHeader,
  Select,
  Switch,
  TextInput,
} from "../components/ui";
import { apiClient } from "../lib/api";
import type { AppSettings } from "../lib/types";
import { formatBytes } from "../lib/utils";

function Section({
  title,
  description,
  icon,
  children,
}: {
  title: string;
  description: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-surface-2 text-accent">
          {icon}
        </div>
        <div>
          <h2 className="text-sm font-semibold text-fg">{title}</h2>
          <p className="mt-0.5 text-xs text-muted">{description}</p>
        </div>
      </div>
      <div className="space-y-3">{children}</div>
    </Card>
  );
}

export function SettingsPage() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: apiClient.settings });
  const info = useQuery({ queryKey: ["systemInfo"], queryFn: apiClient.info, staleTime: 60_000 });
  const [draft, setDraft] = useState<AppSettings | null>(null);

  useEffect(() => {
    if (settings.data && !draft) setDraft(settings.data);
  }, [settings.data, draft]);

  const save = useMutation({
    mutationFn: (values: AppSettings) => apiClient.updateSettings(values),
    onSuccess: (data) => {
      setDraft(data);
      toast.success("Settings saved");
      void queryClient.invalidateQueries();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not save"),
  });

  const reset = useMutation({
    mutationFn: apiClient.resetSettings,
    onSuccess: (data) => {
      setDraft(data);
      toast.success("Settings reset to defaults");
      void queryClient.invalidateQueries();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not reset"),
  });

  if (!draft) {
    return (
      <div className="animate-in space-y-4">
        <PageHeader title="Settings" description="Global defaults for every origin." />
        <Card className="h-64 shimmer" />
      </div>
    );
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(settings.data);
  const set = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) =>
    setDraft((current) => (current ? { ...current, [key]: value } : current));

  return (
    <div className="animate-in">
      <PageHeader
        title="Settings"
        description="Global defaults. Any origin can override the import mode, path formats and auto-tag threshold."
        actions={
          <>
            <Button
              variant="ghost"
              icon={<RotateCcw className="h-4 w-4" />}
              onClick={() => {
                if (window.confirm("Reset all settings to their defaults?")) reset.mutate();
              }}
              loading={reset.isPending}
            >
              Reset
            </Button>
            <Button
              icon={<Save className="h-4 w-4" />}
              disabled={!dirty}
              loading={save.isPending}
              onClick={() => draft && save.mutate(draft)}
            >
              Save changes
            </Button>
          </>
        }
      />

      <div className="grid gap-4 xl:grid-cols-2">
        <Section
          title="Importing"
          description="How files are imported. Tag only writes metadata in place; organising folders is a separate step."
          icon={<FolderCog className="h-4 w-4" />}
        >
          <Field label="Default import mode" hint="origins can override this">
            <Select
              value={draft.import_mode}
              onChange={(event) => set("import_mode", event.target.value as AppSettings["import_mode"])}
            >
              <option value="tag">Tag only — write tags, keep files where they are</option>
              <option value="move">Move files into artist/album folders</option>
              <option value="copy">Copy files, keep the originals</option>
            </Select>
          </Field>
          <Field label="Album path format" hint="beets template">
            <TextInput
              className="font-mono text-xs"
              value={draft.path_format}
              onChange={(event) => set("path_format", event.target.value)}
            />
          </Field>
          <Field label="Compilation path format" hint="for Various Artists albums">
            <TextInput
              className="font-mono text-xs"
              value={draft.comp_path_format}
              onChange={(event) => set("comp_path_format", event.target.value)}
            />
          </Field>
          <Field label="Singleton path format">
            <TextInput
              className="font-mono text-xs"
              value={draft.singleton_path_format}
              onChange={(event) => set("singleton_path_format", event.target.value)}
            />
          </Field>
          <div className="rounded-xl border border-line bg-surface-2/30 px-3">
            <Switch
              label="Write tags to files"
              description="Store the matched metadata inside the audio files."
              checked={draft.write_tags}
              onChange={(value) => set("write_tags", value)}
            />
            <Switch
              label="Remove empty folders"
              description="After a move, prune the empty folders left behind in the origin."
              checked={draft.delete_empty_dirs}
              onChange={(value) => set("delete_empty_dirs", value)}
            />
          </div>
        </Section>

        <Section
          title="Tagging"
          description="When Beetser may import without asking."
          icon={<Sparkles className="h-4 w-4" />}
        >
          <div className="rounded-xl border border-line bg-surface-2/30 px-3">
            <Switch
              label="Automatic tagging"
              description="Look up MusicBrainz and apply confident matches automatically."
              checked={draft.auto_tag_enabled}
              onChange={(value) => set("auto_tag_enabled", value)}
            />
          </div>
          <div>
            <div className="mb-1.5 flex items-center justify-between text-xs">
              <span className="font-medium text-fg">Confidence threshold</span>
              <span className="font-mono text-accent">{Math.round(draft.auto_tag_threshold * 100)}%</span>
            </div>
            <input
              type="range"
              min={0.5}
              max={1}
              step={0.01}
              value={draft.auto_tag_threshold}
              onChange={(event) => set("auto_tag_threshold", Number(event.target.value))}
              className="w-full accent-[var(--accent)]"
            />
            <p className="mt-1 text-[11px] text-muted">
              Lower values import more automatically. 85–95% is a good balance.
            </p>
          </div>
          <Field label="Ambiguity gap" hint="difference to the runner-up">
            <TextInput
              inputMode="decimal"
              value={String(draft.auto_tag_min_gap)}
              onChange={(event) => set("auto_tag_min_gap", Number(event.target.value) || 0)}
            />
          </Field>
          <div className="rounded-xl border border-line bg-surface-2/30 px-3">
            <Switch
              label="Fetch album art online"
              description="Download missing covers from Cover Art Archive / iTunes. Local cover files are always used."
              checked={draft.fetch_art}
              onChange={(value) => set("fetch_art", value)}
            />
            <Switch
              label="Embed album art"
              description="Write the cover into each file's tags (slower)."
              checked={draft.embed_art}
              onChange={(value) => set("embed_art", value)}
            />
          </div>
        </Section>

        <Section
          title="Scanning"
          description="How quickly new downloads are noticed."
          icon={<ScanLine className="h-4 w-4" />}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Settle time" hint="seconds">
              <TextInput
                inputMode="numeric"
                value={String(draft.settle_seconds)}
                onChange={(event) => set("settle_seconds", Number(event.target.value) || 0)}
              />
            </Field>
            <Field label="Full scan interval" hint="seconds">
              <TextInput
                inputMode="numeric"
                value={String(draft.scan_interval_seconds)}
                onChange={(event) => set("scan_interval_seconds", Number(event.target.value) || 60)}
              />
            </Field>
          </div>
          <p className="text-[11px] text-muted">
            Watchers react instantly; the interval is a safety net for network shares where inotify is unreliable.
          </p>
          <div className="rounded-xl border border-line bg-surface-2/30 px-3">
            <Switch
              label="Import loose files as singles"
              description="Files dropped directly in an origin root are treated as individual tracks."
              checked={draft.include_singletons}
              onChange={(value) => set("include_singletons", value)}
            />
          </div>
          <Field label="Ignored folder names" hint="comma separated">
            <TextInput
              className="font-mono text-xs"
              value={draft.ignore_dirs.join(", ")}
              onChange={(event) =>
                set(
                  "ignore_dirs",
                  event.target.value
                    .split(",")
                    .map((value) => value.trim())
                    .filter(Boolean),
                )
              }
            />
          </Field>
          <Field label="Ignored file patterns" hint="glob, comma separated">
            <TextInput
              className="font-mono text-xs"
              value={draft.ignore_globs.join(", ")}
              onChange={(event) =>
                set(
                  "ignore_globs",
                  event.target.value
                    .split(",")
                    .map((value) => value.trim())
                    .filter(Boolean),
                )
              }
            />
          </Field>
        </Section>

        <Section
          title="Notifications"
          description="Get pinged when something needs a decision."
          icon={<Bell className="h-4 w-4" />}
        >
          <Field label="Webhook URL" hint="Discord, ntfy, Slack or generic JSON">
            <TextInput
              className="font-mono text-xs"
              placeholder="https://ntfy.sh/my-beetser"
              value={draft.notify_webhook_url}
              onChange={(event) => set("notify_webhook_url", event.target.value)}
            />
          </Field>
          <div className="rounded-xl border border-line bg-surface-2/30 px-3">
            <Switch
              label="Notify when review is needed"
              description="Duplicates and uncertain matches."
              checked={draft.notify_on_review}
              onChange={(value) => set("notify_on_review", value)}
            />
            <Switch
              label="Notify after automatic imports"
              description="Only for imports that needed no human decision."
              checked={draft.notify_on_import}
              onChange={(value) => set("notify_on_import", value)}
            />
            <Switch
              label="Notify on errors"
              checked={draft.notify_on_error}
              onChange={(value) => set("notify_on_error", value)}
            />
          </div>
          <p className="text-[11px] text-muted">
            The webhook receives a JSON body with <code className="font-mono">title</code>,{" "}
            <code className="font-mono">message</code>, <code className="font-mono">text</code> and{" "}
            <code className="font-mono">content</code> fields.
          </p>
        </Section>

        <PasswordCard />

        <Card className="p-5 xl:col-span-2">
          <div className="mb-4 flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-surface-2 text-accent">
              <Database className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-fg">About</h2>
              <p className="mt-0.5 text-xs text-muted">Runtime and storage details.</p>
            </div>
            <Badge tone="accent" className="ml-auto">
              v{info.data?.beetser_version}
            </Badge>
          </div>
          <div className="grid gap-x-8 gap-y-1 sm:grid-cols-2">
            <KeyValue label="beets" value={info.data?.beets_version ?? "–"} />
            <KeyValue label="Python" value={info.data?.python_version ?? "–"} />
            <KeyValue
              label="Library database"
              value={<span className="font-mono text-[10px]">{info.data?.library_path ?? "–"}</span>}
            />
            <KeyValue
              label="Config directory"
              value={<span className="font-mono text-[10px]">{info.data?.data_dir ?? "–"}</span>}
            />
            <KeyValue
              label="Disk free"
              value={info.data ? `${formatBytes(info.data.disk.free)} of ${formatBytes(info.data.disk.total)}` : "–"}
            />
            <KeyValue label="Library ready" value={info.data?.library_exists ? "yes" : "no"} />
          </div>
        </Card>
      </div>
    </div>
  );
}

function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");

  const mutation = useMutation({
    mutationFn: () => apiClient.changePassword(current, next),
    onSuccess: () => {
      toast.success("Password updated");
      setCurrent("");
      setNext("");
      setConfirm("");
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not update password"),
  });

  const valid = next.length >= 8 && next === confirm && current.length > 0;

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-surface-2 text-accent">
          <ShieldCheck className="h-4 w-4" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-fg">Security</h2>
          <p className="mt-0.5 text-xs text-muted">Change the admin password used to sign in.</p>
        </div>
      </div>
      <div className="space-y-3">
        <Field label="Current password">
          <TextInput type="password" autoComplete="current-password" value={current} onChange={(event) => setCurrent(event.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="New password" hint="min 8 characters">
            <TextInput type="password" autoComplete="new-password" value={next} onChange={(event) => setNext(event.target.value)} />
          </Field>
          <Field label="Confirm new password">
            <TextInput type="password" autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} />
          </Field>
        </div>
        <Button
          variant="secondary"
          disabled={!valid}
          loading={mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          Update password
        </Button>
      </div>
    </Card>
  );
}
