import { useCallback, useEffect, useMemo, useState } from "react";
import {
  EMOJI_FACTORY_STORAGE_KEY,
  type EmojiFactoryStageId,
  EMOJI_FACTORY_STAGES,
} from "../lib/emojiFactoryWorkflow";

export type EmojiFactoryProject = {
  version: string;
  cols: number;
  rows: number;
  tilePx: number;
  marginPct: number;
  loopSec: number;
  crf: number;
  masterPath: string;
  outDir: string;
  manifestPath: string;
  packTitle: string;
  shortName: string;
  currentStageIndex: number;
};

type StoredProgress = {
  project: EmojiFactoryProject;
  checklist: Record<EmojiFactoryStageId, Record<string, boolean>>;
};

const DEFAULT_PROJECT: EmojiFactoryProject = {
  version: "v01",
  cols: 4,
  rows: 4,
  tilePx: 100,
  marginPct: 8,
  loopSec: 3,
  crf: 44,
  masterPath: "",
  outDir: "",
  manifestPath: "",
  packTitle: "TBCC emoji pack",
  shortName: "",
  currentStageIndex: 0,
};

function emptyChecklist(): StoredProgress["checklist"] {
  const out = {} as StoredProgress["checklist"];
  for (const stage of EMOJI_FACTORY_STAGES) {
    out[stage.id] = {};
  }
  return out;
}

function loadStored(): StoredProgress {
  try {
    const raw = window.localStorage.getItem(EMOJI_FACTORY_STORAGE_KEY);
    if (!raw) return { project: { ...DEFAULT_PROJECT }, checklist: emptyChecklist() };
    const parsed = JSON.parse(raw) as Partial<StoredProgress>;
    return {
      project: { ...DEFAULT_PROJECT, ...parsed.project },
      checklist: { ...emptyChecklist(), ...parsed.checklist },
    };
  } catch {
    return { project: { ...DEFAULT_PROJECT }, checklist: emptyChecklist() };
  }
}

function saveStored(data: StoredProgress) {
  try {
    window.localStorage.setItem(EMOJI_FACTORY_STORAGE_KEY, JSON.stringify(data));
  } catch {
    // ignore
  }
}

export function useEmojiFactoryProgress() {
  const [data, setData] = useState<StoredProgress>(loadStored);

  useEffect(() => {
    saveStored(data);
  }, [data]);

  const setProject = useCallback((patch: Partial<EmojiFactoryProject>) => {
    setData((prev) => ({ ...prev, project: { ...prev.project, ...patch } }));
  }, []);

  const setStageIndex = useCallback((index: number) => {
    const clamped = Math.max(0, Math.min(EMOJI_FACTORY_STAGES.length - 1, index));
    setProject({ currentStageIndex: clamped });
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", `#stage-${clamped}`);
    }
  }, [setProject]);

  const toggleCheck = useCallback((stageId: EmojiFactoryStageId, itemId: string) => {
    setData((prev) => {
      const stage = { ...prev.checklist[stageId] };
      stage[itemId] = !stage[itemId];
      return { ...prev, checklist: { ...prev.checklist, [stageId]: stage } };
    });
  }, []);

  const resetStageChecklist = useCallback((stageId: EmojiFactoryStageId) => {
    setData((prev) => ({
      ...prev,
      checklist: { ...prev.checklist, [stageId]: {} },
    }));
  }, []);

  const resetAll = useCallback(() => {
    setData({ project: { ...DEFAULT_PROJECT }, checklist: emptyChecklist() });
  }, []);

  const stageProgress = useMemo(() => {
    return EMOJI_FACTORY_STAGES.map((stage) => {
      const items = stage.checklist;
      const done = items.filter((it) => data.checklist[stage.id]?.[it.id]).length;
      return { stage, done, total: items.length, complete: done === items.length && items.length > 0 };
    });
  }, [data.checklist]);

  const currentStage = EMOJI_FACTORY_STAGES[data.project.currentStageIndex] ?? EMOJI_FACTORY_STAGES[0];

  return {
    project: data.project,
    checklist: data.checklist,
    setProject,
    setStageIndex,
    toggleCheck,
    resetStageChecklist,
    resetAll,
    stageProgress,
    currentStage,
  };
}

/** Sync stage from URL hash #stage-N on mount. */
export function useEmojiFactoryHashStage(setStageIndex: (n: number) => void) {
  useEffect(() => {
    const hash = window.location.hash;
    const m = /^#stage-(\d+)$/.exec(hash);
    if (m) {
      const n = Number(m[1]);
      if (!Number.isNaN(n)) setStageIndex(n);
    }
  }, [setStageIndex]);
}
