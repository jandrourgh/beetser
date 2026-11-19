# Architecture

Beetser is a single Python process that serves the web UI/API and runs a small
background worker. It owns a central **beets library** and a separate
**application database** with import jobs, origins and dedupe fingerprints.

```
                        ┌────────────────────────────────────────────┐
  browser ──HTTP/SSE──► │ FastAPI (uvicorn, 1 worker)                │
                        │  auth · origins · jobs · library · settings│
                        └───────────────┬────────────────────────────┘
                                        │ read-only queries
                        ┌───────────────▼────────────────────────────┐
                        │ BeetsEngine                                │
                        │  · per-origin config generation            │
                        │  · in-process MusicBrainz lookups          │
                        │  · library reads + stats                   │
                        │  · subprocess imports (`beetser.beets_cli`)│
                        └───────────────┬────────────────────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        ▼                               ▼                               ▼
  /config/library.db             /config/beetser.db              media folders
  (beets, central)               (jobs, origins, dedupe)         (origins + destinations)
```

## Process model

- **One uvicorn worker.** The beets Python API relies on global configuration
  and a single library database; horizontal scaling inside one container would
  only add contention. Scaling means running multiple containers against
  *different* libraries.
- **Async API, threaded blocking work.** FastAPI runs blocking endpoints in its
  thread pool. The background worker offloads scans, hashing, MusicBrainz
  lookups and imports with `asyncio.to_thread`, so the event loop is never
  blocked.
- **A single job queue** serializes all beets work. This keeps MusicBrainz
  requests polite, avoids two imports racing for the same library file and makes
  the state machine easy to reason about.
- **Watchdog threads** only emit debounced "scan origin X" requests; all actual
  work happens in the worker.

## Storage layout

```
/config/
  library.db              central beets library (albums + items + artwork paths)
  beetser.db              Beetser state (SQLite, WAL)
  secret.key              session cookie signing key (0600)
  beets/
    config.yaml           base config used for in-process lookups
    origins/<id>.yaml     generated per-origin import config
    state-<id>.pickle     beets incremental state (one per origin)
  music/                  placeholder music dir for beets path resolution
```

Beetser's own database contains:

| Table | Purpose |
| --- | --- |
| `origins` | Watched folders, destinations and per-origin policy |
| `jobs` | One import job per album folder or loose file |
| `tracked_files` | Every file seen in an origin, with hash and status |
| `imported_fingerprints` | SHA-256 of every imported file, for exact dedupe |
| `activity` | Human-readable event log |
| `app_settings` | Global settings as JSON values |

## Scanning

A scan walks an origin tree and produces **album groups**:

1. Directories starting with `.`, configured ignore dirs and directories that
   contain a `.beetser-ignore` marker are pruned entirely.
2. Audio files (by extension) are considered; files matching `ignore_globs` or
   with zero size are skipped.
3. Files younger than the origin's **settle time** (mtime/ctime) are skipped and
   the scan is rescheduled — this avoids importing partially downloaded albums.
4. Files whose absolute path is already in the library or in `tracked_files` are
   skipped.
5. Remaining files are hashed (SHA-256) and grouped by parent directory.
6. Files directly in the origin root become **singleton** jobs (if enabled);
   every other directory becomes an **album** job.
7. A pending job for the same folder is extended with the new files and
   re-analyzed instead of creating a duplicate job.

If the destination is a subdirectory of the origin, it is pruned from the walk;
imported files are also filtered by library path.

`tracked_files` is the dedupe/ID memory of the scanner: it prevents re-importing
skipped or failed files on every scan. Deleting a job ("Remove") clears its
tracked rows so the files can be rediscovered.

## Analysis

```
Item.from_path(file) ──► Source.from_items(items) ──► tag_album(source)
                                                        │
                                                        ▼
                                       Proposal(candidates, recommendation)
```

- `tag_item` is used for singleton jobs.
- Candidates are serialized for the UI with album/track metadata, MusicBrainz
  IDs, cover-art URL, missing/extra track counts and a **similarity score**
  (`1 − beets distance`, 0–1).
- The lookup is text/metadata based. Beetser does not require an AcoustID key;
  fingerprinting can be added later without changing the job model.

### Automatic vs. reviewed

A job is imported automatically only when **all** of these hold:

- auto-tagging is enabled globally and for the origin;
- the best candidate's similarity ≥ threshold (default `0.85`);
- the match has no missing or unmatched tracks;
- there is no competing candidate with a different artist/album within
  `auto_tag_min_gap` (default `0.03`);
- the candidate's release MBID is not already in the library;
- no duplicate report is blocking.

Otherwise the job becomes `needs_review` with all candidates available in the UI.

## Importing

Imports run in a subprocess:

```
python -m beetser.beets_cli -c /config/beets/origins/<id>.yaml import \
    -q -I (-C -M -w | -m | -c) (-s) (-S <release-id>) (-A) --set k=v ... -- <folder>
```

Why a subprocess?

- A crash or plugin error cannot take down the API.
- Beets global state and CLI prompts stay isolated.
- The exact same importer that users know from `beet import` is used, including
  path formats, artwork plugins and tag writing.

`fetchart` is always enabled with the `filesystem` source first, so a local
`cover`/`folder`/`front` image is adopted by as-is imports even without a
MusicBrainz match. Online sources are added only when `fetch_art` is on, and
`fetch_for_asis: false` keeps as-is imports from downloading art silently.

The generated config sets:

- `library` → the central database;
- `directory` → the origin's destination;
- `duplicate_action: keep` (Beetser performs its own, more precise dedupe);
- `quiet_fallback: skip` (never import garbage silently);
- a relaxed `match.max_rec`/threshold, because the user (or the auto rule)
  already chose a release explicitly via `--search-id`.

Each import carries `--set=beetser_origin=<id>` and `beetser_job=<id>` as beets
flexible attributes, so provenance stays attached to library items.

### Import modes

`tag` is the default and mirrors `beet import -CMw`: tags (and cover art) are
written into the files, which stay exactly where the download client left them.
`move` and `copy` are opt-in, globally or per origin, and send files to the
origin destination using the path formats.

### Absolute paths

beets 2.14 stores paths relative to the configured `directory` when the item
lives below it. With one central library and many destination roots that is
ambiguous. Beetser patches
`beets.dbcore.pathutils.normalize_path_for_db` in its own processes (both the
API and the CLI wrapper) to keep absolute paths. Absolute paths are valid in
every beets version and resolve correctly regardless of the active music
directory.

### Verifying an import

beets exits `0` even when it skips an album. After the subprocess finishes,
Beetser compares `MAX(items.id)` before and after:

- new rows → success (recording album IDs, paths and hashing the new files);
- no new rows → failure/skip, with the CLI output stored in the job log for the UI.

## Organizing after import

Because tag-only imports never rename or move anything, sorting is a separate,
explicit action: `POST /api/library/albums/<id>/organize` for one album, or
`POST /api/origins/<id>/organize` for every album of an origin. Both run
`beet move -a -d <base> id:<album>`, which applies the path formats without
touching metadata and moves album art with the files.

The base directory is the album's current root: albums still inside their origin
are sorted in place (`origin/Artist/Album/…`), while albums already moved to a
destination stay there. Moving files invalidates the scanner bookkeeping, so
`beetser/organize.py` rewrites the `tracked_files` rows from the old paths to the
new ones. Without that, a future download reusing the same folder names would be
mistaken for an already-imported file.

## Editing albums after import

Album edits reuse the same per-origin config and run `beet modify` through the
CLI wrapper, so path formats, tag writing and file moves behave exactly like an
import. Artwork changes go through beets' `Album.set_art`, which copies the
image into the album folder, and optionally embed it into each item.

## Duplicate protection

Three independent layers:

1. **Exact files** — SHA-256 compared against `imported_fingerprints` and
   `tracked_files`. Catches the same download arriving twice.
2. **Release identity** — the candidate's MusicBrainz release ID already exists
   in `albums.mb_albumid`.
3. **Album/track similarity** — same normalized album name and artist, or
   incoming tracks whose artist, title and length (±3 s) match existing items.

A blocking report moves the job to `duplicate`. Importing anyway is an explicit,
confirmed action; it also sets `force=true` on the API call.

## Job state machine

| State | Meaning | Transitions |
| --- | --- | --- |
| `discovered` | Files grouped, waiting for analysis | → `analyzing` |
| `analyzing` | Lookup running | → `ready`, `needs_review`, `duplicate`, `failed` |
| `ready` | Decision made, waiting for import | → `importing` |
| `importing` | beets is moving/copying files | → `imported`, `failed` |
| `needs_review` | Human decision required | → `ready` (apply), `skipped` |
| `duplicate` | Duplicate report is blocking | → `ready` (force), `skipped` |
| `failed` | Import/analysis error | → `discovered` (retry), `skipped` |
| `imported` | Files in the library | terminal |
| `skipped` | Dismissed, files left untouched | terminal (Remove to forget) |

On startup, `discovered`/`ready` jobs are requeued and `importing` jobs (killed
mid-flight) are marked failed with a note.

## API and UI

- REST API under `/api`, OpenAPI docs at `/api/docs`.
- Authentication: one admin account. The password is scrypt-hashed; sessions are
  signed cookies (`itsdangerous`). Login attempts are throttled per client.
- **SSE** at `/api/system/events` notifies the UI of changes; TanStack Query
  invalidates the affected caches. This keeps the review queue and dashboard
  live without polling.
- The React SPA (Vite + Tailwind) is built into the image and served by FastAPI
  with an SPA fallback.

## Known limitations

- **Multi-disc albums** in separate `CD1`/`CD2` directories are treated as
  separate album jobs. Put multi-disc releases in one folder or import them
  manually for now.
- **Singletons** are stored as beets singletons (no album row) and shown in the
  Library's *Singles* tab.
- **AcoustID fingerprinting** is not used; matching relies on existing tags and
  track lengths.
- **inotify over network shares** is unreliable. The periodic scan is the safety
  net; lower `scan_interval_seconds` if latency matters.
- **`beets>=2.14.1` is required** for the Source/Proposal API used here.
- A library created by a *newer* beets version cannot be opened by the pinned
  version. Back up `/config` before upgrading.
- Import music through Beetser (or its CLI wrapper). A plain `beet import`
  invoked with a different `directory` may store relative paths, which a
  multi-destination library cannot resolve unambiguously.
