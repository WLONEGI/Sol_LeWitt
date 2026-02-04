import { ScrollArea } from "@/components/ui/scroll-area"
import { Reasoning, ReasoningContent, ReasoningTrigger } from "./reasoning"
import { ChatItem } from "./chat-item"
import { TaskAccordion } from "./task-accordion"
import { PlanStatusChecklist } from "./plan-status-checklist"
import { ArtifactButton } from "./artifact-button"
import { WorkerResult } from "./worker-result"
import { ResearchStatusButton } from "./message/research-status-button"
import { ArtifactPreview } from "./artifact-preview"
import { CodeExecutionBlock } from "./code-execution-block"
import { SlideOutline } from "./slide-outline"
import { TimelineEvent } from "../types/timeline"
import { useEffect, useRef, useMemo } from "react"

interface ChatListProps {
    timeline: TimelineEvent[];
    latestOutline?: any; // Added
    isLoading?: boolean;
    className?: string;
}

export function ChatList({ timeline, latestOutline, isLoading, className }: ChatListProps) {
    const bottomRef = useRef<HTMLDivElement>(null);

    // Auto-scroll on new items
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [timeline, isLoading]);

    // Enhanced timeline with outline injection
    const processedTimeline = useMemo(() => {
        const items = [...timeline];
        if (latestOutline) {
            items.push({
                id: 'current-slide-outline',
                type: 'slide_outline',
                timestamp: Date.now(),
                slides: latestOutline.slides,
                title: latestOutline.title
            } as any);
        }
        return items;
    }, [timeline, latestOutline]);

    return (
        <ScrollArea className={className}>
            <div className="flex flex-col gap-6 p-4 pb-32 max-w-4xl mx-auto w-full">
                {processedTimeline.map((item: any) => {
                    const isLast = item === processedTimeline[processedTimeline.length - 1];

                    // 1. User/Assistant Message
                    if (item.type === 'message') {
                        const msg = item.message;

                        // Extract reasoning from parts (Standard Protocol) or fallback to custom property
                        const reasoningPart = msg.parts?.find((p: any) => p.type === 'reasoning');
                        const reasoningText = reasoningPart && 'text' in reasoningPart
                            ? (reasoningPart as any).text
                            : (msg as any).reasoning;

                        return (
                            <div key={item.id} className="flex flex-col gap-2">
                                <ChatItem
                                    role={msg.role}
                                    content={msg.content}
                                    parts={msg.parts}
                                    name={msg.name}
                                    avatar={msg.avatar}
                                    toolInvocations={msg.toolInvocations}
                                    isStreaming={isLast && msg.role === 'assistant' && isLoading}
                                />
                            </div>
                        );
                    }

                    // 2. Process Step (Accordion)
                    if (item.type === 'process_step') {
                        return (
                            <TaskAccordion
                                key={item.id}
                                steps={[item.step]}
                                isRunning={item.step.status === 'running'}
                            />
                        );
                    }

                    // 3. Worker Result
                    if (item.type === 'worker_result') {
                        return (
                            <WorkerResult
                                key={item.id}
                                role={item.role}
                                summary={item.summary}
                                status={item.status}
                            />
                        );
                    }

                    // 4. Artifact / Images
                    if (item.type === 'artifact') {
                        // Check for slide_deck artifact to use specialized ChatItem view
                        if ((item as any).kind === 'slide_deck') {
                            return (
                                <div key={item.id} className="flex flex-col gap-2">
                                    <ChatItem
                                        role="assistant"
                                        content="" // No text content for slide deck itself
                                        name="Visualizer" // Or generic robot name
                                        artifact={{
                                            kind: 'slide_deck',
                                            id: item.artifactId,
                                            title: item.title,
                                            slides: (item as any).slides,
                                            status: (item as any).status
                                        }}
                                        isStreaming={(item as any).status === 'streaming'}
                                    />
                                </div>
                            )
                        }

                        return (
                            <div key={item.id} className="flex flex-col gap-1 pl-4 md:pl-10">
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

                    // 5. Plan Update - Handled by FixedPlanOverlay in ChatInterface
                    /*
                    if (item.type === 'plan_update') {
                        // ...
                    }
                    */

                    // 6. Code Execution Artifact
                    if (item.type === 'code_execution') {
                        return (
                            <CodeExecutionBlock
                                key={item.id}
                                code={item.code}
                                language={item.language}
                                status={item.status}
                                result={item.result}
                                toolCallId={item.toolCallId}
                            />
                        )
                    }

                    if (item.type === 'slide_outline') {
                        // Similar logic as plan_update, look for pending approve_outline tool call
                        const approvalTool = null;

                        return (
                            <div key={item.id} className="flex flex-col gap-1">
                                <SlideOutline
                                    slides={item.slides}
                                    title={item.title}
                                    approvalStatus={isLoading ? 'loading' : 'idle'}
                                />
                            </div>
                        );
                    }

                    if (item.type === 'research_report') {
                        return (
                            <div key={item.id} className="flex justify-start pl-12 my-2">
                                <ResearchStatusButton
                                    taskId={item.taskId}
                                    perspective={item.perspective}
                                    status={item.status}
                                />
                            </div>
                        );
                    }

                    return null;
                })}

                <div ref={bottomRef} />
            </div>
        </ScrollArea>
    )
}
