"use client"

import { cn } from "@/lib/utils"
import { Markdown } from "@/components/ui/markdown"
import { motion } from "framer-motion";
import { FileCode2, FileImage, FileSpreadsheet, FileText } from "lucide-react";
import type { ComponentType } from "react";
import { SlideDeckPreview } from "./slide-deck-preview"; // Assuming relative path
import { CharacterSheetDeckPreview } from "./character-sheet-deck-preview";
import { ComicPageDeckPreview } from "./comic-page-deck-preview";
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
    /** ストリーミング中かどうか。trueの場合は逐次更新表示を適用 */
    isStreaming?: boolean;
    loadingText?: string;
    // Optional artifact for rendering specific UI components within the chat stream
    artifact?: {
        kind: string;
        title: string;
        id: string;
        slides?: any[];
        status?: string;
        aspectRatio?: string;
    };
    toolInvocations?: any[];
}

type MessageFilePart = {
    type: 'file';
    url: string;
    mediaType?: string;
    filename?: string;
};

function getFileTypeMeta(mediaType?: string, filename?: string): {
    label: string;
    icon: ComponentType<{ className?: string }>;
    iconClassName: string;
} {
    const mt = (mediaType || "").toLowerCase();
    const ext = (filename?.split(".").pop() || "").toLowerCase();

    if (mt.includes("presentationml") || ext === "pptx") {
        return { label: "PPTX", icon: FileText, iconClassName: "bg-orange-500 text-white" };
    }
    if (mt.startsWith("image/")) {
        return { label: "IMAGE", icon: FileImage, iconClassName: "bg-sky-500 text-white" };
    }
    if (mt.includes("html") || ext === "html" || ext === "htm") {
        return { label: "HTML", icon: FileCode2, iconClassName: "bg-red-600 text-white" };
    }
    if (mt.includes("csv") || ext === "csv") {
        return { label: "CSV", icon: FileSpreadsheet, iconClassName: "bg-emerald-600 text-white" };
    }
    if (mt.includes("json") || ext === "json") {
        return { label: "JSON", icon: FileCode2, iconClassName: "bg-violet-600 text-white" };
    }
    if (mt.includes("pdf") || ext === "pdf") {
        return { label: "PDF", icon: FileText, iconClassName: "bg-rose-600 text-white" };
    }
    return { label: "FILE", icon: FileText, iconClassName: "bg-slate-600 text-white" };
}


export function ChatItem({ role, content, parts, avatar, name, className, isStreaming = false, loadingText, artifact, toolInvocations }: ChatItemProps) {
    const isUser = role === 'user';
    const fileParts = (parts ?? []).filter(
        (part) => part?.type === 'file' && typeof part?.url === 'string' && part.url.length > 0
    ) as MessageFilePart[];
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

    const shouldRenderDeck =
        artifact &&
        (artifact.kind === 'slide_deck' ||
            artifact.kind === 'character_sheet_deck' ||
            artifact.kind === 'comic_page_deck');

    // Render visual deck cards in chat stream.
    if (shouldRenderDeck && artifact) {
        const DeckPreviewComponent =
            artifact.kind === 'character_sheet_deck'
                ? CharacterSheetDeckPreview
                : artifact.kind === 'comic_page_deck'
                    ? ComicPageDeckPreview
                    : SlideDeckPreview;
        return (
            <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
                className={cn("flex w-full gap-4 p-4 justify-start", className)}
            >
                <div className="flex flex-col items-start w-full max-w-[80%]">
                    {name && <span className="text-xs text-muted-foreground mb-1 ml-1">{name}</span>}
                    <DeckPreviewComponent
                        artifactId={artifact.id}
                        slides={artifact.slides || []}
                        title={artifact.title}
                        isStreaming={artifact.status === 'streaming'}
                        aspectRatio={artifact.aspectRatio}
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
                        ? "rounded-2xl rounded-tr-sm px-6 py-4 bg-white text-foreground border border-gray-200 shadow-none text-base font-medium"
                        : "text-foreground p-0 bg-transparent border-none shadow-none w-full text-left font-typewriter text-base font-medium"
                )}>
                    {shouldShowLoader ? (
                        <div className="flex items-center py-2">
                            <WaveText
                                text={loadingText ?? "Thinking..."}
                                className="text-sm font-medium text-muted-foreground"
                            />
                        </div>
                    ) : isStreaming && !isUser && !hasReasoningPart ? (
                        <div>
                            <Markdown className={cn(
                                "prose prose-base prose-tight max-w-none text-gray-800 leading-normal font-medium",
                                "font-sans",
                                "prose-p:text-gray-800 prose-p:leading-normal prose-p:font-medium prose-headings:text-gray-900 prose-strong:text-gray-900 prose-li:text-gray-800 prose-li:font-medium prose-code:text-blue-600 prose-code:bg-blue-50 prose-code:px-1 prose-code:rounded prose-code:before:content-none prose-code:after:content-none"
                            )}>{streamedText}</Markdown>
                        </div>
                    ) : (
                        <div className="flex flex-col w-full">
                            {isUser && fileParts.length > 0 && (
                                <div className="mb-3 flex flex-wrap gap-2">
                                    {fileParts.map((file, index) => {
                                        const meta = getFileTypeMeta(file.mediaType, file.filename);
                                        const Icon = meta.icon;
                                        return (
                                            <a
                                                key={`${file.url}-${index}`}
                                                href={file.url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="w-[260px] max-w-full rounded-2xl border border-border bg-muted/40 px-4 py-3 transition-colors hover:bg-muted"
                                            >
                                                <div className="truncate text-sm font-semibold text-foreground">
                                                    {file.filename || "添付ファイル"}
                                                </div>
                                                <div className="mt-3 flex items-center gap-2 text-muted-foreground">
                                                    <span className={cn("inline-flex h-8 w-8 items-center justify-center rounded-md", meta.iconClassName)}>
                                                        <Icon className="h-4 w-4" />
                                                    </span>
                                                    <span className="text-base font-semibold tracking-wide text-foreground/80">{meta.label}</span>
                                                </div>
                                            </a>
                                        );
                                    })}
                                </div>
                            )}
                            {parts && parts.length > 0 ? (
                                parts.map((part, idx) => {
                                    if (part.type === 'text' && part.text) {
                                        return (
                                            <div key={idx} className="mb-0 last:mb-0">
                                                <Markdown className={cn(
                                                    "prose prose-base prose-tight max-w-none text-gray-800 leading-normal font-medium",
                                                    !isUser && "font-sans",
                                                    "prose-p:text-gray-800 prose-p:leading-normal prose-p:font-medium prose-headings:text-gray-900 prose-strong:text-gray-900 prose-li:text-gray-800 prose-li:font-medium prose-code:text-blue-600 prose-code:bg-blue-50 prose-code:px-1 prose-code:rounded prose-code:before:content-none prose-code:after:content-none"
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
                                    if (part.type === 'file') {
                                        return null;
                                    }
                                    return null;
                                })
                            ) : (
                                <Markdown className={cn(
                                    "prose prose-base prose-tight max-w-none text-gray-800 leading-normal font-medium",
                                    !isUser && "font-sans",
                                    "prose-p:text-gray-800 prose-p:leading-normal prose-p:font-medium prose-headings:text-gray-900 prose-strong:text-gray-900 prose-li:text-gray-800 prose-li:font-medium prose-code:text-blue-600 prose-code:bg-blue-50 prose-code:px-1 prose-code:rounded prose-code:before:content-none prose-code:after:content-none"
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
