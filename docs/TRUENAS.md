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
| Image | `ghcr.io/jandrourgh/beetser:0.1.0` |
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

## Publishing to the community catalog

Beetser's app definition lives in
[`catalog/ix-dev/community/beetser`](catalog/ix-dev/community/beetser) and is
laid out exactly like the apps in
[`truenas/apps`](https://github.com/truenas/apps):

```
app.yaml                          catalog metadata (train, versions, lib hash)
item.yaml                         icon, screenshots and tags for the card
ix_values.yaml                    image repository/tag and constants
questions.yaml                    install wizard (groups, ports, storage)
README.md                         description shown in the catalog
templates/docker-compose.yaml     Jinja template rendered by the catalog library
templates/test_values/*.yaml      installation scenarios used by CI
```

It is written against catalog library **2.3.21** and renders with the
`ix_lib` API (`add_container`, `deps.perms`, `add_storage`, ...), not with plain
Docker Compose.

### Licensing

| Component | License | What it means for publishing |
| --- | --- | --- |
| Beetser | MIT ([LICENSE](LICENSE)) | You can publish and redistribute it freely |
| beets 2.14.1 | MIT | Redistribute with its copyright notice (in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and `/app/licenses` inside the image) |
| mutagen, Unidecode (beets dependencies) | GPL-2.0-or-later | Ship them unmodified and keep their source/license available (they are Python packages inside the image, so their sources travel with it) |
| FFmpeg (Debian package), Chromaprint | GPL-2.0-or-later / LGPL-2.1-or-later | Invoked as separate binaries by beets; keep the notices and offer the sources |

Bottom line: beets being MIT is what makes this publishable. The GPL pieces are
unmodified third-party dependencies, not part of Beetser's own code, so the
Beetser source stays MIT. The image ships `LICENSE`,
`THIRD_PARTY_NOTICES.md` and the Debian copyright files under
`/app/licenses` and `/usr/share/doc`.

### Release checklist

1. **Publish the image** so `ghcr.io/jandrourgh/beetser:<tag>` exists and is
   public. Pushing a `vX.Y.Z` tag runs
   [`.github/workflows/container-image.yml`](../.github/workflows/container-image.yml),
   which builds `linux/amd64` + `linux/arm64` and pushes `X.Y.Z`, `X.Y`,
   `sha-<commit>` and `latest` to GHCR:

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

   The first run creates a **private** package; open the package settings on
   GitHub and switch its visibility to *public* so TrueNAS can pull it without
   credentials. Pulls are anonymous afterwards.

   The catalog expects `ghcr.io`. Keep the tag equal to `app_version`. The
   workflow prints the multi-arch digest in the run summary; optionally pin it
   in `ix_values.yaml` (`tag: "0.1.0@sha256:..."`) so installs are
   reproducible.

   Without CI (or to rebuild by hand), the equivalent local command is:

   ```bash
   docker buildx build --platform linux/amd64,linux/arm64 \
     -t ghcr.io/jandrourgh/beetser:0.1.0 --push .
   ```

2. **Bump the chart**: `app_version` (image tag) and `version` (chart) in
   `app.yaml`, and `images.image.tag` in `ix_values.yaml`.

3. **Refresh the library reference** when `truenas/apps` releases a newer
   `library/<version>`: set `lib_version` in `app.yaml` and copy the value of
   that version from `library/hashes.yaml` into `lib_version_hash`.

4. **Validate** with the official tooling (Docker required). From a clone of
   `truenas/apps` with this chart copied into
   `ix-dev/community/beetser`:

   ```bash
   # structure + metadata validation
   docker run --platform=linux/amd64 --rm -e FAKE_ENV=1 \
     -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory \
     -e GIT_CONFIG_VALUE_0=/workspace \
     -v "$PWD:/workspace" ghcr.io/truenas/apps_validation:slim \
     apps_dev_charts_validate validate --path /workspace

   # render each test scenario (needs pyyaml; use devbox shell if available)
   python3 .github/scripts/ci.py --train community --app beetser \
     --test-file basic-values.yaml --render-only=true --skip-metadata
   python3 .github/scripts/ci.py --train community --app beetser \
     --test-file host-path-values.yaml --render-only=true --skip-metadata
   ```

   Drop `--render-only=true` to also start the stack (requires the published
   image) and verify the healthcheck.

5. **Open an issue first** (`truenas/apps` asks for it in the PR template), then
   a PR that only adds files under `ix-dev/community/beetser/`. Include in the
   PR description: upstream link, app version, tested scenarios and the icon
   plus screenshots — the reviewers upload them to
   `https://media.sys.truenas.net/apps/beetser/` and give you the final URLs
   for `app.yaml`/`item.yaml`.

6. After merge, version bumps flow through their automation; you should not open
   PRs just to change the image tag.

### Install wizard

The chart exposes the minimum needed for a working install:

- **Administrator password** (optional; otherwise the UI asks for one on first
  visit).
- **User/group** to run as (defaults to `568:568`, TrueNAS' `apps` user).
- **Web UI port** (default `8080`).
- **Config storage** — `/config`, holds `library.db`, the app database and the
  generated beets configs. Back this up.
- **Media folders** — one storage entry per folder to watch, mounted at any
  container path (for example `/media/soulseek`). Use that container path as the
  origin path in the UI.

Everything else (import mode, path formats, auto-tag threshold, notifications)
is a runtime setting in the web UI, so upgrades never clobber it.

### Before the first PR

- The icon must be a square PNG ≥ 256×256. Screenshots should show the dashboard
  and the review queue (see `docs/screenshots/`).
- `app.yaml` currently points at `https://media.sys.truenas.net/apps/beetser/...`
  placeholders; replace them with the URLs the reviewers provide.
