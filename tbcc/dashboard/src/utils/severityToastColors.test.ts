import { describe, expect, it } from "vitest";
import {
  calmToastStyle,
  classifyOpsAlertKind,
  severityGradeEmoji,
  severityHealthRatio,
} from "./severityToastColors";

describe("severityToastColors", () => {
  it("maps success toward green and critical toward warm red", () => {
    expect(severityHealthRatio("success")).toBeGreaterThan(severityHealthRatio("critical"));
    const ok = calmToastStyle("success");
    const bad = calmToastStyle("critical");
    expect(ok.accentBorder).toMatch(/hsla\(/);
    expect(bad.accentBorder).toMatch(/hsla\(/);
    expect(ok.backgroundColor).toContain("tbcc-bg-surface");
  });

  it("grades emoji by chip ratio", () => {
    expect(severityGradeEmoji(0.9)).toBe("🟢");
    expect(severityGradeEmoji(0.55)).toBe("🟡");
    expect(severityGradeEmoji(0.3)).toBe("🟠");
    expect(severityGradeEmoji(0.05)).toBe("🟤");
  });

  it("classifies ops alerts", () => {
    expect(classifyOpsAlertKind({ code: "payment" })).toBe("payment");
    expect(classifyOpsAlertKind({ severity: "critical" })).toBe("critical");
    expect(classifyOpsAlertKind({ severity: "warning" })).toBe("warning");
  });
});
