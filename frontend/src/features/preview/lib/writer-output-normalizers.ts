type UnknownRecord = Record<string, any>;

function asObject(value: unknown): UnknownRecord {
    return value && typeof value === "object" ? (value as UnknownRecord) : {};
}

function asString(value: unknown): string {
    if (typeof value !== "string") return "";
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : "";
}

function asStringArray(value: unknown): string[] {
    if (!Array.isArray(value)) return [];
    return value
        .map((item) => asString(item))
        .filter((item) => item.length > 0);
}

function formatPageBudget(pageBudgetRaw: unknown): string {
    const pageBudget = asObject(pageBudgetRaw);
    const min = Number(pageBudget.min);
    const max = Number(pageBudget.max);
    if (Number.isFinite(min) && Number.isFinite(max)) return `${min}-${max}p`;
    if (Number.isFinite(min)) return `${min}p+`;
    if (Number.isFinite(max)) return `~${max}p`;
    return "";
}

export interface NormalizedStoryArc {
    phase: string;
    purpose: string;
}

export interface NormalizedStoryFramework {
    concept: string;
    theme: string;
    coreConflict: string;
    structureType: string;
    format: {
        seriesType: string;
        medium: string;
        readingDirection: string;
        pageBudgetText: string;
    };
    world: {
        era: string;
        primaryLocations: string[];
        socialRules: string[];
    };
    directionPolicy: {
        panelingPolicy: string;
        eyeGuidancePolicy: string;
        pageTurnPolicy: string;
        dialoguePolicy: string;
    };
    artStylePolicy: {
        lineStyle: string;
        shadingStyle: string;
        negativeConstraints: string[];
    };
    arcOverview: NormalizedStoryArc[];
    hasContent: boolean;
}

export function normalizeStoryFrameworkContent(content: unknown): NormalizedStoryFramework {
    const data = asObject(content);
    const payload = asObject(data.story_framework);
    const hasPayload = Object.keys(payload).length > 0;

    if (hasPayload) {
        const formatPolicy = asObject(payload.format_policy);
        const worldPolicy = asObject(payload.world_policy);
        const directionPolicy = asObject(payload.direction_policy);
        const artStylePolicy = asObject(payload.art_style_policy);
        const arcRaw = Array.isArray(payload.arc_overview) ? payload.arc_overview : [];

        const arcOverview = arcRaw
            .map((step, index) => {
                const stepObject = asObject(step);
                return {
                    phase: asString(stepObject.phase) || String(index + 1),
                    purpose: asString(stepObject.purpose),
                };
            })
            .filter((step) => step.purpose.length > 0);

        const normalized: NormalizedStoryFramework = {
            concept: asString(payload.concept),
            theme: asString(payload.theme),
            coreConflict: asString(payload.core_conflict),
            structureType: asString(payload.structure_type),
            format: {
                seriesType: asString(formatPolicy.series_type),
                medium: asString(formatPolicy.medium),
                readingDirection: asString(formatPolicy.reading_direction),
                pageBudgetText: formatPageBudget(formatPolicy.page_budget),
            },
            world: {
                era: asString(worldPolicy.era),
                primaryLocations: asStringArray(worldPolicy.primary_locations),
                socialRules: asStringArray(worldPolicy.social_rules),
            },
            directionPolicy: {
                panelingPolicy: asString(directionPolicy.paneling_policy),
                eyeGuidancePolicy: asString(directionPolicy.eye_guidance_policy),
                pageTurnPolicy: asString(directionPolicy.page_turn_policy),
                dialoguePolicy: asString(directionPolicy.dialogue_policy),
            },
            artStylePolicy: {
                lineStyle: asString(artStylePolicy.line_style),
                shadingStyle: asString(artStylePolicy.shading_style),
                negativeConstraints: asStringArray(artStylePolicy.negative_constraints),
            },
            arcOverview,
            hasContent: false,
        };

        normalized.hasContent = Boolean(
            normalized.concept ||
            normalized.theme ||
            normalized.coreConflict ||
            normalized.arcOverview.length > 0
        );

        return normalized;
    }

    const constraints = asStringArray(data.constraints);
    const arcOverview = asStringArray(data.narrative_arc).map((item, index) => ({
        phase: String(index + 1),
        purpose: item,
    }));

    const normalized: NormalizedStoryFramework = {
        concept: asString(data.logline),
        theme: asString(data.tone_and_temperature),
        coreConflict: asString(data.background_context),
        structureType: "legacy",
        format: {
            seriesType: "",
            medium: "",
            readingDirection: "",
            pageBudgetText: "",
        },
        world: {
            era: asString(data.world_setting),
            primaryLocations: [],
            socialRules: [],
        },
        directionPolicy: {
            panelingPolicy: constraints.join(" / "),
            eyeGuidancePolicy: "",
            pageTurnPolicy: "",
            dialoguePolicy: "",
        },
        artStylePolicy: {
            lineStyle: "",
            shadingStyle: "",
            negativeConstraints: constraints,
        },
        arcOverview,
        hasContent: false,
    };

    normalized.hasContent = Boolean(
        normalized.concept ||
        normalized.theme ||
        normalized.coreConflict ||
        normalized.arcOverview.length > 0
    );

    return normalized;
}

export interface NormalizedComicPanel {
    panelNumber: number;
    foreground: string;
    background: string;
    composition: string;
    camera: string;
    lighting: string;
    dialogue: string[];
    negativeConstraints: string[];
}

export interface NormalizedComicPage {
    pageNumber: number;
    pageGoal: string;
    panels: NormalizedComicPanel[];
}

export interface NormalizedComicScript {
    pages: NormalizedComicPage[];
    pageCount: number;
    panelCount: number;
    hasContent: boolean;
}

export function normalizeComicScriptContent(content: unknown): NormalizedComicScript {
    const data = asObject(content);
    const pagesRaw = Array.isArray(data.pages) ? data.pages : [];

    const pages = pagesRaw.map((pageRaw, pageIndex) => {
        const page = asObject(pageRaw);
        const pageNumberValue = Number(page.page_number);
        const pageNumber = Number.isFinite(pageNumberValue) ? pageNumberValue : pageIndex + 1;
        const panelsRaw = Array.isArray(page.panels) ? page.panels : [];

        const panels = panelsRaw.map((panelRaw, panelIndex) => {
            const panel = asObject(panelRaw);
            const panelNumberValue = Number(panel.panel_number);
            const panelNumber = Number.isFinite(panelNumberValue) ? panelNumberValue : panelIndex + 1;

            return {
                panelNumber,
                foreground: asString(panel.foreground),
                background: asString(panel.background),
                composition: asString(panel.composition) || asString(panel.scene_description),
                camera: asString(panel.camera),
                lighting: asString(panel.lighting),
                dialogue: asStringArray(panel.dialogue),
                negativeConstraints: asStringArray(panel.negative_constraints),
            };
        });

        return {
            pageNumber,
            pageGoal: asString(page.page_goal),
            panels,
        };
    });

    const panelCount = pages.reduce((total, page) => total + page.panels.length, 0);
    return {
        pages,
        pageCount: pages.length,
        panelCount,
        hasContent: pages.length > 0 && panelCount > 0,
    };
}
