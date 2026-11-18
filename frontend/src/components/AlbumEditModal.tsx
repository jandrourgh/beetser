import { useMutation } from "@tanstack/react-query";
import { ImagePlus, RefreshCw, Save, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { apiClient } from "../lib/api";
import type { AlbumDetail, AlbumUpdate } from "../lib/types";
import { Button, Cover, Field, Modal, Switch, TextInput } from "./ui";

interface TrackDraft {
  title: string;
  artist: string;
  track: string;
  disc: string;
}

const emptyTrack = (): TrackDraft => ({ title: "", artist: "", track: "", disc: "" });

export function AlbumEditModal({
  album,
  open,
  onClose,
  onAlbumChanged,
}: {
  album: AlbumDetail;
  open: boolean;
  onClose: () => void;
  onAlbumChanged: (album: AlbumDetail) => void;
}) {
  const [fields, setFields] = useState<Record<string, string>>({});
  const [tracks, setTracks] = useState<Record<number, TrackDraft>>({});
  const [writeTags, setWriteTags] = useState(true);
  const [moveFiles, setMoveFiles] = useState(true);
  const [artMtime, setArtMtime] = useState<number | null>(album.art_mtime ?? null);
  const [hasArt, setHasArt] = useState(Boolean(album.artpath));
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setFields({
      album: album.album ?? "",
      albumartist: album.albumartist ?? "",
      year: album.year ? String(album.year) : "",
      genres: album.genres ?? "",
      label: album.label ?? "",
      catalognum: album.catalognum ?? "",
      country: album.country ?? "",
      albumtype: album.albumtype ?? "",
      albumdisambig: album.albumdisambig ?? "",
      barcode: album.barcode ?? "",
      asin: album.asin ?? "",
    });
    const next: Record<number, TrackDraft> = {};
    album.tracks.forEach((track) => {
      next[track.id] = {
        title: track.title ?? "",
        artist: track.artist ?? "",
        track: track.track ? String(track.track) : "",
        disc: track.disc ? String(track.disc) : "",
      };
    });
    setTracks(next);
    setWriteTags(true);
    setMoveFiles(true);
    setArtMtime(album.art_mtime ?? null);
    setHasArt(Boolean(album.artpath));
  }, [open, album.id]);

  const applyAlbum = (updated: AlbumDetail) => {
    setArtMtime(updated.art_mtime ?? Date.now() / 1000);
    setHasArt(Boolean(updated.artpath));
    onAlbumChanged(updated);
  };

  const save = useMutation({
    mutationFn: () => {
      const payload: AlbumUpdate = {
        fields: Object.fromEntries(
          Object.entries(fields).map(([key, value]) => [key, value.trim()]),
        ),
        tracks: Object.fromEntries(
          Object.entries(tracks).map(([id, draft]) => [
            Number(id),
            {
              title: draft.title.trim(),
              artist: draft.artist.trim(),
              ...(draft.track.trim() ? { track: draft.track.trim() } : {}),
              ...(draft.disc.trim() ? { disc: draft.disc.trim() } : {}),
            },
          ]),
        ),
        write_tags: writeTags,
        move_files: moveFiles,
      };
      return apiClient.updateAlbum(album.id, payload);
    },
    onSuccess: (result) => {
      applyAlbum(result.album);
      if (result.warnings.length) {
        toast.warning(result.warnings.join(" "));
      } else {
        toast.success("Album updated");
      }
      onClose();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not update album"),
  });

  const upload = useMutation({
    mutationFn: (file: File) => apiClient.uploadAlbumCover(album.id, file),
    onSuccess: (result) => {
      applyAlbum(result.album);
      if (result.warnings.length) toast.warning(result.warnings.join(" "));
      else toast.success("Cover updated");
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not upload cover"),
  });

  const removeArt = useMutation({
    mutationFn: () => apiClient.deleteAlbumCover(album.id),
    onSuccess: (result) => {
      applyAlbum(result.album);
      if (result.warnings.length) toast.warning(result.warnings.join(" "));
      else toast.success("Cover removed");
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not remove cover"),
  });

  const fetchArt = useMutation({
    mutationFn: () => apiClient.fetchAlbumCover(album.id),
    onSuccess: (result) => {
      applyAlbum(result.album);
      if (result.warnings.length) toast.warning(result.warnings.join(" "));
      else toast.success("Cover downloaded from Cover Art Archive");
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not fetch cover"),
  });

  const onFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      toast.error("Use a JPEG, PNG or WebP image");
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      toast.error("Image is larger than 15 MB");
      return;
    }
    upload.mutate(file);
  };

  const busy = save.isPending || upload.isPending || removeArt.isPending || fetchArt.isPending;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Edit album"
      description="Metadata, tracks and artwork. Changes are written to the files and the library."
      size="xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            icon={<Save className="h-4 w-4" />}
            loading={save.isPending}
            disabled={busy}
            onClick={() => save.mutate()}
          >
            Save changes
          </Button>
        </>
      }
    >
      <div className="space-y-6">
        <div className="flex flex-col gap-4 rounded-xl border border-line bg-surface-2/30 p-3 sm:flex-row">
          <Cover
            src={hasArt ? apiClient.coverUrl(album.id, artMtime) : null}
            alt={album.album}
            className="h-32 w-32 shrink-0"
            rounded="rounded-xl"
          />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-fg">Artwork</p>
            <p className="mt-0.5 text-xs text-muted">
              Upload a cover, download it from the Cover Art Archive, or remove the current one.
              The image is stored as the album's cover file and can also be cleared from embedded tags.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <input
                ref={fileInput}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={onFile}
              />
              <Button
                size="sm"
                variant="secondary"
                icon={<ImagePlus className="h-4 w-4" />}
                loading={upload.isPending}
                disabled={busy}
                onClick={() => fileInput.current?.click()}
              >
                Upload image
              </Button>
              <Button
                size="sm"
                variant="outline"
                icon={<RefreshCw className="h-4 w-4" />}
                loading={fetchArt.isPending}
                disabled={busy || !album.mb_albumid}
                onClick={() => fetchArt.mutate()}
                title={album.mb_albumid ? "Fetch from Cover Art Archive" : "No MusicBrainz release id"}
              >
                Fetch from CAA
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-danger hover:bg-danger-soft"
                icon={<Trash2 className="h-4 w-4" />}
                loading={removeArt.isPending}
                disabled={busy}
                onClick={() => {
                  if (window.confirm("Remove the cover art from this album and its files?")) {
                    removeArt.mutate();
                  }
                }}
              >
                Remove
              </Button>
            </div>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Album">
            <TextInput value={fields.album ?? ""} onChange={(e) => setFields({ ...fields, album: e.target.value })} />
          </Field>
          <Field label="Album artist">
            <TextInput
              value={fields.albumartist ?? ""}
              onChange={(e) => setFields({ ...fields, albumartist: e.target.value })}
            />
          </Field>
          <Field label="Year">
            <TextInput
              inputMode="numeric"
              value={fields.year ?? ""}
              onChange={(e) => setFields({ ...fields, year: e.target.value })}
            />
          </Field>
          <Field label="Genres" hint="separated by ;">
            <TextInput value={fields.genres ?? ""} onChange={(e) => setFields({ ...fields, genres: e.target.value })} />
          </Field>
          <Field label="Label">
            <TextInput value={fields.label ?? ""} onChange={(e) => setFields({ ...fields, label: e.target.value })} />
          </Field>
          <Field label="Catalogue number">
            <TextInput
              value={fields.catalognum ?? ""}
              onChange={(e) => setFields({ ...fields, catalognum: e.target.value })}
            />
          </Field>
          <Field label="Country">
            <TextInput value={fields.country ?? ""} onChange={(e) => setFields({ ...fields, country: e.target.value })} />
          </Field>
          <Field label="Album type">
            <TextInput
              value={fields.albumtype ?? ""}
              onChange={(e) => setFields({ ...fields, albumtype: e.target.value })}
            />
          </Field>
          <Field label="Disambiguation">
            <TextInput
              value={fields.albumdisambig ?? ""}
              onChange={(e) => setFields({ ...fields, albumdisambig: e.target.value })}
            />
          </Field>
          <Field label="Barcode">
            <TextInput value={fields.barcode ?? ""} onChange={(e) => setFields({ ...fields, barcode: e.target.value })} />
          </Field>
          <Field label="ASIN">
            <TextInput value={fields.asin ?? ""} onChange={(e) => setFields({ ...fields, asin: e.target.value })} />
          </Field>
        </div>

        <div>
          <p className="mb-2 text-xs font-medium text-fg">Tracks</p>
          <div className="overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-left text-xs">
              <thead className="bg-surface-2/50 text-[10px] uppercase tracking-wide text-muted">
                <tr>
                  <th className="w-20 px-2 py-2 font-medium">Disc</th>
                  <th className="w-20 px-2 py-2 font-medium">Track</th>
                  <th className="px-2 py-2 font-medium">Title</th>
                  <th className="px-2 py-2 font-medium">Artist</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {album.tracks.map((track) => (
                  <tr key={track.id}>
                    <td className="px-2 py-1.5">
                      <TextInput
                        className="h-8 w-16 text-xs"
                        value={tracks[track.id]?.disc ?? ""}
                        onChange={(e) =>
                          setTracks({ ...tracks, [track.id]: { ...(tracks[track.id] ?? emptyTrack()), disc: e.target.value } })
                        }
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <TextInput
                        className="h-8 w-16 text-xs"
                        value={tracks[track.id]?.track ?? ""}
                        onChange={(e) =>
                          setTracks({ ...tracks, [track.id]: { ...(tracks[track.id] ?? emptyTrack()), track: e.target.value } })
                        }
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <TextInput
                        className="h-8 text-xs"
                        value={tracks[track.id]?.title ?? ""}
                        onChange={(e) =>
                          setTracks({ ...tracks, [track.id]: { ...(tracks[track.id] ?? emptyTrack()), title: e.target.value } })
                        }
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <TextInput
                        className="h-8 text-xs"
                        value={tracks[track.id]?.artist ?? ""}
                        onChange={(e) =>
                          setTracks({ ...tracks, [track.id]: { ...(tracks[track.id] ?? emptyTrack()), artist: e.target.value } })
                        }
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-xl border border-line bg-surface-2/30 px-3">
          <Switch
            label="Write tags to files"
            description="Persist the edited metadata inside the audio files."
            checked={writeTags}
            onChange={setWriteTags}
            disabled={busy}
          />
          <Switch
            label="Move files to the new paths"
            description="Reorganize the album if album artist, album name, year or track numbers changed."
            checked={moveFiles}
            onChange={setMoveFiles}
            disabled={busy}
          />
        </div>
      </div>
    </Modal>
  );
}
