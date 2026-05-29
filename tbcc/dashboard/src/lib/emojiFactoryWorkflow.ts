/**
 * Staged workflow for split-grid Telegram custom emoji packs.
 * Mirrors tbcc/services/emoji-factory/DESIGN-WORKFLOW.md
 */

export type EmojiFactoryStageId =
  | "concept"
  | "compose"
  | "stylize"
  | "motion"
  | "export"
  | "factory"
  | "upload"
  | "iterate";

export type EmojiFactoryCheckItem = {
  id: string;
  label: string;
  hint?: string;
};

export type EmojiFactoryStage = {
  id: EmojiFactoryStageId;
  index: number;
  title: string;
  subtitle: string;
  gate: string;
  learn: string[];
  rules: string[];
  checklist: EmojiFactoryCheckItem[];
  /** Where this stage lives in TBCC (conceptual navigation). */
  inApp: string;
};

export const EMOJI_FACTORY_STAGES: EmojiFactoryStage[] = [
  {
    id: "concept",
    index: 0,
    title: "Concept & grid",
    subtitle: "Plan the wall before you animate",
    gate: "Grid size and seam map decided",
    learn: [
      "Pick cols×rows (start 4×4). Sketch which cells are hero vs glue.",
      "Mark seam lines; move them off faces and hard outlines.",
    ],
    rules: [
      "Master canvas = 512×cols by 512×rows px (e.g. 4×4 → 2048×2048).",
      "Chat displays ~100×100 per tile — design for small size, not 4K.",
    ],
    checklist: [
      { id: "grid", label: "Grid size chosen (cols × rows)" },
      { id: "seams", label: "Seam map sketched — seams in low-detail areas" },
      { id: "subject", label: "Subject fits ~80–85% of full grid with room for margins" },
    ],
    inApp: "Use the canvas calculator below; save project settings.",
  },
  {
    id: "compose",
    index: 1,
    title: "Master composition",
    subtitle: "One square comp at exact pixel size",
    gate: "Static frame looks good at 25% zoom",
    learn: [
      "Create comp at exact master dimensions @ 30 fps.",
      "Enable 8–10% safe-zone guides on every cell.",
    ],
    rules: [
      "Square master for square grids.",
      "No eyes, mouths, or logos in the outer 8–10% of each tile.",
    ],
    checklist: [
      { id: "comp", label: "Comp created at master width × height" },
      { id: "guides", label: "Per-tile safe margin guides enabled" },
      { id: "zoom", label: "Screenshot checked at 25% zoom — still readable" },
    ],
    inApp: "External NLE (After Effects, Resolve, etc.) + Design sketchbook below (saved in TBCC, never auto-cleared).",
  },
  {
    id: "stylize",
    index: 2,
    title: "Stylize for compression",
    subtitle: "Chunky art survives VP9 and small display",
    gate: "Single test tile readable at ~100 px",
    learn: [
      "Crush blacks, boost contrast, reduce fine texture.",
      "Optional slight oversharpen — Telegram softens on upload.",
    ],
    rules: [
      "Prefer outlines, cel shading, limited palette.",
      "Avoid grain, fog, soft blur, micro-detail.",
    ],
    checklist: [
      { id: "contrast", label: "High contrast grade applied" },
      { id: "detail", label: "Fine texture reduced (skin, fabric, grain)" },
      { id: "test_tile", label: "One tile exported small — still recognizable" },
    ],
    inApp: "External grade; export one test still if unsure.",
  },
  {
    id: "motion",
    index: 3,
    title: "Motion & loop",
    subtitle: "2–4 s seamless loop, simple motion",
    gate: "Loop has no pop; seams OK while playing",
    learn: [
      "Animate one focal element; keep backgrounds calm.",
      "Preview loop 10×; scrub seams during playback.",
    ],
    rules: [
      "Duration 2–4 s; 30 fps (24 OK if intentional).",
      "All tiles must share the same master timeline — never retime tiles separately.",
    ],
    checklist: [
      { id: "duration", label: "Loop length 2–4 seconds" },
      { id: "loop", label: "Loop point seamless (frame 0 ↔ end)" },
      { id: "motion", label: "Motion slow and centered in safe zones" },
      { id: "seams_play", label: "Seams checked during playback" },
    ],
    inApp: "External NLE loop preview.",
  },
  {
    id: "export",
    index: 4,
    title: "Export master MP4",
    subtitle: "Factory-ready input file",
    gate: "ffprobe shows correct size, fps, duration",
    learn: [
      "Export H.264 MP4: exact master resolution, no audio.",
      "Name with version: wall_4x4_v01.mp4",
    ],
    rules: [
      "Resolution = 512×cols × 512×rows.",
      "30 fps, 2–4 s, seamless loop baked in.",
    ],
    checklist: [
      { id: "resolution", label: "Width/height match master canvas" },
      { id: "fps", label: "Constant fps (30 recommended)" },
      { id: "audio", label: "Audio stripped" },
      { id: "ffprobe", label: "ffprobe verified (or factory prerequisites green)" },
    ],
    inApp: "Note master path in project; check prerequisites.",
  },
  {
    id: "factory",
    index: 5,
    title: "Factory split + VP9",
    subtitle: "One WebM per tile + manifest",
    gate: "All tiles play locally; manifest within size budget",
    learn: [
      "Run emoji_factory CLI on the API host (same machine as TBCC).",
      "Review manifest.json for over_soft_limit tiles.",
    ],
    rules: [
      "Default margin 8%; loop-sec 3; crf 38 — tune if files too large.",
      "Do not hand-split tiles in separate exports.",
    ],
    checklist: [
      { id: "cli", label: "python -m emoji_factory completed" },
      { id: "tiles", label: "All tiles play in a local viewer" },
      { id: "manifest", label: "manifest.json present; sizes acceptable" },
    ],
    inApp: "Copy CLI below; paste manifest path when done.",
  },
  {
    id: "upload",
    index: 6,
    title: "Upload & in-chat test",
    subtitle: "Real Telegram rendering",
    gate: "Wall reads on phone and desktop; tiles in sync",
    learn: [
      "Dry-run first, then upload. Send tiles in row-major order in a private chat.",
      "Install pack on poster account if you later use caption banners.",
    ],
    rules: [
      "Short name: lowercase, unique (script adds _by_<user_id>).",
      "Test on mobile and desktop — scaling differs slightly.",
    ],
    checklist: [
      { id: "dry_run", label: "Dry-run upload succeeded" },
      { id: "upload", label: "Pack created on Telegram" },
      { id: "chat", label: "Wall sent in grid order — seams and sync OK" },
      { id: "devices", label: "Checked on phone and desktop" },
    ],
    inApp: "Upload form on this stage; caption tools live under Misc.",
  },
  {
    id: "iterate",
    index: 7,
    title: "Iterate",
    subtitle: "One knob per revision",
    gate: "v+1 fixes the issue without regressing prior gates",
    learn: [
      "Change only one variable per version (margin, crf, loop, grade).",
      "Version files v01, v02… and note what changed.",
    ],
    rules: [
      "Seams → margin / master composition.",
      "Too soft → contrast / outlines.",
      "Too large → shorter loop, higher crf, simpler motion.",
    ],
    checklist: [
      { id: "note", label: "Revision note recorded (what changed)" },
      { id: "rerun", label: "Re-ran factory and/or upload if needed" },
      { id: "gates", label: "Re-checked failed gate only" },
    ],
    inApp: "Reset checklist items for affected stages; bump project version.",
  },
];

export const EMOJI_FACTORY_STORAGE_KEY = "tbccEmojiFactoryProgress";
export const EMOJI_PACK_VS_CAPTION_NOTE =
  "Split-grid packs (this workflow) are not the same as caption <tg-emoji> banners in Misc.";

export function masterCanvasPx(cols: number, rows: number, tilePx = 512): { w: number; h: number } {
  return { w: tilePx * cols, h: tilePx * rows };
}

export function buildFactoryCli(opts: {
  inputPath: string;
  outDir: string;
  cols: number;
  rows: number;
  marginPct?: number;
  loopSec?: number;
  crf?: number;
}): string {
  const {
    inputPath,
    outDir,
    cols,
    rows,
    marginPct = 8,
    loopSec = 3,
    crf = 38,
  } = opts;
  return [
    "cd tbcc\\services\\emoji-factory",
    "$env:PYTHONPATH = (Get-Location).Path",
    `python -m emoji_factory -i "${inputPath}" -o "${outDir}" --cols ${cols} --rows ${rows} --margin-pct ${marginPct} --loop-sec ${loopSec} --crf ${crf}`,
  ].join("\n");
}

export function stageById(id: EmojiFactoryStageId): EmojiFactoryStage | undefined {
  return EMOJI_FACTORY_STAGES.find((s) => s.id === id);
}

export function stageFromIndex(index: number): EmojiFactoryStage {
  return EMOJI_FACTORY_STAGES[Math.max(0, Math.min(EMOJI_FACTORY_STAGES.length - 1, index))]!;
}
