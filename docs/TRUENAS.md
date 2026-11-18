# TrueNAS SCALE

Beetser ships as a single Docker image with no external dependencies. It works
as a **Custom App** (Docker Compose) and includes a scaffold for the community
Apps catalog.

## Requirements

- TrueNAS SCALE 24.10 (Electric Eel) or newer — the Docker-based Apps system.
- An apps dataset with enough space for `/config` (the database is small; a few
  hundred MB is plenty).
- A media dataset (or datasets) containing the folders Beetser should watch.
- Network access to `musicbrainz.org` and `coverartarchive.org` for tagging.

Suggested resources: 1 CPU, 512 MB RAM, 1 GB free on the apps dataset.

## 1. Prepare datasets

```text
/mnt/tank/apps/beetser              ← app data (owned by 568:568)
/mnt/tank/media/soulseek            ← origin (one per service)
/mnt/tank/media/downloads           ← origin
/mnt/tank/media/incoming            ← origin
/mnt/tank/music                     ← optional central destination
```

In the TrueNAS UI: **Datasets → Add Dataset**, then **Edit Permissions** and set
the owner to `apps` (UID/GID `568`) with read/write access for that dataset.

> The container runs as `PUID:PGID` (default `1000:1000`; the TrueNAS examples
> use `568:568`). It must be able to create folders in every destination and
> delete/move files in every origin.

## 2. Install as a Custom App

Easiest: **Apps → Discover Apps → Custom App**, then paste
[`truenas/custom-app.yaml`](custom-app.yaml) and adjust:

```yaml
environment:
  BEETSER_PASSWORD: "a-strong-password"
  PUID: "568"
  PGID: "568"
volumes:
  - /mnt/tank/apps/beetser:/config
  # One container path per service/dataset:
  - /mnt/tank/media/soulseek:/media/soulseek
  - /mnt/tank/media/downloads:/media/downloads
  - /mnt/tank/media/incoming:/media/incoming
  - /mnt/tank/music:/music
```

Remove or add mounts to match your services. Every container path becomes an
origin you can configure in Beetser.

If you prefer the UI form, use:

| Field | Value |
| --- | --- |
| Image | `ghcr.io/beetser/beetser:0.1.0` |
| Port | `8080` → `8080` |
| Storage | Host path `/mnt/tank/apps/beetser` → `/config` |
| Storage | Host path `/mnt/tank/media/soulseek` → `/media/soulseek` |
| Storage | Host path `/mnt/tank/media/downloads` → `/media/downloads` |
| Storage | Host path `/mnt/tank/media/incoming` → `/media/incoming` |
| Storage | Host path `/mnt/tank/music` → `/music` (optional) |
| Env | `BEETSER_PASSWORD`, `PUID=568`, `PGID=568` |

The app starts in ~2 seconds. `GET /api/system/health` returns `{"status":"ok"}`.

## 3. Configure Beetser

Open `http://<truenas-ip>:8080`.

1. Sign in (or create the password if you did not set `BEETSER_PASSWORD`).
2. **Origins → Add origin** for each mounted folder:
   - source path, e.g. `/media/soulseek`, `/media/downloads`, `/media/incoming`
   - destination: the same path (sort in place) or `/music` for a shared library
   - import mode: *inherit* (global `move`), *move* or *copy*
   - auto-tag: *global*, *enabled* or *disabled*
3. Drop an album into the origin. Watch it appear in **Review** or **Library**.

Every path you type is a path **inside the container**. Mount each dataset you
need at its own container path (`/media/sonarr`, `/media/radarr`, …). Do not
expect Beetser to see host paths such as `/mnt/tank/...` directly.

If you prefer one shared tree, mount its parent once (`/mnt/tank/media:/media`)
and use subfolders like `/media/sonarr` inside it. Both models work; mixing a
parent and its children as separate mounts is possible but harder to reason
about.

## Notes specific to TrueNAS

- **Network shares:** inotify does not propagate over SMB/NFS. The periodic scan
  (Settings → Scanning) is the safety net; set it to 60–120 seconds if you want
  imports to start quickly. Local ZFS datasets get instant inotify.
- **Snapshots:** `#snapshot` and `@eaDir` directories are ignored by default.
- **Permissions:** if imports fail with `EACCES`, check that `PUID:PGID` can
  write to the destination and move files out of the origin. The entrypoint
  repairs ownership of `/config` on start, but not of media paths.
- **Updates:** change the image tag in the app settings and restart. Back up
  `/config` first — the beets schema can migrate on upgrade.
- **Resource use:** scanning hashes new files. A very large first-time library
  will temporarily use CPU/disk; subsequent scans only hash new files.

## Community catalog chart (scaffold)

The folder [`catalog/ix-dev/stable/beetser`](catalog/ix-dev/stable/beetser)
contains a starting point for a PR to the
[`truenas/apps`](https://github.com/truenas/apps) repository:

```
app.yaml              metadata (title, train, version, lib_version)
ix_values.yaml        image tag and defaults
questions.yaml        install wizard fields
templates/
  docker-compose.yaml rendered compose file
```

Before submitting:

1. Publish the image to a registry and set `images.image.repository/tag` in
   `ix_values.yaml`.
2. Bump `app_version`, `version`, `lib_version` and `lib_version_hash` to match
   the current `truenas/apps` library release (the hash is provided by their
   tooling).
3. Add a real icon URL and maintainer details in `app.yaml`.
4. Run the catalog validation tooling from `truenas/apps` (`python3
   .github/scripts/validate.py` or their CI) — chart templating details change
   between library versions, and this scaffold is intentionally minimal.

A custom app is the supported path today; the catalog chart is a convenience
for publishing.
