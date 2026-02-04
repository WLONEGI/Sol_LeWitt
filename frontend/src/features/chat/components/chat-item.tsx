"use client"

import { cn } from "@/lib/utils"
import { Markdown } from "@/components/ui/markdown"
import { motion } from "framer-motion";
import { SlideDeckPreview } from "./slide-deck-preview"; // Assuming relative path
import { TypewriterText } from "@/components/ui/typewriter-text";
import { ToolInvocationBlock } from "./tool-invocation";
import { TimelineReasoning } from "./timeline-reasoning";
import { WaveText } from "@/components/ui/wave-text";

interface ChatItemProps {
    role: 'user' | 'assistant' | 'system';
    content: string;
    parts?: any[];
    avatar?: string;
    name?: string;
    className?: string;
    /** ストリーミング中かどうか。trueの場合タイプライターエフェクトを適用 */
    isStreaming?: boolean;
    loadingText?: string;
    // Optional artifact for rendering specific UI components within the chat stream
    artifact?: {
        kind: string;
        title: string;
        id: string;
        slides?: any[];
        status?: string;
    };
    toolInvocations?: any[];
}


export function ChatItem({ role, content, parts, avatar, name, className, isStreaming = false, loadingText, artifact, toolInvocations }: ChatItemProps) {
    const isUser = role === 'user';
    const streamedText =
        content ||
        (parts ?? [])
            .filter((part) => part?.type === 'text' && typeof part.text === 'string')
            .map((part) => part.text)
            .join('');
    const hasReasoningPart = (parts ?? []).some(
        (part) => part?.type === 'reasoning' && typeof part.text === 'string'
    );
    const shouldShowLoader = isStreaming && !isUser && streamedText.length === 0 && !hasReasoningPart;

    // Check if this chat item is meant to display a slide deck
    if (artifact && artifact.kind === 'slide_deck') {
        return (
            <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
                className={cn("flex w-full gap-4 p-4 justify-start", className)}
            >
                <div className="flex flex-col items-start w-full max-w-[80%]">
                    {name && <span className="text-xs text-muted-foreground mb-1 ml-1">{name}</span>}
                    {/* Render the SlideDeckPreview component */}
                    <SlideDeckPreview
                        artifactId={artifact.id}
                        slides={artifact.slides || []}
                        title={artifact.title}
                        isStreaming={artifact.status === 'streaming'}
                    />
                </div>
            </motion.div>
        )
    }

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className={cn("flex w-full gap-4 p-4", isUser ? "justify-end" : "justify-start", className)}
        >
            <div className={cn(
                "flex flex-col",
                isUser ? "items-end max-w-[80%]" : "items-start w-full"
            )}>
                {name && <span className="text-sm text-muted-foreground mb-1 ml-1">{name}</span>}
                <div className={cn(
                    isUser
                        ? "rounded-2xl rounded-tr-sm px-6 py-4 bg-white text-foreground border border-gray-200 shadow-none text-base"
                        : "text-foreground p-0 bg-transparent border-none shadow-none w-full text-left font-typewriter text-base"
                )}>
                    {shouldShowLoader ? (
                        <div className="flex items-center py-2">
                            <WaveText
                                text={loadingText ?? "Thinking..."}
                                className="text-sm font-medium text-muted-foreground"
                            />
                        </div>
                    ) : isStreaming && !isUser && !hasReasoningPart ? (
                        <div className="prose prose-base dark:prose-invert max-w-none text-foreground font-medium font-typewriter">
                            <TypewriterText
                                text={streamedText}
                                speed={18}
                                showCursor={true}
                            />
                        </div>
                    ) : (
                        <div className="flex flex-col w-full">
                            {parts && parts.length > 0 ? (
                                parts.map((part, idx) => {
                                    if (part.type === 'text' && part.text) {
                                        return (
                                            <div key={idx} className="mb-3 last:mb-0">
                                                <Markdown className={cn(
                                                    "prose prose-base max-w-none text-gray-800 leading-relaxed font-normal",
                                                    !isUser && "font-sans",
                                                    "prose-p:text-gray-800 prose-headings:text-gray-900 prose-strong:text-gray-900 prose-li:text-gray-800 prose-code:text-blue-600 prose-code:bg-blue-50 prose-code:px-1 prose-code:rounded prose-code:before:content-none prose-code:after:content-none"
                                                )}>{part.text}</Markdown>
                                            </div>
                                        );
                                    }
                                    if (part.type === 'reasoning') {
                                        const reasoningText =
                                            typeof part.text === 'string'
                                                ? part.text
                                                : '';
                                        if (!reasoningText.trim()) return null;
                                        return (
                                            <TimelineReasoning
                                                key={idx}
                                                content={reasoningText}
                                                isLastInSequence={idx === parts.length - 1}
                                                isStreaming={isStreaming && !isUser}
                                            />
                                        );
                                    }
                                    return null;
                                })
                            ) : (
                                <Markdown className={cn(
                                    "prose prose-base max-w-none text-gray-800 leading-relaxed font-normal",
                                    !isUser && "font-sans",
                                    "prose-p:text-gray-800 prose-headings:text-gray-900 prose-strong:text-gray-900 prose-li:text-gray-800 prose-code:text-blue-600 prose-code:bg-blue-50 prose-code:px-1 prose-code:rounded prose-code:before:content-none prose-code:after:content-none"
                                )}>{content}</Markdown>
                            )}

                            {toolInvocations && toolInvocations.length > 0 && (
                                <ToolInvocationBlock toolInvocations={toolInvocations} />
                            )}
                        </div>
                    )}
                </div>
            </div>
        </motion.div>
    )
}
