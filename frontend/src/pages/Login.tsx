import { useQuery } from "@tanstack/react-query";
import { Disc3, LockKeyhole, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { apiClient } from "../lib/api";
import { Button, Card, TextInput } from "../components/ui";

export function Login() {
  const { status, login, setup } = useAuth();
  const info = useQuery({ queryKey: ["systemInfo"], queryFn: apiClient.info, retry: false });
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isSetup = status?.setup_required ?? false;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (isSetup && password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    if (isSetup && password.length < 8) {
      setError("Use at least 8 characters");
      return;
    }
    setBusy(true);
    try {
      if (isSetup) {
        await setup(password);
      } else {
        await login(password);
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="surface-gradient relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10">
      <div className="pointer-events-none absolute inset-0 opacity-[0.035] dark:opacity-[0.06]">
        <div className="absolute -left-20 top-10 h-80 w-80 rounded-full bg-accent blur-3xl" />
        <div className="absolute -right-10 bottom-0 h-80 w-80 rounded-full bg-cyan-400 blur-3xl" />
      </div>

      <div className="relative w-full max-w-md">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-accent text-white shadow-[0_20px_50px_-20px_var(--accent)]">
            <Disc3 className="h-7 w-7" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-fg">Beetser</h1>
          <p className="mt-1 text-sm text-muted">
            {isSetup
              ? "Create an admin password to finish setting up"
              : "Sign in to your music importer"}
          </p>
        </div>

        <Card className="p-6">
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-fg">Admin password</label>
              <div className="relative">
                <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
                <TextInput
                  type="password"
                  autoFocus
                  autoComplete={isSetup ? "new-password" : "current-password"}
                  className="pl-9"
                  placeholder="••••••••"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </div>
            </div>

            {isSetup && (
              <div>
                <label className="mb-1.5 block text-xs font-medium text-fg">Confirm password</label>
                <div className="relative">
                  <ShieldCheck className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
                  <TextInput
                    type="password"
                    autoComplete="new-password"
                    className="pl-9"
                    placeholder="••••••••"
                    value={confirm}
                    onChange={(event) => setConfirm(event.target.value)}
                  />
                </div>
              </div>
            )}

            {error && (
              <p className="rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger">{error}</p>
            )}

            <Button type="submit" className="w-full" size="lg" loading={busy}>
              {isSetup ? "Set password & continue" : "Sign in"}
            </Button>
          </form>

          {isSetup && (
            <p className="mt-4 text-center text-[11px] leading-relaxed text-muted">
              Tip: you can also set <code className="rounded bg-surface-2 px-1 py-0.5 font-mono">BEETSER_PASSWORD</code>{" "}
              in the container environment and skip this step.
            </p>
          )}
        </Card>

        <p className="mt-6 text-center text-[11px] text-muted">
          {info.data
            ? `beets ${info.data.beets_version} · library at ${info.data.library_path}`
            : "self-hosted · private by default"}
        </p>
      </div>
    </div>
  );
}
