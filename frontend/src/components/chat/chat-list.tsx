import { ScrollArea } from "@/components/ui/scroll-area"
import { ChatItem } from "./chat-item"
import { TaskAccordion } from "./task-accordion"
import { PlanAccordion } from "./plan-accordion"
import { ArtifactButton } from "./artifact-button"
import { WorkerResult } from "./worker-result"
import { ArtifactPreview } from "./artifact-preview"
import { useEffect, useRef } from "react"
import { TimelineEvent } from "@/types/timeline"

interface ChatListProps {
    timeline: TimelineEvent[];
    isLoading?: boolean;
    className?: string;
    // streamingSources kept for compatibility if needed, though now handled via timeline logic presumably
    streamingSources?: { title: string; url: string }[];
}

export function ChatList({ timeline, isLoading, className, streamingSources }: ChatListProps) {
    const bottomRef = useRef<HTMLDivElement>(null);

    // Auto-scroll on new items
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [timeline, isLoading]);

    return (
        <ScrollArea className={className}>
            <div className="flex flex-col gap-2 p-4 pb-32">
                {timeline.map((item) => {
                    const isLast = item === timeline[timeline.length - 1];

                    // 1. User/Assistant Message
                    if (item.type === 'message') {
                        const msg = item.message;
                        // For assistant messages, we might attach streaming sources if it's the last one
                        const effectiveSources = msg.sources || (isLast && msg.role === 'assistant' ? streamingSources : undefined);

                        return (
                            <div key={item.id} className="flex flex-col gap-1">
                                {msg.reasoning && (
                                    <details className="mb-2 ml-14 text-xs text-muted-foreground bg-white/5 p-2 rounded cursor-pointer open:bg-white/10 transition-colors max-w-[80%]">
                                        <summary className="font-medium hover:text-foreground">Thinking Process</summary>
                                        <div className="mt-2 text-wrap pl-2 border-l-2 border-primary/20">
                                            {msg.reasoning}
                                        </div>
                                    </details>
                                )}
                                <ChatItem
                                    role={msg.role}
                                    content={msg.content}
                                    name={msg.name}
                                    avatar={msg.avatar}
                                    sources={effectiveSources}
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

                    // 3. Worker Result (if strictly typed in timeline, but for now we rely on message metadata or specific events?)
                    // The backend sends 'tool_result' log events which go into ProcessStep.
                    // But if we have standalone WorkerResult items (from older logic or explicit artifact)
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
                        return (
                            <div key={item.id} className="flex flex-col gap-1">
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

                    // 5. Plan Update
                    if (item.type === 'plan_update') {
                        return (
                            <PlanAccordion
                                key={item.id}
                                plan={item.plan}
                                title={item.title}
                                description={item.description}
                            />
                        );
                    }

                    return null;
                })}

                <div ref={bottomRef} />
            </div>
        </ScrollArea>
    )
}
