"use client"

import { cn } from "@/lib/utils"
import { Markdown } from "@/components/ui/markdown"
import { ExternalLink } from "lucide-react"
import { motion } from "framer-motion";
import { SlideDeckPreview } from "./slide-deck-preview"; // Assuming relative path
import { useArtifactStore } from "../../preview/store/artifact";
import { TypewriterText } from "@/components/ui/typewriter-text";

interface ChatItemProps {
    role: 'user' | 'assistant' | 'system';
    content: string;
    avatar?: string;
    name?: string;
    className?: string;
    sources?: { title: string; url: string }[];
    /** ストリーミング中かどうか。trueの場合タイプライターエフェクトを適用 */
    isStreaming?: boolean;
    // Optional artifact for rendering specific UI components within the chat stream
    artifact?: {
        kind: string;
        title: string;
        id: string;
        slides?: any[];
        status?: string;
    }
}

interface Source {
    title: string;
    url: string;
}

interface SourceCitationProps {
    sources: Source[];
}

function SourceCitation({ sources }: SourceCitationProps) {
    if (!sources || sources.length === 0) return null;

    return (
        <div className="mt-3 flex flex-col gap-2">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Confirmed Sources</div>
            <div className="grid grid-cols-1 gap-2">
                {sources.map((source, index) => (
                    <a
                        key={index}
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2 p-2 rounded-md bg-background/50 border hover:bg-background/80 transition-colors text-sm group"
                    >
                        <div className="bg-primary/10 p-1.5 rounded-full text-primary group-hover:bg-primary/20">
                            <ExternalLink className="h-3 w-3" />
                        </div>
                        <span className="truncate flex-1 font-medium text-foreground/80 group-hover:text-primary transition-colors">
                            {source.title}
                        </span>
                    </a>
                ))}
            </div>
        </div>
    )
}

export function ChatItem({ role, content, avatar, name, className, sources, isStreaming = false, artifact }: ChatItemProps) {
    const isUser = role === 'user';

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
                {name && <span className="text-xs text-muted-foreground mb-1 ml-1">{name}</span>}
                <div className={cn(
                    isUser
                        ? "rounded-2xl rounded-tr-sm px-5 py-3 bg-white text-foreground border border-gray-200 shadow-none"
                        : "text-foreground p-0 bg-transparent border-none shadow-none w-full text-left font-typewriter"
                )}>
                    {isStreaming && !isUser ? (
                        <div className="prose prose-sm dark:prose-invert max-w-none text-foreground font-medium font-typewriter">
                            <TypewriterText
                                text={content}
                                speed={12}
                                showCursor={true}
                            />
                        </div>
                    ) : (
                        <Markdown className={cn(
                            "prose prose-sm max-w-none text-gray-800 leading-relaxed font-normal", // Typography: Line-height 1.6-1.7 (leading-relaxed)
                            !isUser && "font-sans",
                            "prose-p:text-gray-800 prose-headings:text-gray-900 prose-strong:text-gray-900 prose-li:text-gray-800 prose-code:text-blue-600 prose-code:bg-blue-50 prose-code:px-1 prose-code:rounded prose-code:before:content-none prose-code:after:content-none"
                        )}>{content}</Markdown>
                    )}

                    {sources && sources.length > 0 && (
                        <SourceCitation sources={sources} />
                    )}
                </div>
            </div>
        </motion.div>
    )
}
