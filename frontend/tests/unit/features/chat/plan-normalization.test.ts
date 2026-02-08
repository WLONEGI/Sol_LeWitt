import { describe, expect, it } from "vitest";
import { normalizePlanStep, normalizePlanUpdateData } from "@/features/chat/types/plan";

describe("plan normalization", () => {
  it("accepts canonical capability step", () => {
    const step = normalizePlanStep(
      {
        id: 7,
        capability: "writer",
        instruction: "outline",
        title: "Legacy",
        status: "in_progress",
      },
      0
    );

    expect(step.id).toBe(7);
    expect(step.capability).toBe("writer");
    expect(step.status).toBe("in_progress");
    expect(step.title).toBe("Legacy");
    expect(step.instruction).toBe("outline");
  });

  it("normalizes invalid status to pending", () => {
    const data = normalizePlanUpdateData({
      plan: [{ id: 1, capability: "visualizer", status: "running" }],
    });

    expect(data.plan).toHaveLength(1);
    expect(data.plan[0].status).toBe("pending");
  });

  it("returns safe empty structure for invalid payload", () => {
    const data = normalizePlanUpdateData(null);
    expect(data).toEqual({ plan: [] });
  });
});
