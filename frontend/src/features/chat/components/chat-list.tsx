import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatItem } from "./chat-item";
import { TaskAccordion } from "./task-accordion";
import { ArtifactButton } from "./artifact-button";
import { WorkerResult } from "./worker-result";
import { ResearchTaskCard } from "./message/research-task-card";
import { ArtifactPreview } from "./artifact-preview";
import { CodeExecutionBlock } from "./code-execution-block";
import { SlideOutline } from "./slide-outline";
import { CharacterSheetSummary } from "./character-sheet-summary";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { useArtifactStore } from "@/features/preview/stores/artifact";
import { ArrowRight, CheckCircle2, ChevronDown, ChevronUp, Circle, Loader2, MessageSquare } from "lucide-react";
import { TimelineEvent } from "../types/timeline";
import type { PlanStepStatus, PlanUpdateData } from "../types/plan";
import { normalizePlanStepStatus, normalizePlanUpdateData } from "../types/plan";
import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import {
    CHARACTER_SHEET_BUNDLE_ARTIFACT_ID,
    inferVisualizerModeFromPayload,
    normalizeCharacterSheetBundle,
} from "@/features/preview/lib/character-sheet-bundle";

interface ChatListProps {
    timeline: TimelineEvent[];
    latestPlan?: PlanUpdateData | null;
    latestOutline?: any;
    latestSlideDeck?: any;
    queuedUserMessage?: string | null;
    isLoading?: boolean;
    status?: "ready" | "submitted" | "streaming" | "error";
    onSendFollowup?: (prompt: string) => void;
    className?: string;
}

type TimelineRenderEntry =
    | { kind: "item"; key: string; item: TimelineEvent }
    | {
        kind: "step_group";
        key: string;
        stepId: string;
        title: string;
        items: TimelineEvent[];
        status: PlanStepStatus;
    };

type VisualDeckKind = "slide_deck" | "character_sheet_deck" | "comic_page_deck";

const DEFAULT_ASPECT_RATIO_BY_MODE: Record<string, string> = {
    slide_render: "16:9",
    document_layout_render: "4:5",
    comic_page_render: "9:16",
    character_sheet_render: "2:3",
};

function resolveVisualDeckKind(mode?: string | null): VisualDeckKind {
    if (mode === "character_sheet_render") return "character_sheet_deck";
    if (mode === "comic_page_render") return "comic_page_deck";
    return "slide_deck";
}

function resolveVisualAspectRatio(
    mode?: string | null,
    rawAspectRatio?: string | null,
    kind?: VisualDeckKind | null,
): string {
    if (typeof rawAspectRatio === "string" && rawAspectRatio.trim().length > 0) {
        return rawAspectRatio.trim();
    }
    if (kind === "character_sheet_deck") return "2:3";
    if (kind === "comic_page_deck") return "9:16";
    if (typeof mode === "string" && mode in DEFAULT_ASPECT_RATIO_BY_MODE) {
        return DEFAULT_ASPECT_RATIO_BY_MODE[mode];
    }
    return "16:9";
}

export function ChatList({
    timeline,
    latestPlan,
    latestOutline,
    latestSlideDeck,
    queuedUserMessage,
    isLoading,
    status,
    onSendFollowup,
    className,
}: ChatListProps) {
    const { artifacts } = useArtifactStore(
        useShallow((state) => ({
            artifacts: state.artifacts,
        }))
    );
    const scrollAreaRef = useRef<HTMLDivElement | null>(null);
    const viewportRef = useRef<HTMLElement | null>(null);
    const shouldAutoScrollRef = useRef(true);
    const NEAR_BOTTOM_THRESHOLD = 120;

    useEffect(() => {
        const root = scrollAreaRef.current;
        if (!root) return;
        const viewport = root.querySelector<HTMLElement>('[data-slot="scroll-area-viewport"]');
        if (!viewport) return;

        viewportRef.current = viewport;
        const updateAutoScrollState = () => {
            const distance = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight;
            shouldAutoScrollRef.current = distance <= NEAR_BOTTOM_THRESHOLD;
        };

        updateAutoScrollState();
        viewport.addEventListener("scroll", updateAutoScrollState, { passive: true });
        return () => {
            viewport.removeEventListener("scroll", updateAutoScrollState);
            if (viewportRef.current === viewport) {
                viewportRef.current = null;
            }
        };
    }, []);

    useEffect(() => {
        const viewport = viewportRef.current;
        if (!viewport) return;
        if (!shouldAutoScrollRef.current) return;
        viewport.scrollTo({
            top: viewport.scrollHeight,
            behavior: isLoading ? "auto" : "smooth",
        });
    }, [timeline, isLoading]);

    const processedTimeline = useMemo(() => [...timeline], [timeline]);

    const lastMessageId = useMemo(() => {
        for (let i = processedTimeline.length - 1; i >= 0; i--) {
            const item = processedTimeline[i];
            if (item.type === "message") return item.id;
        }
        return undefined;
    }, [processedTimeline]);

    const isLastPartReasoning = useMemo(() => {
        const lastMessage = [...processedTimeline].reverse().find((item) => item.type === "message");
        if (!lastMessage?.message?.parts) return false;
        const parts = lastMessage.message.parts;
        const lastPart = parts[parts.length - 1];
        return lastPart?.type === "reasoning";
    }, [processedTimeline]);

    const shouldRenderPendingAssistant = Boolean(isLoading && !isLastPartReasoning);
    const pendingLabel = status === "streaming" ? "Generating..." : "Thinking...";
    const hasSlideDeckInTimeline = useMemo(
        () =>
            processedTimeline.some(
                (item) =>
                    item.type === "artifact" &&
                    ((item as any).kind === "slide_deck" ||
                        (item as any).kind === "character_sheet_deck" ||
                        (item as any).kind === "comic_page_deck")
            ),
        [processedTimeline]
    );
    const hasOutlineInTimeline = useMemo(
        () => processedTimeline.some((item) => item.type === "slide_outline"),
        [processedTimeline]
    );
    const latestSlideDeckFromArtifactStore = useMemo(() => {
        const slideDeckArtifacts = Object.values(artifacts).filter((artifact) => artifact?.type === "slide_deck");
        if (slideDeckArtifacts.length === 0) return null;
        const latestArtifact = slideDeckArtifacts
            .slice()
            .sort((a, b) => (b?.version ?? 0) - (a?.version ?? 0))[0];
        if (!latestArtifact) return null;
        const content = latestArtifact.content && typeof latestArtifact.content === "object" ? latestArtifact.content : {};
        const mode = inferVisualizerModeFromPayload(content, typeof (content as any).mode === "string" ? (content as any).mode : null);
        return {
            artifactId: latestArtifact.id,
            title: latestArtifact.title || "Generated Slides",
            slides: Array.isArray(content.slides) ? content.slides : [],
            status: latestArtifact.status || "completed",
            pdf_url: typeof content.pdf_url === "string" ? content.pdf_url : undefined,
            mode,
            aspectRatio:
                typeof (content as any).aspect_ratio === "string"
                    ? (content as any).aspect_ratio
                    : typeof (content as any).metadata?.aspect_ratio === "string"
                        ? (content as any).metadata.aspect_ratio
                        : undefined,
        };
    }, [artifacts]);
    const effectiveLatestSlideDeck = latestSlideDeck ?? latestSlideDeckFromArtifactStore;
    const characterSheetVisualRunArtifactIds = useMemo(() => {
        const bundleArtifact = artifacts[CHARACTER_SHEET_BUNDLE_ARTIFACT_ID];
        const bundle = normalizeCharacterSheetBundle(bundleArtifact?.content);
        const ids = new Set<string>();

        bundle.versions.forEach((version) => {
            version.visual_runs.forEach((run) => {
                if (typeof run.visual_artifact_id === "string" && run.visual_artifact_id.trim().length > 0) {
                    ids.add(run.visual_artifact_id.trim());
                }
            });
        });

        return ids;
    }, [artifacts]);
    const writerArtifactIdsInTimeline = useMemo(() => {
        const ids = new Set<string>();
        processedTimeline.forEach((item) => {
            if (item.type !== "artifact") return;
            const kind = (item as any).kind;
            if (typeof kind !== "string" || !kind.startsWith("writer_")) return;
            if (typeof item.artifactId === "string" && item.artifactId.trim().length > 0) {
                ids.add(item.artifactId);
            }
        });
        return ids;
    }, [processedTimeline]);
    const fallbackWriterArtifacts = useMemo(() => {
        return Object.values(artifacts)
            .filter((artifact) => {
                if (!artifact || typeof artifact.type !== "string") return false;
                if (!artifact.type.startsWith("writer_")) return false;
                if (artifact.type === "writer_character_sheet" && artifact.id !== CHARACTER_SHEET_BUNDLE_ARTIFACT_ID) {
                    return false;
                }
                return !writerArtifactIdsInTimeline.has(artifact.id);
            })
            .sort((a, b) => (b?.version ?? 0) - (a?.version ?? 0));
    }, [artifacts, writerArtifactIdsInTimeline]);

    const planStepStatusById = useMemo(() => {
        const statusMap = new Map<string, PlanStepStatus>();
        const steps = normalizePlanUpdateData(latestPlan).plan;
        steps.forEach((step: any, index: number) => {
            const stepId = String(step?.id ?? index);
            const normalized = normalizePlanStepStatus(step?.status);
            statusMap.set(stepId, normalized);
        });
        return statusMap;
    }, [latestPlan]);

    const renderEntries = useMemo<TimelineRenderEntry[]>(() => {
        const entries: TimelineRenderEntry[] = [];
        const stepOccurrenceById = new Map<string, number>();
        let currentGroup:
            | { stepId: string; title: string; items: TimelineEvent[] }
            | null = null;

        const pushGroup = (group: { stepId: string; title: string; items: TimelineEvent[] }, isLastGroup: boolean) => {
            const statusFromPlan = planStepStatusById.get(group.stepId);
            const fallbackStatus: PlanStepStatus =
                statusFromPlan ?? (isLastGroup && isLoading ? "in_progress" : "completed");
            const occurrence = stepOccurrenceById.get(group.stepId) ?? 0;
            stepOccurrenceById.set(group.stepId, occurrence + 1);
            const stepKey = occurrence === 0
                ? `step-${group.stepId}`
                : `step-${group.stepId}-${occurrence}`;

            entries.push({
                kind: "step_group",
                key: stepKey,
                stepId: group.stepId,
                title: group.title,
                items: group.items,
                status: fallbackStatus,
            });
        };

        processedTimeline.forEach((item, idx) => {
            if (item.type === "plan_step_marker") {
                if (currentGroup) {
                    pushGroup(currentGroup, false);
                }
                currentGroup = {
                    stepId: item.stepId,
                    title: item.title,
                    items: [],
                };
                return;
            }

            if (item.type === "plan_step_end_marker") {
                if (currentGroup) {
                    pushGroup(currentGroup, false);
                    currentGroup = null;
                }
                return;
            }

            if (currentGroup) {
                currentGroup.items.push(item);
                return;
            }

            entries.push({
                kind: "item",
                key: `item-${item.id}-${idx}`,
                item,
            });
        });

        if (currentGroup) {
            pushGroup(currentGroup, true);
        }

        return entries;
    }, [isLoading, planStepStatusById, processedTimeline]);

    const renderTimelineItem = (item: TimelineEvent, key: string): ReactNode => {
        const isLastMessage = item.type === "message" && item.id === lastMessageId;

        if (item.type === "message") {
            const msg = item.message;
            return (
                <div key={key} className="flex flex-col gap-2">
                    <ChatItem
                        role={msg.role}
                        content={msg.content}
                        parts={msg.parts}
                        name={msg.name}
                        avatar={msg.avatar}
                        toolInvocations={msg.toolInvocations}
                        isStreaming={isLastMessage && msg.role === "assistant" && isLoading}
                    />
                </div>
            );
        }

        if (item.type === "process_step") {
            return <TaskAccordion key={key} steps={[item.step]} />;
        }

        if (item.type === "worker_result") {
            const workerKey = item.capability || "worker";
            return (
                <WorkerResult
                    key={key}
                    role={workerKey}
                    summary={item.summary}
                    status={item.status}
                />
            );
        }

        if (item.type === "artifact") {
            if (
                (item as any).kind === "slide_deck" ||
                (item as any).kind === "character_sheet_deck" ||
                (item as any).kind === "comic_page_deck"
            ) {
                const itemKind = typeof (item as any).kind === "string" ? (item as any).kind : "slide_deck";
                const mode = typeof (item as any).mode === "string" ? (item as any).mode : null;
                const baseArtifactId =
                    typeof item.artifactId === "string" && item.artifactId.trim().length > 0
                        ? item.artifactId
                        : "visual_deck";
                const previewArtifactId =
                    mode === "character_sheet_render" && characterSheetVisualRunArtifactIds.has(baseArtifactId)
                        ? CHARACTER_SHEET_BUNDLE_ARTIFACT_ID
                        : baseArtifactId;
                const deckKind: VisualDeckKind =
                    itemKind === "character_sheet_deck" || itemKind === "comic_page_deck"
                        ? itemKind
                        : resolveVisualDeckKind(mode);
                const aspectRatio = resolveVisualAspectRatio(
                    mode,
                    (item as any).aspectRatio || (item as any).metadata?.aspect_ratio,
                    deckKind
                );
                return (
                    <div key={key} className="flex flex-col gap-2">
                        <ChatItem
                            role="assistant"
                            content=""
                            name="Visualizer"
                            artifact={{
                                kind: deckKind,
                                id: previewArtifactId,
                                title: item.title,
                                slides: (item as any).slides,
                                status: (item as any).status,
                                aspectRatio,
                            }}
                            isStreaming={(item as any).status === "streaming"}
                        />
                    </div>
                );
            }

            if ((item as any).kind === "writer_character_sheet") {
                return (
                    <CharacterSheetSummary
                        key={key}
                        artifactId={item.artifactId || CHARACTER_SHEET_BUNDLE_ARTIFACT_ID}
                    />
                );
            }

            return (
                <div key={key} className="flex flex-col gap-1 pl-4 md:pl-10">
                    <ArtifactButton
                        artifactId={item.artifactId}
                        title={item.title}
                        icon={item.icon}
                    />
                    {item.previewUrls && item.previewUrls.length > 0 && (
                        <ArtifactPreview
                            previewUrls={item.previewUrls}
                            title={item.title}
                            artifactId={item.artifactId}
                        />
                    )}
                </div>
            );
        }

        if (item.type === "code_execution") {
            return (
                <CodeExecutionBlock
                    key={key}
                    code={item.code}
                    language={item.language}
                    status={item.status}
                    result={item.result}
                    toolCallId={item.toolCallId}
                />
            );
        }

        if (item.type === "slide_outline") {
            return (
                <div key={key} className="flex flex-col gap-1">
                    <SlideOutline
                        slides={item.slides}
                        title={(item as any).title}
                        approvalStatus={isLoading ? "loading" : "idle"}
                    />
                </div>
            );
        }

        if (item.type === "research_report") {
            return (
                <div key={key} className="flex w-full justify-start">
                    <ResearchTaskCard
                        taskId={item.taskId}
                        perspective={item.perspective}
                        status={item.status}
                        searchMode={item.searchMode}
                        report={item.report}
                        sources={item.sources}
                    />
                </div>
            );
        }

        if (item.type === "coordinator_followups") {
            return (
                <div key={key} className="py-2">
                    <CoordinatorFollowupsCard
                        options={item.options}
                        onSendFollowup={onSendFollowup}
                        disabled={Boolean(isLoading)}
                    />
                </div>
            );
        }

        return null;
    };

    return (
        <ScrollArea ref={scrollAreaRef} className={className}>
            <div className="flex flex-col gap-1 p-4 pb-32 max-w-5xl mx-auto w-full">
                {renderEntries.map((entry) => {
                    if (entry.kind === "item") {
                        return renderTimelineItem(entry.item, entry.key);
                    }

                    return (
                        <PlanStepSection
                            key={entry.key}
                            stepId={entry.stepId}
                            title={entry.title}
                            status={entry.status}
                        >
                            {entry.items.map((item, idx) =>
                                renderTimelineItem(item, `${entry.key}-item-${idx}`)
                            )}
                        </PlanStepSection>
                    );
                })}

                {!hasOutlineInTimeline && latestOutline && Array.isArray(latestOutline.slides) ? (
                    <div className="flex flex-col gap-1">
                        <SlideOutline
                            slides={latestOutline.slides}
                            title={latestOutline.title}
                            approvalStatus={isLoading ? "loading" : "idle"}
                        />
                    </div>
                ) : null}

                {fallbackWriterArtifacts.map((artifact) => (
                    artifact.type === "writer_character_sheet" ? (
                        <CharacterSheetSummary
                            key={`fallback-writer-${artifact.id}`}
                            artifactId={artifact.id}
                        />
                    ) : (
                        <div key={`fallback-writer-${artifact.id}`} className="flex flex-col gap-1 pl-4 md:pl-10">
                            <ArtifactButton
                                artifactId={artifact.id}
                                title={artifact.title || "Writer Output"}
                                icon="BookOpen"
                            />
                        </div>
                    )
                ))}

                {effectiveLatestSlideDeck && !hasSlideDeckInTimeline ? (
                    <div className="flex flex-col gap-2">
                        {(() => {
                            const mode = typeof effectiveLatestSlideDeck.mode === "string"
                                ? effectiveLatestSlideDeck.mode
                                : null;
                            const deckKind = resolveVisualDeckKind(mode);
                            const aspectRatio = resolveVisualAspectRatio(
                                mode,
                                (effectiveLatestSlideDeck as any).aspectRatio || (effectiveLatestSlideDeck as any).metadata?.aspect_ratio,
                                deckKind
                            );
                            const previewArtifactId =
                                mode === "character_sheet_render" &&
                                    typeof effectiveLatestSlideDeck.artifactId === "string" &&
                                    characterSheetVisualRunArtifactIds.has(effectiveLatestSlideDeck.artifactId)
                                    ? CHARACTER_SHEET_BUNDLE_ARTIFACT_ID
                                    : (effectiveLatestSlideDeck.artifactId || "visual_deck");
                            return (
                                <ChatItem
                                    role="assistant"
                                    content=""
                                    name="Visualizer"
                                    artifact={{
                                        kind: deckKind,
                                        id: previewArtifactId,
                                        title: effectiveLatestSlideDeck.title || "Generated Slides",
                                        slides: Array.isArray(effectiveLatestSlideDeck.slides) ? effectiveLatestSlideDeck.slides : [],
                                        status: effectiveLatestSlideDeck.status,
                                        aspectRatio,
                                    }}
                                    isStreaming={effectiveLatestSlideDeck.status === "streaming"}
                                />
                            );
                        })()}
                    </div>
                ) : null}

                {shouldRenderPendingAssistant && (
                    <div className="flex flex-col gap-2">
                        <ChatItem
                            role="assistant"
                            content=""
                            parts={[]}
                            isStreaming={true}
                            loadingText={pendingLabel}
                        />
                    </div>
                )}

                {queuedUserMessage && queuedUserMessage.trim().length > 0 && (
                    <div className="flex flex-col gap-2">
                        <ChatItem
                            role="user"
                            content={queuedUserMessage}
                        />
                    </div>
                )}
            </div>
        </ScrollArea>
    );
}

interface CoordinatorFollowupsCardProps {
    options: Array<{ id: string; prompt: string }>;
    onSendFollowup?: (prompt: string) => void;
    disabled?: boolean;
}

function CoordinatorFollowupsCard({ options, onSendFollowup, disabled = false }: CoordinatorFollowupsCardProps) {
    if (!options || options.length === 0) return null;

    return (
        <div className="w-full max-w-3xl py-2">
            <p className="text-[14px] font-medium text-slate-500/80 mb-1 px-1">Suggested follow-ups</p>
            <div className="flex flex-col border-t border-slate-100">
                {options.map((option) => (
                    <button
                        key={option.id}
                        type="button"
                        onClick={() => onSendFollowup?.(option.prompt)}
                        disabled={disabled}
                        className={cn(
                            "group w-full flex items-start gap-4 py-4 px-1 border-b border-slate-100 transition-colors text-left",
                            "hover:bg-slate-50/50 disabled:opacity-50 disabled:cursor-not-allowed"
                        )}
                    >
                        <MessageSquare className="h-5 w-5 mt-0.5 shrink-0 text-slate-400 group-hover:text-slate-600 transition-colors" />
                        <div className="flex-1 min-w-0">
                            <p className="text-[16px] font-medium text-slate-700 leading-snug group-hover:text-slate-900 transition-colors">
                                {option.prompt}
                            </p>
                        </div>
                        <ArrowRight className="h-5 w-5 mt-0.5 shrink-0 text-slate-300 group-hover:text-slate-500 transition-colors" />
                    </button>
                ))}
            </div>
        </div>
    );
}

interface PlanStepSectionProps {
    stepId: string;
    title: string;
    status: PlanStepStatus;
    children: ReactNode;
}

function PlanStepSection({ stepId, title, status, children }: PlanStepSectionProps) {
    const [open, setOpen] = useState(status === "in_progress" || status === "blocked");

    useEffect(() => {
        if (status === "in_progress" || status === "blocked") {
            setOpen(true);
        }
    }, [status]);

    const statusIcon = (() => {
        if (status === "completed") {
            return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
        }
        if (status === "in_progress") {
            return <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />;
        }
        if (status === "blocked") {
            return <Circle className="h-4 w-4 text-red-500" />;
        }
        return <Circle className="h-4 w-4 text-slate-300" />;
    })();

    return (
        <Collapsible
            open={open}
            onOpenChange={setOpen}
            className="relative w-full"
            data-step-id={stepId}
        >
            <div className={cn(
                "absolute left-[14px] top-9 bottom-2 border-l-2 border-dashed border-slate-400/90",
                !open && "bottom-auto h-3"
            )} />
            <CollapsibleTrigger asChild>
                <button
                    type="button"
                    className="flex w-full items-center gap-3 py-1 text-left hover:opacity-90 transition-opacity"
                >
                    <span className="relative z-10 flex h-7 w-7 items-center justify-center rounded-full bg-white border border-slate-200 shadow-sm">
                        {statusIcon}
                    </span>
                    <span className="flex-1 min-w-0 text-[18px] leading-tight font-semibold text-slate-900 truncate">
                        {title}
                    </span>
                    {open ? (
                        <ChevronUp className="h-5 w-5 text-slate-500" />
                    ) : (
                        <ChevronDown className="h-5 w-5 text-slate-500" />
                    )}
                </button>
            </CollapsibleTrigger>
            <CollapsibleContent>
                <div className="pl-10 pb-1 flex flex-col gap-1">{children}</div>
            </CollapsibleContent>
        </Collapsible>
    );
}
