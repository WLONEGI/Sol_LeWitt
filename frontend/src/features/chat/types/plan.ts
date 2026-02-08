export type PlanCapability = "writer" | "visualizer" | "researcher" | "data_analyst";
export type PlanStepStatus = "pending" | "in_progress" | "completed" | "blocked";

export interface PlanStep {
    id: number | string;
    capability?: PlanCapability;
    mode?: string;
    instruction?: string;
    title?: string;
    description?: string;
    status?: PlanStepStatus;
    result_summary?: string | null;
}

export interface PlanUpdateData {
    plan: PlanStep[];
    title?: string;
    description?: string;
    ui_type?: string;
}

const CAPABILITY_LABEL: Record<PlanCapability, string> = {
    writer: "Writer",
    visualizer: "Visualizer",
    researcher: "Researcher",
    data_analyst: "Data Analyst",
};

export function normalizePlanStepStatus(raw: unknown): PlanStepStatus {
    if (raw === "pending" || raw === "in_progress" || raw === "completed" || raw === "blocked") {
        return raw;
    }
    return "pending";
}

type CapabilityLikeStep = { capability?: PlanCapability };

export function resolvePlanStepCapability(step: CapabilityLikeStep): PlanCapability | null {
    if (step.capability && step.capability in CAPABILITY_LABEL) {
        return step.capability;
    }
    return null;
}

export function getPlanStepActorLabel(step: CapabilityLikeStep): string {
    const capability = resolvePlanStepCapability(step);
    if (capability) return CAPABILITY_LABEL[capability];
    return "Worker";
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

function asPlanCapability(value: unknown): PlanCapability | undefined {
    if (value === "writer" || value === "visualizer" || value === "researcher" || value === "data_analyst") {
        return value;
    }
    return undefined;
}

export function normalizePlanStep(raw: unknown, index: number): PlanStep & { status: PlanStepStatus } {
    const fallbackId = index + 1;
    if (!isRecord(raw)) {
        return {
            id: fallbackId,
            title: `Step ${fallbackId}`,
            description: "タスク",
            instruction: "",
            status: "pending",
        };
    }

    const capability = asPlanCapability(raw.capability);
    const id = typeof raw.id === "number" || typeof raw.id === "string" ? raw.id : fallbackId;
    const title = typeof raw.title === "string" && raw.title.trim() ? raw.title.trim() : `Step ${fallbackId}`;
    const description =
        typeof raw.description === "string" && raw.description.trim()
            ? raw.description.trim()
            : title;
    const instruction =
        typeof raw.instruction === "string"
            ? raw.instruction
            : "";
    const resultSummary =
        typeof raw.result_summary === "string"
            ? raw.result_summary
            : raw.result_summary === null
                ? null
                : undefined;

    return {
        id,
        capability,
        mode: typeof raw.mode === "string" ? raw.mode : undefined,
        instruction,
        title,
        description,
        status: normalizePlanStepStatus(raw.status),
        result_summary: resultSummary,
    };
}

export function normalizePlanUpdateData(raw: unknown): PlanUpdateData {
    const fallback: PlanUpdateData = { plan: [] };
    if (!isRecord(raw)) return fallback;

    const rawPlan = Array.isArray(raw.plan) ? raw.plan : [];
    const normalizedPlan = rawPlan.map((step, index) => normalizePlanStep(step, index));

    return {
        plan: normalizedPlan,
        title: typeof raw.title === "string" ? raw.title : undefined,
        description: typeof raw.description === "string" ? raw.description : undefined,
        ui_type: typeof raw.ui_type === "string" ? raw.ui_type : undefined,
    };
}
