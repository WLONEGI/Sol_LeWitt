import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatItem } from "./chat-item";
import { TaskAccordion } from "./task-accordion";
import { ArtifactButton } from "./artifact-button";
import { WorkerResult } from "./worker-result";
import { ResearchStatusButton } from "./message/research-status-button";
import { ArtifactPreview } from "./artifact-preview";
import { CodeExecutionBlock } from "./code-execution-block";
import { SlideOutline } from "./slide-outline";
import { ImageSearchResults } from "./image-search-results";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { useArtifactStore } from "@/features/preview/stores/artifact";
import { CheckCircle2, ChevronDown, ChevronUp, Circle, Loader2 } from "lucide-react";
import { TimelineEvent } from "../types/timeline";
import type { PlanStepStatus, PlanUpdateData } from "../types/plan";
import { normalizePlanStepStatus, normalizePlanUpdateData } from "../types/plan";
import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";

interface ChatListProps {
    timeline: TimelineEvent[];
    latestPlan?: PlanUpdateData | null;
    latestOutline?: any;
    latestSlideDeck?: any;
    selectedImageUrls?: string[];
    onToggleImageCandidate?: (candidate: any) => void;
    queuedUserMessage?: string | null;
    isLoading?: boolean;
    status?: "ready" | "submitted" | "streaming" | "error";
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

export function ChatList({
    timeline,
    latestPlan,
    latestOutline,
    latestSlideDeck,
    selectedImageUrls = [],
    onToggleImageCandidate,
    queuedUserMessage,
    isLoading,
    status,
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
                (item) => item.type === "artifact" && (item as any).kind === "slide_deck"
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
        return {
            artifactId: latestArtifact.id,
            title: latestArtifact.title || "Generated Slides",
            slides: Array.isArray(content.slides) ? content.slides : [],
            status: latestArtifact.status || "completed",
            pdf_url: typeof content.pdf_url === "string" ? content.pdf_url : undefined,
        };
    }, [artifacts]);
    const effectiveLatestSlideDeck = latestSlideDeck ?? latestSlideDeckFromArtifactStore;
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
        let currentGroup:
            | { stepId: string; title: string; items: TimelineEvent[] }
            | null = null;

        const pushGroup = (group: { stepId: string; title: string; items: TimelineEvent[] }, isLastGroup: boolean) => {
            const statusFromPlan = planStepStatusById.get(group.stepId);
            const fallbackStatus: PlanStepStatus =
                statusFromPlan ?? (isLastGroup && isLoading ? "in_progress" : "completed");

            entries.push({
                kind: "step_group",
                key: `step-${group.stepId}-${entries.length}`,
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
            if ((item as any).kind === "slide_deck") {
                return (
                    <div key={key} className="flex flex-col gap-2">
                        <ChatItem
                            role="assistant"
                            content=""
                            name="Visualizer"
                            artifact={{
                                kind: "slide_deck",
                                id: item.artifactId,
                                title: item.title,
                                slides: (item as any).slides,
                                status: (item as any).status,
                            }}
                            isStreaming={(item as any).status === "streaming"}
                        />
                    </div>
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
                <div key={key} className="flex w-full gap-4 p-4 justify-start">
                    <div className="flex flex-col items-start w-full">
                        <ResearchStatusButton
                            taskId={item.taskId}
                            perspective={item.perspective}
                            status={item.status}
                        />
                    </div>
                </div>
            );
        }

        if (item.type === "image_search_results") {
            return (
                <ImageSearchResults
                    key={key}
                    query={item.query || item.perspective || "image search"}
                    candidates={item.candidates || []}
                    selectedUrls={selectedImageUrls}
                    onToggleSelect={(candidate) => onToggleImageCandidate?.(candidate)}
                />
            )
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
                    <div key={`fallback-writer-${artifact.id}`} className="flex flex-col gap-1 pl-4 md:pl-10">
                        <ArtifactButton
                            artifactId={artifact.id}
                            title={artifact.title || "Writer Output"}
                            icon="BookOpen"
                        />
                    </div>
                ))}

                {effectiveLatestSlideDeck && !hasSlideDeckInTimeline ? (
                    <div className="flex flex-col gap-2">
                        <ChatItem
                            role="assistant"
                            content=""
                            name="Visualizer"
                            artifact={{
                                kind: "slide_deck",
                                id: effectiveLatestSlideDeck.artifactId || "visual_deck",
                                title: effectiveLatestSlideDeck.title || "Generated Slides",
                                slides: Array.isArray(effectiveLatestSlideDeck.slides) ? effectiveLatestSlideDeck.slides : [],
                                status: effectiveLatestSlideDeck.status,
                            }}
                            isStreaming={effectiveLatestSlideDeck.status === "streaming"}
                        />
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
                "absolute left-[14px] top-9 bottom-2 border-l border-dashed border-slate-300/80",
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
