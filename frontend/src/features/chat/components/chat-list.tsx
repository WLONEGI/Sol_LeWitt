import { ScrollArea } from "@/components/ui/scroll-area"
import { Reasoning, ReasoningContent, ReasoningTrigger } from "@/components/ai-elements/reasoning"
import { ChatItem } from "./chat-item"
import { TaskAccordion } from "./task-accordion"
import { PlanAccordion } from "./plan-accordion"
import { ArtifactButton } from "./artifact-button"
import { WorkerResult } from "./worker-result"
import { ArtifactPreview } from "./artifact-preview"
import { CodeExecutionBlock } from "./code-execution-block"
import { SlideOutline } from "./slide-outline"
import { useEffect, useRef } from "react"
import { TimelineEvent } from "../types/timeline"

interface ChatListProps {
    timeline: TimelineEvent[];
    isLoading?: boolean;
    className?: string;
}

export function ChatList({ timeline, isLoading, className }: ChatListProps) {
    const bottomRef = useRef<HTMLDivElement>(null);

    // Auto-scroll on new items
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [timeline, isLoading]);

    return (
        <ScrollArea className={className}>
            <div className="flex flex-col gap-6 p-4 pb-32 max-w-4xl mx-auto w-full">
                {timeline.map((item) => {
                    const isLast = item === timeline[timeline.length - 1];

                    // 1. User/Assistant Message
                    if (item.type === 'message') {
                        const msg = item.message;
                        const effectiveSources = msg.sources;

                        // Extract reasoning from parts (Standard Protocol) or fallback to custom property
                        const reasoningPart = msg.parts?.find(p => p.type === 'reasoning');
                        const reasoningText = reasoningPart && 'text' in reasoningPart
                            ? (reasoningPart as any).text
                            : (msg as any).reasoning;

                        return (
                            <div key={item.id} className="flex flex-col gap-2">
                                {reasoningText && (
                                    <div className="ml-14 mb-2">
                                        <Reasoning>
                                            <ReasoningTrigger />
                                            <ReasoningContent>{reasoningText}</ReasoningContent>
                                        </Reasoning>
                                    </div>
                                )}
                                <ChatItem
                                    role={msg.role}
                                    content={msg.content}
                                    name={msg.name}
                                    avatar={msg.avatar}
                                    sources={effectiveSources}
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
                        return (
                            <div key={item.id} className="flex flex-col gap-1 pl-4 md:pl-10">
                                <SlideOutline slides={item.slides} />
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
