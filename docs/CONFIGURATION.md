# Configuration

There are two layers:

1. **Deployment configuration** — environment variables read at startup.
2. **Runtime settings** — stored in `/config/beetser.db` and edited in the UI
   (global defaults, plus per-origin overrides).

## Environment variables

All variables use the `BEETSER_` prefix unless noted.

| Variable | Default | Description |
| --- | --- | --- |
| `BEETSER_DATA_DIR` | `/config` | State, library database, generated configs |
| `BEETSER_LIBRARY_DB` | `$DATA_DIR/library.db` | Central beets library path |
| `BEETSER_STATIC_DIR` | `static` | Built frontend assets |
| `BEETSER_HOST` | `0.0.0.0` | HTTP bind address |
| `BEETSER_PORT` | `8080` | HTTP port |
| `BEETSER_LOG_LEVEL` | `INFO` | Python log level |
| `BEETSER_PASSWORD` | — | Admin password (plain). Used unless a UI password was set |
| `BEETSER_PASSWORD_HASH` | — | Pre-hashed password (`scrypt$…`, see below) |
| `BEETSER_SECRET_KEY` | generated | Session signing key. Persisted to `$DATA_DIR/secret.key` if unset |
| `BEETSER_SESSION_MAX_AGE` | `1209600` | Session lifetime in seconds (14 days) |
| `BEETSER_SECURE_COOKIES` | `false` | Force the `Secure` cookie flag (auto-detected from `X-Forwarded-Proto`) |
| `BEETSER_SCAN_INTERVAL` | `300` | Full-scan interval used on first run (later read from the UI setting) |
| `BEETSER_IMPORT_TIMEOUT` | `900` | Per-import subprocess timeout (seconds) |
| `PUID` / `PGID` | `1000` | Container user/group (entrypoint drops privileges) |
| `TZ` | system | Container timezone |

Generating a password hash without Beetser installed:

```bash
python - <<'PY'
import base64, hashlib, secrets
salt = secrets.token_bytes(16)
digest = hashlib.scrypt(b"your-password", salt=salt, n=16384, r=8, p=1, dklen=32)
print("scrypt$16384$8$1$%s$%s" % (
    base64.b64encode(salt).decode(), base64.b64encode(digest).decode()))
PY
```

> If `BEETSER_PASSWORD` is set, it keeps working even after changing the
> password in the UI. Remove the variable if the UI password should be the only
> one.

## Global settings

| Key | Default | Description |
| --- | --- | --- |
| `import_mode` | `tag` | `tag` (write tags, leave files in place), `move` or `copy`; the default for origins set to *inherit* |
| `path_format` | `$albumartist/$album%aunique{}/$track $title` | beets path template for albums |
| `comp_path_format` | `Compilations/$album%aunique{}/$track $title` | template for Various Artists albums |
| `singleton_path_format` | `Singletons/$artist/$title` | template for singleton imports |
| `write_tags` | `true` | Write matched metadata into the files (`tag` mode always writes tags) |
| `delete_empty_dirs` | `true` | Remove empty folders left in an origin after a move |
| `auto_tag_enabled` | `true` | Master switch for automatic imports |
| `auto_tag_threshold` | `0.85` | Minimum similarity (0–1) for an automatic import |
| `auto_tag_min_gap` | `0.03` | Required lead over a competing, different release |
| `fetch_art` | `true` | Add online cover sources (Cover Art Archive/iTunes). Local `cover`/`folder` images are always adopted |
| `embed_art` | `false` | Also enable `embedart` (write art into file tags) |
| `settle_seconds` | `30` | Ignore files modified more recently than this |
| `scan_interval_seconds` | `300` | Safety-net full scan interval |
| `include_singletons` | `true` | Import files directly in an origin root individually |
| `notify_webhook_url` | empty | Webhook for notifications |
| `notify_on_review` | `true` | Notify when a job needs review (including duplicates) |
| `notify_on_import` | `false` | Notify after automatic imports |
| `notify_on_error` | `true` | Notify after failed imports |
| `ignore_dirs` | `@eaDir`, `#recycle`, `#snapshot`, `lost+found`, `System Volume Information` | Folder names skipped while scanning |
| `ignore_globs` | `.*`, `*~`, `Thumbs.db`, `.DS_Store` | File name patterns skipped while scanning |

Settings are validated server-side (types, ranges, protected keys).

## Origins

| Field | Description |
| --- | --- |
| Name | Display name |
| Path | Absolute folder inside the container |
| Destination | Where imported music is organized. Defaults to the origin path |
| Import mode | `inherit` (global), `move` or `copy` |
| Auto-tag | `inherit` (global), `enabled` (auto-import above the threshold) or `disabled` (always review) |
| Confidence threshold | Per-origin override for `auto_tag_threshold` |
| Settle time | Per-origin override for `settle_seconds` |
| Watch | Use inotify in addition to periodic scans |
| Enabled | Disable to pause an origin without deleting it |
| Import loose files as singles | Treat root-level files as singletons |
| Album / singleton path format | Per-origin beets templates (empty = global) |
| Notes | Free text |

Origins may not overlap (a path cannot be equal to, inside, or a parent of
another origin) because that would import the same files twice.

### Multiple media mounts (Docker)

Beetser can only see paths that exist **inside the container**. If different
services write to different host folders/datasets, mount each one at its own
container path. The repository includes
[`docker-compose.multi-media.yml`](../docker-compose.multi-media.yml):

```yaml
services:
  beetser:
    # Replaces the single /media mount from docker-compose.yml.
    # Requires Docker Compose 2.24+ (the current Docker Engine ships newer).
    volumes: !override
      - ./config:/config
      - /mnt/tank/media/soulseek:/media/soulseek
      - /mnt/tank/media/downloads:/media/downloads
      - /mnt/tank/media/incoming:/media/incoming
      - /mnt/tank/music:/music
```

Apply it in one of two ways:

```bash
# Explicit, nothing to copy:
docker compose -f docker-compose.yml -f docker-compose.multi-media.yml up -d

# Or make it permanent (auto-loaded and git-ignored):
cp docker-compose.multi-media.yml docker-compose.override.yml
docker compose up -d
```

Then add one **origin per mount** in the UI:

| Origin path | Destination | Mode |
| --- | --- | --- |
| `/media/soulseek` | `/media/soulseek` | tag only (default) |
| `/media/downloads` | `/media/downloads` | tag only (default) |
| `/media/incoming` | `/media/incoming` | tag only (default) |
| `/media/downloads` | `/music` | move (central library) |

The app's path browser (Origins → Browse) shows exactly what is mounted.

> Mount either one parent folder at `/media` **or** individual children such as
> `/media/sonarr`. Do not try to "share" a single mount point between two host
> folders; Docker mounts one host path per container path.

### Common layouts

**Tag only, organize later (the default)**

```
Origin:      /media/downloads
Destination: /media/downloads      (same as origin)
Mode:        tag
```

Imports run like `beet import -CMw`: tags (and cover art) are written in place,
the folder layout is untouched. When the metadata looks right, press
**Organize files** on the album (or **Organize** on the origin to do all its
albums) to sort them into `Artist/Album/…`. Organizing never rewrites tags and
keeps the files inside the origin folder.

**Inbox → central library (move)**

```
Origin:      /media/downloads
Destination: /media/music
Mode:        move
```

Downloads are tagged, moved to `/media/music/<artist>/<album>/…`, and the inbox
is left clean.

**Sort in place (move)**

```
Origin:      /media/downloads
Destination: /media/downloads      (same as origin)
Mode:        move
```

Files stay inside the origin tree but are renamed into artist/album folders.

**Archive without deleting (copy)**

```
Origin:      /media/incoming
Destination: /media/archive
Mode:        copy
```

The original download is kept; the library receives a tagged copy.

## Path formats

Any [beets path template](https://beets.readthedocs.io/en/stable/reference/pathformat.html)
works. Useful fields: `$albumartist`, `$album`, `$year`, `$track`, `$title`,
`$disc`, `$genre`, `$label`, `$catalognum`, `$format`.

- `%aunique{}` disambiguates albums with the same name (adds year/label/etc.).
- The default layout is `Artist/Album/01 Title.ext`.
- Set a per-origin format when different sources should be laid out differently
  (e.g. audiobooks in `$albumartist/$series/$album`).

> Path templates are evaluated by beets, not by Beetser. Invalid templates make
> imports fail with the beets error in the job log.

## Notifications

When a webhook URL is configured, Beetser POSTs JSON:

```json
{
  "title": "Album needs review",
  "message": "Artist - Album from Downloads",
  "text": "Album needs review\nArtist - Album from Downloads",
  "content": "**Album needs review**\nArtist - Album from Downloads",
  "kind": "review",
  "url": null
}
```

`content` is Discord-flavoured; `text` suits ntfy/Slack; the rest is generic.
No retries are attempted — a failed webhook is logged and dropped.

## Reverse proxy

Beetser speaks plain HTTP on `8080`. Example Caddy configuration:

```caddy
music.example.com {
    reverse_proxy 127.0.0.1:8080 {
        flush_interval -1   # keep server-sent events streaming
    }
}
```

Nginx requires `proxy_buffering off;` (or `X-Accel-Buffering: no`, which Beetser
already sends) for the live event stream.

## Backups

Back up the whole `/config` directory. It contains:

- `library.db` — the music library metadata (small);
- `beetser.db` — jobs, origins, fingerprints;
- `secret.key` — invalidating it signs everyone out;
- generated beets configs.

The media files themselves live wherever you pointed the origins. Beetser also
keeps a rolling daily copy of the library at `library.db.backup`.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Files are not picked up | Origin path exists *inside the container*; settle time elapsed; folder not ignored; `.beetser-ignore` absent |
| Job fails instantly | Open the Log tab — usually a beets config/path format error or permission problem |
| "Duplicate must be confirmed" | Expected: use *Import anyway* or *Skip* |
| MusicBrainz failures | Lookup errors leave the job in review; retry when the network is back |
| No cover art | Is there a local `cover`/`folder`/`front` image? `fetch_art` enabled and Cover Art Archive reachable? Upload one from **Edit album** |
| Wrong destination | `destination` on the origin; *inherit* uses the global import mode only, not the destination |
| Nothing updates in the UI | `/api/system/events` blocked by a proxy (disable buffering) |
