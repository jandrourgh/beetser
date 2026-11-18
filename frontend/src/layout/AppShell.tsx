import { useQuery } from "@tanstack/react-query";
import {
  Activity as ActivityIcon,
  Disc3,
  FolderInput,
  LayoutDashboard,
  Library,
  ListChecks,
  LogOut,
  Menu,
  Moon,
  Settings as SettingsIcon,
  Sun,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useTheme } from "../hooks/useTheme";
import { apiClient } from "../lib/api";
import { cn } from "../lib/utils";
import { Badge, Button } from "../components/ui";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/review", label: "Review", icon: ListChecks, badge: true },
  { to: "/library", label: "Library", icon: Library },
  { to: "/origins", label: "Origins", icon: FolderInput },
  { to: "/activity", label: "Activity", icon: ActivityIcon },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { theme, toggle } = useTheme();
  const { logout } = useAuth();
  const location = useLocation();

  const stats = useQuery({ queryKey: ["jobStats"], queryFn: apiClient.jobStats });
  const info = useQuery({ queryKey: ["systemInfo"], queryFn: apiClient.info, staleTime: 60_000 });

  const reviewCount = stats.data?.review ?? 0;

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-5 py-6">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-white shadow-[0_10px_30px_-12px_var(--accent)]">
          <Disc3 className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm font-semibold tracking-tight text-fg">Beetser</p>
          <p className="text-[11px] text-muted">music importer</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active =
            item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => setMobileOpen(false)}
              className={cn(
                "group flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-surface-2 text-fg"
                  : "text-muted hover:bg-surface-2/70 hover:text-fg",
              )}
            >
              <Icon className={cn("h-4 w-4", active ? "text-accent" : "text-muted group-hover:text-fg")} />
              <span className="flex-1">{item.label}</span>
              {item.badge && reviewCount > 0 && (
                <Badge tone="accent" className="px-1.5">
                  {reviewCount}
                </Badge>
              )}
            </NavLink>
          );
        })}
      </nav>

      <div className="space-y-3 border-t border-line px-4 py-4">
        <div className="rounded-xl bg-surface-2/60 px-3 py-2.5">
          <p className="text-[11px] font-medium uppercase tracking-wide text-muted">Library</p>
          <p className="mt-1 truncate font-mono text-[11px] text-fg" title={info.data?.library_path}>
            {info.data?.library_path ?? "…"}
          </p>
          <p className="mt-1 text-[11px] text-muted">
            beets {info.data?.beets_version ?? "…"} · v{info.data?.beetser_version ?? "…"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={toggle} icon={theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}>
            {theme === "dark" ? "Light" : "Dark"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            onClick={() => void logout()}
            icon={<LogOut className="h-4 w-4" />}
          >
            Sign out
          </Button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen bg-bg">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-line bg-surface/50 lg:block">
        {sidebar}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 h-full w-72 border-r border-line bg-surface">
            <div className="absolute right-3 top-4">
              <Button variant="ghost" size="icon" onClick={() => setMobileOpen(false)} aria-label="Close menu">
                <X className="h-4 w-4" />
              </Button>
            </div>
            {sidebar}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-bg/80 px-4 py-3 backdrop-blur lg:hidden">
          <Button variant="ghost" size="icon" onClick={() => setMobileOpen(true)} aria-label="Open menu">
            <Menu className="h-5 w-5" />
          </Button>
          <span className="text-sm font-semibold">Beetser</span>
          {reviewCount > 0 && <Badge tone="accent">{reviewCount} to review</Badge>}
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
      </div>
    </div>
  );
}
