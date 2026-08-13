"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";

type GalleryOption = { id: number; slug: string; title: string; item_count: number; is_public: boolean };

type FileRow = {
  id: string;
  file: File;
  status: "queued" | "uploading" | "processing" | "done" | "duplicate" | "failed";
  progress: number;
  mediaId?: number;
  error?: string;
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function putWithProgress(url: string, file: File, onProgress: (pct: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`upload failed: ${xhr.status}`));
    };
    xhr.onerror = () => reject(new Error("upload network error"));
    xhr.send(file);
  });
}

export function UploadPanel() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<"files" | "url">("files");
  const [rows, setRows] = useState<FileRow[]>([]);
  const [galleries, setGalleries] = useState<GalleryOption[]>([]);
  const [galleryId, setGalleryId] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [urlValue, setUrlValue] = useState("");
  const [urlMsg, setUrlMsg] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    fetch("/api/upload/galleries")
      .then((r) => r.json())
      .then((j) => setGalleries(j.items ?? []))
      .catch(() => undefined);
  }, []);

  const updateRow = useCallback((id: string, patch: Partial<FileRow>) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }, []);

  const queueFiles = useCallback((files: FileList | File[]) => {
    const list = Array.from(files);
    if (!list.length) return;
    setRows((prev) => [
      ...prev,
      ...list.map((file) => ({
        id: `${file.name}-${file.size}-${file.lastModified}-${Math.random()}`,
        file,
        status: "queued" as const,
        progress: 0,
      })),
    ]);
  }, []);

  const runUpload = useCallback(async () => {
    const pending = rows.filter((r) => r.status === "queued");
    if (!pending.length || busy) return;
    setBusy(true);

    try {
      const presignRes = await fetch("/api/upload/presign", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          files: pending.map((r) => ({
            name: r.file.name,
            contentType: r.file.type || "application/octet-stream",
            size: r.file.size,
          })),
          galleryId: galleryId ? Number.parseInt(galleryId, 10) : null,
        }),
      });
      const presignJson = await presignRes.json();
      if (!presignRes.ok) {
        throw new Error(presignJson.error || "presign failed");
      }

      const uploads: Array<{
        key: string;
        putUrl: string;
        contentType: string;
        filename: string;
        byteSize: number;
      }> = presignJson.uploads;

      const completeItems: Array<{
        key: string;
        filename: string;
        contentType: string;
        byteSize: number;
        rowId: string;
      }> = [];

      for (let i = 0; i < pending.length; i++) {
        const row = pending[i];
        const slot = uploads[i];
        if (!slot) continue;
        updateRow(row.id, { status: "uploading", progress: 0 });
        try {
          await putWithProgress(slot.putUrl, row.file, (pct) => updateRow(row.id, { progress: pct }));
          updateRow(row.id, { status: "processing", progress: 100 });
          completeItems.push({
            key: slot.key,
            filename: slot.filename,
            contentType: slot.contentType,
            byteSize: slot.byteSize,
            rowId: row.id,
          });
        } catch (e) {
          updateRow(row.id, { status: "failed", error: (e as Error).message });
        }
      }

      if (completeItems.length) {
        const completeRes = await fetch("/api/upload/complete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            items: completeItems.map(({ rowId: _r, ...rest }) => rest),
            galleryId: galleryId ? Number.parseInt(galleryId, 10) : null,
          }),
        });
        const completeJson = await completeRes.json();
        if (!completeRes.ok) throw new Error(completeJson.error || "complete failed");

        for (const result of completeJson.results ?? []) {
          const match = completeItems.find((c) => c.key === result.key);
          if (!match) continue;
          if (result.status === "done") {
            updateRow(match.rowId, { status: "done", mediaId: result.mediaId });
          } else if (result.status === "skipped_duplicate") {
            updateRow(match.rowId, { status: "duplicate", mediaId: result.mediaId });
          } else {
            updateRow(match.rowId, { status: "failed", error: result.reason || "failed" });
          }
        }
      }
    } catch (e) {
      const msg = (e as Error).message;
      setRows((prev) =>
        prev.map((r) =>
          r.status === "queued" || r.status === "uploading" || r.status === "processing"
            ? { ...r, status: "failed", error: msg }
            : r
        )
      );
    } finally {
      setBusy(false);
    }
  }, [rows, busy, galleryId, updateRow]);

  useEffect(() => {
    if (!rows.some((r) => r.status === "queued") || busy) return;
    void runUpload();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run when new queued rows appear
  }, [rows, busy]);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    queueFiles(e.dataTransfer.files);
  };

  const submitUrl = async () => {
    setUrlMsg(null);
    const source_url = urlValue.trim();
    if (!source_url) return;
    const res = await fetch("/api/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_url,
        source_kind: "web_pull",
        destination_gallery_id: galleryId ? Number.parseInt(galleryId, 10) : null,
      }),
    });
    const j = await res.json();
    if (!res.ok) {
      setUrlMsg(j.error || "queue failed");
      return;
    }
    setUrlMsg(`Job #${j.job?.id} queued — run the ingest worker to process.`);
    setUrlValue("");
  };

  const doneCount = rows.filter((r) => r.status === "done" || r.status === "duplicate").length;

  return (
    <div className="upload-panel">
      <p className="muted">
        Drop as much as you want — we handle storage, dedupe, and tagging. Uploads stay private until
        you add them to a <strong>public</strong> gallery.
      </p>

      <div className="tabs" style={{ marginBottom: "1rem" }}>
        <button type="button" className={tab === "files" ? "active" : ""} onClick={() => setTab("files")}>
          Files
        </button>
        <button type="button" className={tab === "url" ? "active" : ""} onClick={() => setTab("url")}>
          URL
        </button>
      </div>

      <label className="upload-gallery-pick">
        Add to gallery (optional)
        <select value={galleryId} onChange={(e) => setGalleryId(e.target.value)}>
          <option value="">— none —</option>
          {galleries.map((g) => (
            <option key={g.id} value={String(g.id)}>
              {g.title} ({g.item_count}){g.is_public ? "" : " · private"}
            </option>
          ))}
        </select>
        <span className="muted" style={{ fontSize: "0.8rem" }}>
          No gallery? <Link href="/g/new">Create one</Link>
        </span>
      </label>

      {tab === "files" && (
        <>
          <div
            className={`upload-dropzone${dragOver ? " drag-over" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
            }}
          >
            <div className="upload-dropzone-title">Drop files here or click to browse</div>
            <div className="muted" style={{ fontSize: "0.85rem" }}>
              Images &amp; videos · up to 20 files per batch
            </div>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept="image/*,video/*"
              hidden
              onChange={(e) => {
                if (e.target.files) queueFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>

          {rows.length > 0 && (
            <ul className="upload-queue">
              {rows.map((r) => (
                <li key={r.id} className={`upload-row status-${r.status}`}>
                  <div className="upload-row-head">
                    <span className="upload-row-name">{r.file.name}</span>
                    <span className="muted">{formatBytes(r.file.size)}</span>
                    <span className="upload-row-status">{r.status}</span>
                  </div>
                  {(r.status === "uploading" || r.status === "processing") && (
                    <div className="upload-progress">
                      <div className="upload-progress-bar" style={{ width: `${r.progress}%` }} />
                    </div>
                  )}
                  {r.mediaId && (
                    <div style={{ fontSize: "0.85rem", marginTop: "0.25rem" }}>
                      → <Link href={`/m/${r.mediaId}`}>media #{r.mediaId}</Link>
                    </div>
                  )}
                  {r.error && (
                    <div className="muted" style={{ color: "var(--danger)", fontSize: "0.8rem" }}>
                      {r.error}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}

          {doneCount > 0 && galleryId && (
            <div className="card" style={{ marginTop: "1rem" }}>
              Added to gallery.{" "}
              <Link href={`/g/${galleries.find((g) => String(g.id) === galleryId)?.slug ?? ""}`}>
                View gallery
              </Link>
            </div>
          )}
        </>
      )}

      {tab === "url" && (
        <div className="card">
          <label>
            Source URL
            <input
              type="url"
              placeholder="https://erome.com/..."
              value={urlValue}
              onChange={(e) => setUrlValue(e.target.value)}
            />
          </label>
          <button type="button" className="primary" style={{ marginTop: "0.75rem" }} onClick={() => void submitUrl()}>
            Queue URL
          </button>
          {urlMsg && <p className="muted" style={{ marginTop: "0.75rem" }}>{urlMsg}</p>}
          <p className="muted" style={{ fontSize: "0.8rem", marginTop: "0.75rem" }}>
            URL imports need <code>npm run ingest:watch</code> running locally.
          </p>
        </div>
      )}
    </div>
  );
}
