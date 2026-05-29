import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { CopyToClipboardButton } from "../components/CopyToClipboardButton";
import { EmojiFactoryExpress } from "../components/EmojiFactoryExpress";
import { EmojiFactoryMaker } from "../components/EmojiFactoryMaker";
import { EmojiFactorySketchbook } from "../components/EmojiFactorySketchbook";
import { InfoDisclosure } from "../components/InfoDisclosure";
import { QueryErrorBanner } from "../components/QueryErrorBanner";
import { useEmojiFactoryHashStage, useEmojiFactoryProgress } from "../hooks/useEmojiFactoryProgress";
import {
  buildFactoryCli,
  EMOJI_FACTORY_STAGES,
  masterCanvasPx,
  type EmojiFactoryStageId,
} from "../lib/emojiFactoryWorkflow";

function PrerequisitesBanner() {
  const q = useQuery({
    queryKey: ["emojiFactoryPrerequisites"],
    queryFn: () => api.emojiFactory.prerequisites(),
    refetchOnWindowFocus: true,
  });
  if (q.isLoading) return <p className="text-xs text-slate-500">Checking ffmpeg and Telegram session…</p>;
  if (q.isError)
    return (
      <QueryErrorBanner title="Prerequisites" message={(q.error as Error).message} onRetry={() => void q.refetch()} />
    );
  const d = q.data;
  if (!d) return null;
  return (
    <div className="flex flex-wrap gap-3 text-xs">
      <span className={d.ffmpeg ? "text-emerald-400" : "text-amber-400"}>
        ffmpeg: {d.ffmpeg ? "ready" : "not on PATH"}
      </span>
      <span className={d.telethon_session ? "text-emerald-400" : "text-amber-400"}>
        admin session: {d.telethon_session ? "ready" : "not logged in"}
      </span>
      {d.telethon_error ? <span className="text-slate-500 max-w-xl">{d.telethon_error}</span> : null}
    </div>
  );
}

export function EmojiFactoryPanel({ embedded = false }: { embedded?: boolean }) {
  const {
    project,
    checklist,
    setProject,
    setStageIndex,
    toggleCheck,
    resetStageChecklist,
    resetAll,
    stageProgress,
    currentStage,
  } = useEmojiFactoryProgress();

  useEmojiFactoryHashStage(setStageIndex);

  // Design canvas always uses the 512 px author tile size, regardless of Telegram upload size (100 px).
  const canvas = useMemo(
    () => masterCanvasPx(project.cols, project.rows, 512),
    [project.cols, project.rows]
  );
  const tileCount = project.cols * project.rows;

  const factoryCli = useMemo(
    () =>
      buildFactoryCli({
        inputPath: project.masterPath || "C:\\path\\wall_4x4_v01.mp4",
        outDir: project.outDir || "C:\\path\\pack-out",
        cols: project.cols,
        rows: project.rows,
        marginPct: project.marginPct,
        loopSec: project.loopSec,
        crf: project.crf,
      }),
    [project]
  );

  const [uploadResult, setUploadResult] = useState<Record<string, unknown> | null>(null);
  const [panelMode, setPanelMode] = useState<"guided" | "express">(() => {
    try {
      return window.localStorage.getItem("tbccEmojiFactoryMode") === "express" ? "express" : "guided";
    } catch {
      return "guided";
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem("tbccEmojiFactoryMode", panelMode);
    } catch {
      /* ignore */
    }
  }, [panelMode]);

  const uploadMut = useMutation({
    mutationFn: (dryRun: boolean) =>
      api.emojiFactory.uploadFromManifest({
        manifest_path: project.manifestPath.trim(),
        title: project.packTitle.trim() || "TBCC emoji pack",
        short_name: project.shortName.trim(),
        dry_run: dryRun,
      }),
    onSuccess: (data) => setUploadResult(data),
  });

  const stageChecks = checklist[currentStage.id] ?? {};
  const gateReady =
    currentStage.checklist.length > 0 &&
    currentStage.checklist.every((it) => stageChecks[it.id]);

  useEffect(() => {
    if (!project.manifestPath.trim() && project.outDir.trim()) {
      const base = project.outDir.replace(/[/\\]+$/, "");
      setProject({ manifestPath: `${base}\\manifest.json` });
    }
  }, [project.outDir, project.manifestPath, setProject]);

  return (
    <div className="max-w-5xl space-y-6">
      <header>
        {!embedded && (
          <>
            <p className="text-xs uppercase tracking-wide text-cyan-500/90 mb-1">Design → export → factory → upload</p>
            <h1 className="text-2xl font-semibold text-slate-100">Emoji pack workflow</h1>
            <p className="text-sm text-slate-400 mt-2 max-w-3xl leading-relaxed">
              Learn split-grid custom emoji packs (dimensions, timing, safe margins), or skip straight to the maker: upload
              an image/video, pick a grid (e.g. 4×4), and publish to Telegram. For caption banners using{" "}
              <code className="text-slate-300">&lt;tg-emoji&gt;</code>, use{" "}
              <Link to="/misc#caption-emoji-banners" className="text-violet-400 hover:underline">
                Misc → Caption banners
              </Link>
              .
            </p>
          </>
        )}
        <div className="mt-3">
          <PrerequisitesBanner />
        </div>
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={() => setPanelMode("guided")}
            className={`px-3 py-1.5 rounded text-sm border ${
              panelMode === "guided"
                ? "border-cyan-500 bg-cyan-950/50 text-cyan-100"
                : "border-slate-700 text-slate-400 hover:border-slate-500"
            }`}
          >
            Guided workflow
          </button>
          <button
            type="button"
            onClick={() => setPanelMode("express")}
            className={`px-3 py-1.5 rounded text-sm border ${
              panelMode === "express"
                ? "border-amber-500 bg-amber-950/40 text-amber-100"
                : "border-slate-700 text-slate-400 hover:border-slate-500"
            }`}
          >
            Express (upload & publish)
          </button>
        </div>
      </header>

      {panelMode === "express" ? (
        <div className="space-y-6">
          <EmojiFactoryExpress />
          <EmojiFactorySketchbook />
        </div>
      ) : null}

      {panelMode === "guided" ? (
      <>
      {/* Pipeline stepper — mirrors DESIGN-WORKFLOW stages */}
      <nav aria-label="Workflow stages" className="overflow-x-auto pb-1">
        <ol className="flex gap-1 min-w-max">
          {stageProgress.map(({ stage, done, total, complete }, i) => {
            const active = project.currentStageIndex === i;
            return (
              <li key={stage.id}>
                <button
                  type="button"
                  onClick={() => setStageIndex(i)}
                  className={`px-2 py-2 rounded text-left text-xs border transition-colors ${
                    active
                      ? "border-cyan-500 bg-cyan-950/50 text-cyan-100"
                      : complete
                        ? "border-emerald-800/60 bg-emerald-950/20 text-emerald-200 hover:border-emerald-600"
                        : "border-slate-700 bg-slate-800/40 text-slate-400 hover:border-slate-500"
                  }`}
                  title={stage.gate}
                >
                  <span className="block font-medium">{stage.index}. {stage.title}</span>
                  <span className="block text-[10px] opacity-80 mt-0.5">
                    {done}/{total}
                    {complete ? " ✓" : ""}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </nav>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Stage detail + checklist */}
        <div className="lg:col-span-2 space-y-4">
          <section className="rounded-lg border border-slate-700 bg-slate-800/40 p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="text-lg font-medium text-slate-100">
                  Stage {currentStage.index}: {currentStage.title}
                </h2>
                <p className="text-sm text-slate-400">{currentStage.subtitle}</p>
              </div>
              <span
                className={`text-xs px-2 py-1 rounded shrink-0 ${
                  gateReady ? "bg-emerald-900/50 text-emerald-300" : "bg-slate-700 text-slate-400"
                }`}
              >
                Gate: {gateReady ? "ready" : "in progress"}
              </span>
            </div>
            <p className="text-xs text-cyan-200/80 mt-2">
              <strong className="text-cyan-300">Pass gate:</strong> {currentStage.gate}
            </p>
            <p className="text-xs text-slate-500 mt-1">{currentStage.inApp}</p>

            <ul className="mt-4 space-y-2">
              {currentStage.learn.map((line) => (
                <li key={line} className="text-sm text-slate-300 flex gap-2">
                  <span className="text-cyan-500 shrink-0">→</span>
                  {line}
                </li>
              ))}
            </ul>

            <InfoDisclosure title="Rules for this stage" className="mt-4">
              <ul className="list-disc pl-4 space-y-1">
                {currentStage.rules.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </InfoDisclosure>
          </section>

          <section className="rounded-lg border border-slate-600 bg-slate-900/50 p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-slate-200">Checklist</h3>
              <button
                type="button"
                className="text-xs text-slate-500 hover:text-slate-300"
                onClick={() => resetStageChecklist(currentStage.id)}
              >
                Reset stage
              </button>
            </div>
            <ul className="space-y-2">
              {currentStage.checklist.map((item) => (
                <li key={item.id}>
                  <label className="flex gap-2 items-start cursor-pointer text-sm text-slate-300">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={Boolean(stageChecks[item.id])}
                      onChange={() => toggleCheck(currentStage.id, item.id)}
                    />
                    <span>
                      {item.label}
                      {item.hint ? <span className="block text-xs text-slate-500 mt-0.5">{item.hint}</span> : null}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </section>

          <StageTools
            stageId={currentStage.id}
            project={project}
            setProject={setProject}
            canvas={canvas}
            tileCount={tileCount}
            factoryCli={factoryCli}
            uploadMut={uploadMut}
            uploadResult={uploadResult}
          />

          <div className="flex gap-2">
            <button
              type="button"
              disabled={project.currentStageIndex <= 0}
              onClick={() => setStageIndex(project.currentStageIndex - 1)}
              className="px-3 py-2 rounded bg-slate-700 text-white text-sm disabled:opacity-40"
            >
              ← Previous stage
            </button>
            <button
              type="button"
              disabled={project.currentStageIndex >= EMOJI_FACTORY_STAGES.length - 1}
              onClick={() => setStageIndex(project.currentStageIndex + 1)}
              className="px-3 py-2 rounded bg-cyan-700 hover:bg-cyan-600 text-white text-sm disabled:opacity-40"
            >
              Next stage →
            </button>
          </div>
        </div>

        {/* Project sidebar — persists across stages */}
        <aside className="space-y-4">
          <section className="rounded-lg border border-slate-700 p-4 bg-slate-800/30">
            <h3 className="text-sm font-medium text-slate-200 mb-3">Project</h3>
            <label className="block text-xs text-slate-500 mb-1">Version label</label>
            <input
              className="w-full mb-3 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm"
              value={project.version}
              onChange={(e) => setProject({ version: e.target.value })}
            />
            <div className="grid grid-cols-2 gap-2 mb-3">
              <div>
                <label className="text-xs text-slate-500">Cols</label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm"
                  value={project.cols}
                  onChange={(e) => setProject({ cols: Math.max(1, Number(e.target.value) || 4) })}
                />
              </div>
              <div>
                <label className="text-xs text-slate-500">Rows</label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm"
                  value={project.rows}
                  onChange={(e) => setProject({ rows: Math.max(1, Number(e.target.value) || 4) })}
                />
              </div>
            </div>
            <p className="text-xs text-cyan-300/90 mb-3">
              Master canvas: <strong>{canvas.w}×{canvas.h}</strong> px · {tileCount} tiles @ {project.tilePx}px
            </p>
            <label className="block text-xs text-slate-500 mb-1">Master MP4 path</label>
            <input
              className="w-full mb-2 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-xs font-mono"
              placeholder="C:\path\wall_4x4_v01.mp4"
              value={project.masterPath}
              onChange={(e) => setProject({ masterPath: e.target.value })}
            />
            <label className="block text-xs text-slate-500 mb-1">Factory output dir</label>
            <input
              className="w-full mb-2 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-xs font-mono"
              placeholder="C:\path\pack-out"
              value={project.outDir}
              onChange={(e) => setProject({ outDir: e.target.value })}
            />
            <label className="block text-xs text-slate-500 mb-1">manifest.json path</label>
            <input
              className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1 text-xs font-mono"
              placeholder="C:\path\pack-out\manifest.json"
              value={project.manifestPath}
              onChange={(e) => setProject({ manifestPath: e.target.value })}
            />
          </section>

          <section className="rounded-lg border border-slate-700 p-4 text-xs text-slate-500 space-y-2">
            <p className="text-slate-400 font-medium text-sm">Overall progress</p>
            {stageProgress.map(({ stage, done, total }) => (
              <div key={stage.id} className="flex justify-between gap-2">
                <button
                  type="button"
                  className="text-left text-cyan-400/90 hover:underline truncate"
                  onClick={() => setStageIndex(stage.index)}
                >
                  {stage.index}. {stage.title}
                </button>
                <span>
                  {done}/{total}
                </span>
              </div>
            ))}
            <button type="button" onClick={resetAll} className="text-rose-400/80 hover:text-rose-300 mt-2">
              Reset all progress
            </button>
          </section>

          <InfoDisclosure title="Format cheat sheet">
            <ul className="list-disc pl-4 space-y-1">
              <li>Edit: MP4 master (H.264, no audio)</li>
              <li>Deliver: WebM VP9 per tile (factory)</li>
              <li>Loop: 2–4 s @ 30 fps</li>
              <li>Margin: 8–10% per tile safe zone</li>
              <li>Avoid GIF as source of truth</li>
            </ul>
          </InfoDisclosure>
        </aside>
      </div>
      </>
      ) : null}
    </div>
  );
}

function StageTools({
  stageId,
  project,
  setProject,
  canvas,
  tileCount,
  factoryCli,
  uploadMut,
  uploadResult,
}: {
  stageId: EmojiFactoryStageId;
  project: ReturnType<typeof useEmojiFactoryProgress>["project"];
  setProject: ReturnType<typeof useEmojiFactoryProgress>["setProject"];
  canvas: { w: number; h: number };
  tileCount: number;
  factoryCli: string;
  uploadMut: ReturnType<typeof useMutation<Record<string, unknown>, Error, boolean>>;
  uploadResult: Record<string, unknown> | null;
}) {
  if (stageId === "compose") {
    return <EmojiFactorySketchbook />;
  }

  if (stageId === "concept") {
    return (
      <section className="rounded-lg border border-cyan-900/40 bg-cyan-950/20 p-4 text-sm text-slate-300">
        <h3 className="font-medium text-cyan-100 mb-2">Canvas calculator</h3>
        <p>
          Your grid produces <strong className="text-white">{tileCount}</strong> tiles. Export your master at{" "}
          <strong className="text-white">
            {canvas.w}×{canvas.h}
          </strong>{" "}
          pixels before splitting.
        </p>
        <p className="text-xs text-slate-500 mt-2">
          Tip: 4×4 is the most common “emoji wall” size; try 2×2 first while learning margins.
        </p>
      </section>
    );
  }

  if (stageId === "export") {
    return (
      <section className="rounded-lg border border-slate-700 p-4 text-sm">
        <h3 className="font-medium text-slate-200 mb-2">Export verification</h3>
        <p className="text-slate-400 text-xs mb-2">On the API host (where TBCC runs):</p>
        <pre className="text-xs bg-slate-900 p-2 rounded overflow-x-auto text-slate-300">
          {`ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate,duration -of csv=p=0 "${project.masterPath || "your_master.mp4"}"`}
        </pre>
        <p className="text-xs text-slate-500 mt-2">
          Expect width={canvas.w}, height={canvas.h}, duration 2–4 s, ~30 fps.
        </p>
      </section>
    );
  }

  if (stageId === "factory") {
    return (
      <div className="space-y-4">
        <EmojiFactoryMaker variant="guided" />
      <section className="rounded-lg border border-slate-700 p-4 space-y-3">
        <h3 className="font-medium text-slate-200">Factory CLI (optional)</h3>
        <p className="text-xs text-slate-500">Power users: run on the TBCC server if you already have a master MP4 path.</p>
        <div className="grid grid-cols-3 gap-2 text-sm">
          <label className="text-xs text-slate-500">
            margin %
            <input
              type="number"
              className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1 mt-1"
              value={project.marginPct}
              onChange={(e) => setProject({ marginPct: Number(e.target.value) || 8 })}
            />
          </label>
          <label className="text-xs text-slate-500">
            loop sec
            <input
              type="number"
              step={0.5}
              className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1 mt-1"
              value={project.loopSec}
              onChange={(e) => setProject({ loopSec: Number(e.target.value) || 3 })}
            />
          </label>
          <label className="text-xs text-slate-500">
            crf
            <input
              type="number"
              className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1 mt-1"
              value={project.crf}
              onChange={(e) => setProject({ crf: Number(e.target.value) || 38 })}
            />
          </label>
        </div>
        <pre className="text-xs bg-slate-900 p-3 rounded overflow-x-auto text-slate-300 whitespace-pre-wrap">
          {factoryCli}
        </pre>
        <CopyToClipboardButton text={factoryCli} label="Copy CLI" />
      </section>
      </div>
    );
  }

  if (stageId === "upload") {
    return (
      <section className="rounded-lg border border-slate-700 p-4 space-y-3">
        <h3 className="font-medium text-slate-200">Publish pack</h3>
        <p className="text-xs text-slate-500">
          If you used the file uploader in the Factory stage, the manifest is already set. Otherwise paste the server
          path to <code className="text-slate-400">manifest.json</code> below.
        </p>
        <label className="block text-xs text-slate-500">
          Pack title
          <input
            className="w-full mt-1 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm"
            value={project.packTitle}
            onChange={(e) => setProject({ packTitle: e.target.value })}
          />
        </label>
        <label className="block text-xs text-slate-500">
          Short name (base)
          <input
            className="w-full mt-1 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm font-mono"
            placeholder="my_wall_v01"
            value={project.shortName}
            onChange={(e) => setProject({ shortName: e.target.value })}
          />
        </label>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!project.manifestPath.trim() || !project.shortName.trim() || uploadMut.isPending}
            onClick={() => uploadMut.mutate(true)}
            className="px-3 py-2 rounded bg-slate-700 text-white text-sm"
          >
            {uploadMut.isPending ? "…" : "Dry-run upload"}
          </button>
          <button
            type="button"
            disabled={!project.manifestPath.trim() || !project.shortName.trim() || uploadMut.isPending}
            onClick={() => uploadMut.mutate(false)}
            className="px-3 py-2 rounded bg-cyan-700 hover:bg-cyan-600 text-white text-sm"
          >
            {uploadMut.isPending ? "…" : "Create pack on Telegram"}
          </button>
        </div>
        {uploadMut.isError ? (
          <QueryErrorBanner
            title="Upload failed"
            message={(uploadMut.error as Error).message}
            onRetry={() => uploadMut.reset()}
          />
        ) : null}
        {uploadResult ? (
          <pre className="text-xs bg-slate-900 p-2 rounded text-emerald-300 overflow-x-auto">
            {JSON.stringify(uploadResult, null, 2)}
          </pre>
        ) : null}
        <p className="text-xs text-slate-500">
          After upload: send tiles in row order in a private chat. For caption banners, install the pack on the poster
          account and use{" "}
          <Link to="/misc#caption-emoji-banners" className="text-violet-400 hover:underline">
            Misc → Caption banners
          </Link>
          .
        </p>
      </section>
    );
  }

  if (stageId === "iterate") {
    return (
      <section className="rounded-lg border border-amber-900/40 bg-amber-950/20 p-4 text-sm text-slate-300">
        <h3 className="font-medium text-amber-100 mb-2">Revision discipline</h3>
        <ul className="list-disc pl-4 space-y-1 text-xs">
          <li>Seams visible → margin in master or higher --margin-pct</li>
          <li>Too soft → contrast / outlines in grade</li>
          <li>Files too large → shorter loop, higher crf, simpler motion</li>
          <li>Out of sync → re-export one master MP4; never retime tiles alone</li>
        </ul>
        <button
          type="button"
          className="mt-3 text-xs text-cyan-400 hover:underline"
          onClick={() => {
            const v = project.version.replace(/(\d+)$/, (_, n) => String(Number(n) + 1).padStart(2, "0"));
            setProject({ version: v.includes("v") ? v : `${project.version}_v02` });
          }}
        >
          Bump version label in sidebar
        </button>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-slate-800 p-4 text-xs text-slate-500">
      Work in your NLE for this stage. Use the checklist above; advance when the gate passes.
    </section>
  );
}
