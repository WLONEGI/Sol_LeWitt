import { ScrollArea } from "@/components/ui/scroll-area"
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
    latestSlideDeck?: any;
    isLoading?: boolean;
    status?: 'ready' | 'submitted' | 'streaming' | 'error';
    className?: string;
}

export function ChatList({ timeline, latestOutline, latestSlideDeck, isLoading, status, className }: ChatListProps) {
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
        if (latestSlideDeck) {
            items.push({
                id: 'current-slide-deck',
                type: 'artifact',
                timestamp: Date.now() + 1,
                artifactId: latestSlideDeck.artifactId,
                title: latestSlideDeck.title,
                kind: 'slide_deck',
                slides: latestSlideDeck.slides,
                status: latestSlideDeck.status,
                pdf_url: latestSlideDeck.pdf_url
            } as any);
        }
        return items;
    }, [timeline, latestOutline, latestSlideDeck]);

    const lastMessageId = useMemo(() => {
        for (let i = processedTimeline.length - 1; i >= 0; i--) {
            const item = processedTimeline[i];
            if (item.type === 'message') return item.id;
        }
        return undefined;
    }, [processedTimeline]);

    const lastMessageEvent = useMemo(() => {
        for (let i = processedTimeline.length - 1; i >= 0; i--) {
            const item = processedTimeline[i];
            if (item.type === 'message') return item;
        }
        return undefined;
    }, [processedTimeline]);

    const lastAssistantMessage = useMemo(() => {
        for (let i = processedTimeline.length - 1; i >= 0; i--) {
            const item = processedTimeline[i];
            if (item.type === 'message' && item.message?.role === 'assistant') return item;
        }
        return undefined;
    }, [processedTimeline]);

    const assistantMessageText = useMemo(() => {
        const msg = lastAssistantMessage?.message;
        if (!msg) return '';
        if (msg.content) return msg.content;
        if (!msg.parts) return '';
        return msg.parts
            .filter((part: any) => part?.type === 'text' && typeof part.text === 'string')
            .map((part: any) => part.text)
            .join('');
    }, [lastAssistantMessage]);

    const assistantHasReasoning = useMemo(() => {
        const msg = lastAssistantMessage?.message;
        if (!msg?.parts) return false;
        return msg.parts.some(
            (part: any) => part?.type === 'reasoning' && typeof part.text === 'string'
        );
    }, [lastAssistantMessage]);

    const shouldRenderPendingAssistant = Boolean(
        isLoading &&
            (
                !lastAssistantMessage ||
                lastMessageEvent?.message?.role === 'user' ||
                (assistantMessageText.length === 0 && !assistantHasReasoning)
            )
    );
    const pendingLabel = status === 'streaming' ? 'Generating...' : 'Thinking...';

    return (
        <ScrollArea className={className}>
            <div className="flex flex-col gap-6 p-4 pb-32 max-w-4xl mx-auto w-full">
                {processedTimeline.map((item: any) => {
                    const isLastMessage = item.type === 'message' && item.id === lastMessageId;

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
                                    isStreaming={isLastMessage && msg.role === 'assistant' && isLoading}
                                />
                            </div>
                        );
                    }

                    // 2. Process Step (Accordion)
                    if (item.type === 'process_step') {
                        return (
                            <TaskAccordion key={item.id} steps={[item.step]} />
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
                            <div key={item.id} className="flex w-full gap-4 p-4 justify-start">
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

                    return null;
                })}

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

                <div ref={bottomRef} />
            </div>
        </ScrollArea>
    )
}
