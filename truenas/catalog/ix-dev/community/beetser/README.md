# Beetser

[Beetser](https://github.com/jandrourgh/beetser) is a self-hosted web frontend and
automation layer for [beets](https://beets.io/).

Point it at the folders your download clients write to. Beetser watches them,
groups new files into albums, looks them up on MusicBrainz and either imports
confident matches or queues them for review. Imports are tag-only by default:
metadata and cover art are written in place and folders are left untouched until
you press **Organize**. One central beets library is shared by every origin,
with SHA-256 and MusicBrainz based duplicate protection.

Add one storage entry per folder you want watched (for example
`/media/soulseek`, `/media/downloads` and `/media/incoming`), then create an
origin in the UI using that container path.
