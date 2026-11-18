import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Copy,
  Disc3,
  FolderOpen,
  Library as LibraryIcon,
  Music2,
  Pencil,
  Search,
  User,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  Badge,
  Button,
  Card,
  Cover,
  EmptyState,
  PageHeader,
  Segmented,
  Skeleton,
  Tag,
  TextInput,
} from "../components/ui";
import { AlbumEditModal } from "../components/AlbumEditModal";
import { apiClient } from "../lib/api";
import { formatDate, formatDuration } from "../lib/utils";

type Tab = "albums" | "singles";

export function LibraryPage() {
  const { albumId } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("albums");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(search.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const stats = useQuery({ queryKey: ["libraryStats"], queryFn: apiClient.libraryStats });

  if (albumId) {
    return <AlbumDetailPage albumId={Number(albumId)} onBack={() => navigate("/library")} />;
  }

  return (
    <div className="animate-in">
      <PageHeader
        title="Library"
        description="The central beets database, shared by every origin."
        actions={
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
            <Badge tone="accent">
              <Disc3 className="h-3 w-3" /> {stats.data?.albums ?? 0} albums
            </Badge>
            <Badge>
              <Music2 className="h-3 w-3" /> {stats.data?.tracks ?? 0} tracks
            </Badge>
            <Badge>
              <User className="h-3 w-3" /> {stats.data?.artists ?? 0} artists
            </Badge>
          </div>
        }
      />

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Segmented
          value={tab}
          onChange={(value) => {
            setTab(value);
            setPage(1);
          }}
          options={[
            { value: "albums", label: "Albums" },
            { value: "singles", label: "Singles" },
          ]}
        />
        <div className="relative w-full sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <TextInput
            className="pl-9"
            placeholder={tab === "albums" ? "Search albums, artists, years…" : "Search singles…"}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
      </div>

      {tab === "albums" ? (
        <AlbumGrid query={query} page={page} onPage={setPage} />
      ) : (
        <SinglesTable query={query} page={page} onPage={setPage} />
      )}
    </div>
  );
}

function AlbumGrid({ query, page, onPage }: { query: string; page: number; onPage: (page: number) => void }) {
  const albums = useQuery({
    queryKey: ["albums", query, page],
    queryFn: () => apiClient.albums({ q: query, page, per_page: 30 }),
  });

  if (albums.isLoading) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {Array.from({ length: 10 }).map((_, index) => (
          <div key={index}>
            <Skeleton className="aspect-square w-full" />
            <Skeleton className="mt-2 h-3 w-3/4" />
            <Skeleton className="mt-1.5 h-2.5 w-1/2" />
          </div>
        ))}
      </div>
    );
  }

  if ((albums.data?.albums.length ?? 0) === 0) {
    return (
      <Card>
        <EmptyState
          icon={<LibraryIcon className="h-5 w-5" />}
          title={query ? "No albums match your search" : "Your library is empty"}
          description={
            query
              ? "Try a different artist, album or year."
              : "Add an origin folder and let Beetser import something."
          }
        />
      </Card>
    );
  }

  const total = albums.data?.total ?? 0;
  const perPage = albums.data?.per_page ?? 30;
  const pages = Math.max(1, Math.ceil(total / perPage));

  return (
    <>
      <div className="grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {albums.data?.albums.map((album) => (
          <Link key={album.id} to={`/library/${album.id}`} className="group">
            <Cover
              src={album.artpath ? apiClient.coverUrl(album.id, album.art_mtime) : null}
              alt={album.album}
              className="aspect-square w-full shadow-sm transition group-hover:-translate-y-0.5 group-hover:shadow-lg"
              rounded="rounded-xl"
            />
            <p className="mt-2 truncate text-sm font-medium text-fg">{album.album}</p>
            <p className="truncate text-xs text-muted">
              {album.albumartist}
              {album.year ? ` · ${album.year}` : ""}
            </p>
            <p className="text-[11px] text-muted">{album.track_count} tracks</p>
          </Link>
        ))}
      </div>
      <Pager page={page} pages={pages} total={total} onPage={onPage} />
    </>
  );
}

function SinglesTable({ query, page, onPage }: { query: string; page: number; onPage: (page: number) => void }) {
  const singles = useQuery({
    queryKey: ["singles", query, page],
    queryFn: () => apiClient.singles({ q: query, page, per_page: 50 }),
  });

  if (singles.isLoading) {
    return <Skeleton className="h-64 w-full" />;
  }

  if ((singles.data?.tracks.length ?? 0) === 0) {
    return (
      <Card>
        <EmptyState
          icon={<Music2 className="h-5 w-5" />}
          title="No singles"
          description="Tracks imported outside an album folder will appear here."
        />
      </Card>
    );
  }

  const total = singles.data?.total ?? 0;
  const perPage = singles.data?.per_page ?? 50;
  const pages = Math.max(1, Math.ceil(total / perPage));

  return (
    <>
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-line bg-surface-2/50 text-[11px] uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2.5 font-medium">Title</th>
                <th className="px-4 py-2.5 font-medium">Artist</th>
                <th className="px-4 py-2.5 font-medium">Album</th>
                <th className="px-4 py-2.5 font-medium">Format</th>
                <th className="px-4 py-2.5 text-right font-medium">Length</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {singles.data?.tracks.map((track) => (
                <tr key={track.id} className="hover:bg-surface-2/40">
                  <td className="max-w-[280px] px-4 py-2.5">
                    <p className="truncate font-medium text-fg">{track.title}</p>
                    <p className="truncate font-mono text-[10px] text-muted" title={track.path}>
                      {track.path}
                    </p>
                  </td>
                  <td className="px-4 py-2.5 text-muted">{track.artist || "—"}</td>
                  <td className="px-4 py-2.5 text-muted">{track.album || "—"}</td>
                  <td className="px-4 py-2.5">
                    <Tag>{track.format || "audio"}</Tag>
                  </td>
                  <td className="px-4 py-2.5 text-right text-muted">{formatDuration(track.length)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Pager page={page} pages={pages} total={total} onPage={onPage} />
    </>
  );
}

function Pager({
  page,
  pages,
  total,
  onPage,
}: {
  page: number;
  pages: number;
  total: number;
  onPage: (page: number) => void;
}) {
  if (total === 0) return null;
  return (
    <div className="mt-6 flex items-center justify-between text-xs text-muted">
      <span>
        Page {page} of {pages} · {total} total
      </span>
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

function AlbumDetailPage({ albumId, onBack }: { albumId: number; onBack: () => void }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const album = useQuery({ queryKey: ["album", albumId], queryFn: () => apiClient.album(albumId) });

  const copy = (value: string) => {
    void navigator.clipboard.writeText(value).then(
      () => toast.success("Path copied"),
      () => toast.error("Could not copy"),
    );
  };

  if (album.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-56 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!album.data) {
    return (
      <Card>
        <EmptyState
          title="Album not found"
          description="It may have been removed from the library."
          action={
            <Button variant="secondary" onClick={onBack}>
              Back to library
            </Button>
          }
        />
      </Card>
    );
  }

  const data = album.data;
  const totalLength = data.tracks.reduce((sum, track) => sum + (track.length || 0), 0);

  return (
    <div className="animate-in">
      <div className="mb-4 flex items-center justify-between gap-3">
        <Button variant="ghost" size="sm" onClick={onBack} icon={<ArrowLeft className="h-4 w-4" />}>
          Back to library
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => setEditing(true)}
          icon={<Pencil className="h-4 w-4" />}
        >
          Edit album
        </Button>
      </div>

      <Card className="overflow-hidden">
        <div className="surface-gradient flex flex-col gap-6 p-6 sm:flex-row">
          <Cover
            src={data.artpath ? apiClient.coverUrl(data.id, data.art_mtime) : null}
            alt={data.album}
            className="h-48 w-48 shrink-0 shadow-xl"
            rounded="rounded-2xl"
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              {data.albumtype && <Badge tone="accent">{data.albumtype}</Badge>}
              {data.year && <Badge>{data.year}</Badge>}
              {data.country && <Badge>{data.country}</Badge>}
              {data.genres && <Tag>{data.genres.replace(/;/g, " · ")}</Tag>}
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight text-fg">{data.album}</h1>
            <p className="mt-1 text-sm text-muted">{data.albumartist}</p>

            <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-muted">
              <span>
                {data.tracks.length} tracks · {formatDuration(totalLength)}
              </span>
              {data.label && <span>{data.label}</span>}
              {data.catalognum && <span className="font-mono">{data.catalognum}</span>}
              <span>added {formatDate(data.added)}</span>
              {data.mb_albumid && (
                <a
                  href={`https://musicbrainz.org/release/${data.mb_albumid}`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent hover:underline"
                >
                  MusicBrainz
                </a>
              )}
            </div>

            {data.path && (
              <button
                type="button"
                onClick={() => copy(data.path!)}
                className="mt-4 flex max-w-full items-center gap-2 rounded-lg bg-surface-2/60 px-2.5 py-1.5 text-left font-mono text-[10px] text-muted transition hover:text-fg"
                title="Copy folder path"
              >
                <FolderOpen className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{data.path}</span>
                <Copy className="ml-auto h-3 w-3 shrink-0" />
              </button>
            )}
          </div>
        </div>
      </Card>

      <Card className="mt-4 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-line bg-surface-2/50 text-[11px] uppercase tracking-wide text-muted">
              <tr>
                <th className="w-12 px-4 py-2.5 font-medium">#</th>
                <th className="px-4 py-2.5 font-medium">Title</th>
                <th className="px-4 py-2.5 font-medium">Artist</th>
                <th className="px-4 py-2.5 font-medium">Format</th>
                <th className="px-4 py-2.5 text-right font-medium">Length</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.tracks.map((track) => (
                <tr key={track.id} className="hover:bg-surface-2/40">
                  <td className="px-4 py-2.5 text-right font-mono text-[11px] text-muted">
                    {track.disc > 1 ? `${track.disc}.` : ""}
                    {track.track}
                  </td>
                  <td className="max-w-[320px] px-4 py-2.5">
                    <p className="truncate font-medium text-fg">{track.title}</p>
                    <p className="truncate font-mono text-[10px] text-muted" title={track.path}>
                      {track.path.split("/").slice(-2).join("/")}
                    </p>
                  </td>
                  <td className="px-4 py-2.5 text-muted">{track.artist}</td>
                  <td className="px-4 py-2.5">
                    <Tag>{track.format || "audio"}</Tag>
                  </td>
                  <td className="px-4 py-2.5 text-right text-muted">{formatDuration(track.length)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <AlbumEditModal
        album={data}
        open={editing}
        onClose={() => setEditing(false)}
        onAlbumChanged={(updated) => {
          queryClient.setQueryData(["album", albumId], updated);
          void queryClient.invalidateQueries({ queryKey: ["albums"] });
          void queryClient.invalidateQueries({ queryKey: ["libraryStats"] });
        }}
      />
    </div>
  );
}
