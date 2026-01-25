"use client"

import { cn } from "@/lib/utils"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Markdown } from "@/components/markdown"
import { Bot, User } from "lucide-react"
import { motion } from "framer-motion";
import { SourceCitation } from "./source-citation";
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
}

export function ChatItem({ role, content, avatar, name, className, sources, isStreaming = false }: ChatItemProps) {
    const isUser = role === 'user';

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className={cn("flex w-full gap-4 p-4", isUser ? "flex-row-reverse" : "flex-row", className)}
        >
            <Avatar className="h-8 w-8 border border-white/10 shadow-sm shrink-0">
                {avatar ? <AvatarImage src={avatar} /> : (
                    <AvatarFallback className="bg-muted bg-gradient-to-br from-white/10 to-white/5">
                        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                    </AvatarFallback>
                )}
            </Avatar>

            <div className={cn(
                "flex flex-col max-w-[80%]",
                isUser ? "items-end" : "items-start"
            )}>
                {name && <span className="text-xs text-muted-foreground mb-1 ml-1">{name}</span>}
                <div className={cn(
                    "rounded-2xl px-5 py-3 shadow-md backdrop-blur-sm",
                    isUser
                        ? "bg-gradient-to-br from-primary to-blue-600 text-white rounded-tr-sm"
                        : "bg-white/5 border border-white/10 text-foreground rounded-tl-sm hover:bg-white/10 transition-colors duration-300"
                )}>
                    {/* ストリーミング中はタイプライター、完了後はマークダウン */}
                    {isStreaming && !isUser ? (
                        <div className="prose prose-sm dark:prose-invert max-w-none">
                            <TypewriterText
                                text={content}
                                speed={12}
                                showCursor={true}
                            />
                        </div>
                    ) : (
                        <Markdown className={cn(isUser && "prose-invert")}>{content}</Markdown>
                    )}
                </div>

                {/* Render Citations below the bubble if sources exist */}
                {sources && sources.length > 0 && (
                    <SourceCitation sources={sources} />
                )}
            </div>
        </motion.div>
    )
}
