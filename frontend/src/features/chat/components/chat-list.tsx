import { ScrollArea } from "@/components/ui/scroll-area"
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
            <div className="flex flex-col gap-6 p-4 pb-32 max-w-4xl mx-auto w-full">
                {timeline.map((item) => {
                    const isLast = item === timeline[timeline.length - 1];

                    // 1. User/Assistant Message
                    if (item.type === 'message') {
                        const msg = item.message;
                        const effectiveSources = msg.sources || (isLast && msg.role === 'assistant' ? streamingSources : undefined);

                        return (
                            <div key={item.id} className="flex flex-col gap-2">
                                {msg.reasoning && (
                                    <div className="ml-14 mb-2">
                                        <details className="group open:bg-gray-50 rounded-lg transition-colors duration-200 border border-transparent open:border-gray-100">
                                            <summary className="flex items-center gap-2 cursor-pointer p-2 text-xs font-medium text-gray-500 select-none hover:text-gray-900 transition-colors list-none">
                                                <div className="flex items-center justify-center w-5 h-5 rounded hover:bg-gray-100 transition-colors">
                                                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-open:rotate-90"><path d="m9 18 6-6-6-6" /></svg>
                                                </div>
                                                <span>Thinking Process</span>
                                            </summary>
                                            <div className="px-4 pb-3 pt-1">
                                                <div className="pl-3 border-l-2 border-gray-200 text-sm text-gray-600 font-mono bg-white/50 p-3 rounded-r-md">
                                                    {msg.reasoning}
                                                </div>
                                            </div>
                                        </details>
                                    </div>
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
