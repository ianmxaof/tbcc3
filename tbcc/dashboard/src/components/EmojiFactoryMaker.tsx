import { useMutation, useQuery } from "@tanstack/react-query";
import { useCallback, useId, useState } from "react";
import { api } from "../api";
import { useEmojiFactoryProgress } from "../hooks/useEmojiFactoryProgress";
import { shortNameLooksValidBase, slugShortNameBase } from "../lib/telegramShortName";
import { QueryErrorBanner } from "./QueryErrorBanner";

const GRID_PRESETS = [
  { label: "2×2", cols: 2, rows: 2 },
  { label: "3×3", cols: 3, rows: 3 },
  { label: "4×4", cols: 4, rows: 4 },
  { label: "5×5", cols: 5, rows: 5 },
] as const;

const ACCEPT = "image/png,image/jpeg,image/webp,image/gif,video/mp4,video/webm,video/quicktime,.gif,.png,.jpg,.jpeg,.webp,.mp4,.mov,.webm";

type Props = {
  variant?: "express" | "guided";
};

export function EmojiFactoryMaker({ variant = "express" }: Props) {
  const fileInputId = useId();
  const { project, setProject } = useEmojiFactoryProgress();
  const [file, setFile] = useState<File | null>(null);
  const [staticPack, setStaticPack] = useState(false);
  const [status, setStatus] = useState("");

  const prereqQ = useQuery({
    queryKey: ["emojiFactoryPrerequisites"],
    queryFn: () => api.emojiFactory.prerequisites(),
  });

  const tileCount = project.cols * project.rows;
  const onPickFile = useCallback(
    (f: File | null) => {
      setFile(f);
      if (f) {
        const base = slugShortNameBase(f.name.replace(/\.[^.]+$/, ""));
        const patch: { shortName: string; packTitle?: string } = { shortName: base };
        if (project.packTitle === "TBCC emoji pack") {
          patch.packTitle = base.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
        }
        setProject(patch);
      }
    },
    [project.packTitle, setProject]
  );

  const shortNameOk = shortNameLooksValidBase(project.shortName);

  const publishOnlyMut = useMutation({
    mutationFn: (dryRun: boolean) =>
      api.emojiFactory.uploadFromManifest({
        manifest_path: project.manifestPath.trim(),
        title: project.packTitle.trim() || "TBCC emoji pack",
        short_name: project.shortName.trim(),
        dry_run: dryRun,
      }),
    onSuccess: (data, dryRun) => {
      const up = data as { short_name?: string; install_hint?: string };
      setStatus(
        dryRun
          ? `Dry-run OK — pack ${up.short_name ?? "?"}`
          : `Pack created: ${up.short_name ?? "?"}. ${up.install_hint ?? "Open Settings → My Profile → Emoji."}`
      );
    },
    onError: (e) => setStatus(String(e)),
  });

  const createMut = useMutation({
    mutationFn: (opts: { uploadTelegram: boolean; dryRun: boolean }) => {
      if (!file) throw new Error("Choose an image or video file first.");
      return api.emojiFactory.createFromUpload(file, {
        cols: project.cols,
        rows: project.rows,
        tile_px: project.tilePx,
        margin_pct: project.marginPct,
        loop_sec: project.loopSec,
        crf: project.crf,
        static: staticPack,
        title: project.packTitle.trim() || "TBCC emoji pack",
        short_name: project.shortName.trim(),
        upload_telegram: opts.uploadTelegram,
        dry_run: opts.dryRun,
      });
    },
    onSuccess: (data, vars) => {
      const split = data.split as {
        manifest_path?: string;
        out_dir?: string;
        tile_count?: number;
        over_soft_limit?: number;
        suggested_short_name?: string;
      };
      if (split.manifest_path) {
        setProject({ manifestPath: split.manifest_path });
      }
      if (split.out_dir) setProject({ outDir: split.out_dir });
      if (split.suggested_short_name && !project.shortName.trim()) {
        setProject({ shortName: split.suggested_short_name });
      }
      const over = split.over_soft_limit ?? 0;
      const tiles = split.tile_count ?? 0;
      let msg = `Split complete — ${tiles} tile(s).`;
      if (over > 0) msg += ` ${over} tile(s) over 256 KB soft limit (try higher CRF or shorter loop).`;
      if (vars.uploadTelegram && data.upload) {
        const up = data.upload as { short_name?: string; install_hint?: string; saved_messages_preview_id?: number };
        if (vars.dryRun) {
          msg += ` Dry-run OK — pack would be named ${up.short_name ?? "?"}.`;
        } else {
          msg += ` Done! Check Saved Messages for your grid preview. ${up.install_hint ?? "Tap any emoji → Add emoji."}`;
        }
      }
      setStatus(msg);
    },
    onError: (e) => setStatus(String(e)),
  });

  const ready = Boolean(file) && prereqQ.data?.ffmpeg;
  const canTelegram =
    ready && Boolean(project.shortName.trim()) && shortNameOk && prereqQ.data?.telethon_session;
  const canPublishOnly =
    Boolean(project.manifestPath.trim()) &&
    Boolean(project.shortName.trim()) &&
    shortNameOk &&
    prereqQ.data?.telethon_session;

  const border =
    variant === "express" ? "border-amber-800/50 bg-amber-950/20" : "border-cyan-900/40 bg-cyan-950/15";

  return (
    <section className={`rounded-lg border p-4 space-y-4 ${border}`}>
      <div>
        <h2 className="text-lg font-medium text-slate-100">
          {variant === "express" ? "Emoji maker" : "Build from your file"}
        </h2>
        <p className="text-sm text-slate-400 mt-1 max-w-3xl leading-relaxed">
          Upload one image or short video from your computer. TBCC splits it into a grid and encodes Telegram custom
          emoji tiles (VP9 WebM). Animated clips use up to <strong className="text-slate-200">3 seconds</strong> per
          tile; static packs use a single frame per cell.
        </p>
      </div>

      <div className="rounded-lg border border-sky-900/50 bg-sky-950/30 p-3 text-sm text-sky-100/90 space-y-2">
        <p className="font-medium text-sky-200">What you get in Telegram</p>
        <ul className="list-disc pl-4 text-xs text-sky-100/80 space-y-1">
          <li>
            One message in <strong>Saved Messages</strong> showing your full emoji grid (like emoji-bot packs).
          </li>
          <li>
            <strong>Tap any emoji</strong> in that message → <strong>Add emoji</strong> to install the whole pack.
          </li>
          <li>
            You will <strong>not</strong> get a pile of loose <code className="text-sky-200">.webm</code> files anymore
            (older runs may have — safe to delete those).
          </li>
        </ul>
      </div>

      {prereqQ.data ? (
        <p className="text-xs flex flex-wrap gap-3">
          <span className={prereqQ.data.ffmpeg ? "text-emerald-400" : "text-amber-400"}>
            ffmpeg: {prereqQ.data.ffmpeg ? "ready" : "install ffmpeg on the TBCC host"}
          </span>
          <span className={prereqQ.data.telethon_session ? "text-emerald-400" : "text-amber-400"}>
            Telegram: {prereqQ.data.telethon_session ? "session ready" : "log in admin.session for publish"}
          </span>
        </p>
      ) : null}

      <div className="rounded-lg border border-dashed border-slate-600 bg-slate-900/40 p-4">
        <label htmlFor={fileInputId} className="block cursor-pointer">
          <span className="text-sm font-medium text-cyan-200">Choose image or video</span>
          <span className="block text-xs text-slate-500 mt-1">PNG, JPG, WebP, GIF, MP4, MOV, WebM — max 80 MB</span>
          <input
            id={fileInputId}
            type="file"
            accept={ACCEPT}
            className="mt-3 block w-full text-sm text-slate-400 file:mr-3 file:py-2 file:px-3 file:rounded file:border-0 file:bg-cyan-800 file:text-white hover:file:bg-cyan-700"
            onChange={(e) => onPickFile(e.target.files?.[0] ?? null)}
          />
        </label>
        {file ? (
          <p className="text-xs text-slate-400 mt-2">
            Selected: <span className="text-slate-200">{file.name}</span> ({(file.size / (1024 * 1024)).toFixed(2)} MB)
          </p>
        ) : null}
      </div>

      <div>
        <p className="text-xs text-slate-500 mb-2">Grid split (like 4×4 emoji bots)</p>
        <div className="flex flex-wrap gap-2">
          {GRID_PRESETS.map((p) => {
            const active = project.cols === p.cols && project.rows === p.rows;
            return (
              <button
                key={p.label}
                type="button"
                onClick={() => setProject({ cols: p.cols, rows: p.rows })}
                className={`px-3 py-1.5 rounded text-sm border ${
                  active
                    ? "border-cyan-500 bg-cyan-950/60 text-cyan-100"
                    : "border-slate-600 text-slate-400 hover:border-slate-500"
                }`}
              >
                {p.label} ({p.cols * p.rows} emojis)
              </button>
            );
          })}
        </div>
        <p className="text-xs text-slate-500 mt-2">
          Design canvas: {project.cols * 512}×{project.rows * 512}px · Telegram tiles: {tileCount}×{" "}
          {project.tilePx}×{project.tilePx}px (must be 100×100)
        </p>
      </div>

      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-2 text-slate-300 cursor-pointer">
          <input
            type="radio"
            name={`pack-type-${variant}`}
            checked={!staticPack}
            onChange={() => setStaticPack(false)}
          />
          Animated (loop)
        </label>
        <label className="flex items-center gap-2 text-slate-300 cursor-pointer">
          <input
            type="radio"
            name={`pack-type-${variant}`}
            checked={staticPack}
            onChange={() => setStaticPack(true)}
          />
          Static (one frame per tile)
        </label>
      </div>

      <div className="grid md:grid-cols-2 gap-3 text-sm">
        <label className="text-xs text-slate-500 block">
          Loop length (animated only, max 3s)
          <input
            type="range"
            min={0.5}
            max={3}
            step={0.5}
            disabled={staticPack}
            className="w-full mt-1 disabled:opacity-40"
            value={project.loopSec}
            onChange={(e) => setProject({ loopSec: Number(e.target.value) })}
          />
          <span className="text-slate-300">{staticPack ? "—" : `${project.loopSec}s`}</span>
        </label>
        <label className="text-xs text-slate-500 block md:col-span-2">
          Pack name <span className="text-slate-600">(shown in Telegram, e.g. Five Point Haircut)</span>
          <input
            className="w-full mt-1 bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm"
            placeholder="Five Point Haircut"
            value={project.packTitle}
            onChange={(e) => {
              const t = e.target.value;
              setProject({
                packTitle: t,
                shortName: slugShortNameBase(t || "pack"),
              });
            }}
          />
        </label>
        <details className="text-xs text-slate-500 md:col-span-2">
          <summary className="cursor-pointer text-slate-400">Technical pack ID (optional)</summary>
          <label className="block mt-2">
            Used in Telegram links; auto-filled from pack name. Must start with a letter.
            <input
              className="w-full mt-1 bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm font-mono"
              placeholder="fivepointhaircut"
              value={project.shortName}
              onChange={(e) => setProject({ shortName: e.target.value })}
              onBlur={(e) => {
                const fixed = slugShortNameBase(e.target.value);
                if (fixed !== e.target.value.trim()) setProject({ shortName: fixed });
              }}
            />
          </label>
          {!shortNameOk && project.shortName.trim() ? (
            <span className="text-amber-400 mt-1 block">Must begin with a letter.</span>
          ) : null}
        </details>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!canTelegram || createMut.isPending}
          onClick={() => createMut.mutate({ uploadTelegram: true, dryRun: false })}
          className="px-5 py-2.5 rounded bg-cyan-700 hover:bg-cyan-600 text-white text-sm font-medium disabled:opacity-40"
          title={!prereqQ.data?.telethon_session ? "Requires admin Telethon session" : undefined}
        >
          {createMut.isPending ? "Working…" : "Create emoji pack → Saved Messages"}
        </button>
        {canPublishOnly ? (
          <button
            type="button"
            disabled={publishOnlyMut.isPending || createMut.isPending}
            onClick={() => publishOnlyMut.mutate(false)}
            className="px-3 py-2 rounded border border-emerald-700 text-emerald-200 text-sm hover:bg-emerald-950/40 disabled:opacity-40"
            title="Re-publish tiles already on disk (no re-split)"
          >
            {publishOnlyMut.isPending ? "Publishing…" : "Retry publish only"}
          </button>
        ) : null}
      </div>

      {publishOnlyMut.isError ? (
        <QueryErrorBanner
          title="Publish failed"
          message={(publishOnlyMut.error as Error).message}
          onRetry={() => publishOnlyMut.reset()}
        />
      ) : null}

      {createMut.isError ? (
        <QueryErrorBanner
          title="Emoji pack failed"
          message={(createMut.error as Error).message}
          onRetry={() => createMut.reset()}
        />
      ) : null}

      {status ? <p className="text-sm text-emerald-300/90">{status}</p> : null}

      {createMut.isSuccess && createMut.data ? (
        <details className="text-xs">
          <summary className="cursor-pointer text-slate-400">Technical details</summary>
          <pre className="mt-2 bg-slate-900 p-2 rounded text-slate-300 overflow-x-auto">
            {JSON.stringify(createMut.data, null, 2)}
          </pre>
        </details>
      ) : null}

      <details className="text-xs text-slate-500">
        <summary className="cursor-pointer text-slate-400">Advanced / API-host paths (optional)</summary>
        <p className="mt-2 mb-2">
          Only needed if you already rendered a master MP4 on the same machine as TBCC. Browser upload above is the
          normal path.
        </p>
        <div className="grid md:grid-cols-2 gap-2">
          <label className="block">
            Master file on TBCC server
            <input
              className="w-full mt-1 bg-slate-900 border border-slate-600 rounded px-2 py-1 font-mono"
              value={project.masterPath}
              onChange={(e) => setProject({ masterPath: e.target.value })}
              placeholder="C:\path\master.mp4"
            />
          </label>
          <label className="block">
            Output folder on TBCC server
            <input
              className="w-full mt-1 bg-slate-900 border border-slate-600 rounded px-2 py-1 font-mono"
              value={project.outDir}
              onChange={(e) => setProject({ outDir: e.target.value })}
              placeholder="C:\path\pack-out"
            />
          </label>
        </div>
      </details>
    </section>
  );
}
