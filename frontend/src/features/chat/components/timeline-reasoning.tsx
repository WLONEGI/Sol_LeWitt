"use client"

import { useEffect, useState, useMemo } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Markdown } from "@/components/ui/markdown";
import { motion, AnimatePresence } from "framer-motion";

interface TimelineReasoningProps {
    content: string;
    isLastInSequence: boolean;
    isStreaming?: boolean;
    className?: string;
}

/**
 * テキストから最新の太字（**...**）を抽出する
 */
const extractLatestStep = (text: string): string | null => {
    // 最新の太字（**...**）を取得するために、後ろから検索するか全てのマッチから最後を選択
    const matches = Array.from(text.matchAll(/\*\*(.*?)\*\*/g));
    if (matches.length > 0) {
        return matches[matches.length - 1][1];
    }
    return null;
};

export function TimelineReasoning({ content, isLastInSequence, isStreaming = false, className }: TimelineReasoningProps) {
    const [open, setOpen] = useState(isStreaming);

    // 思考中か完了かのステータスを監視し、自動で開閉する
    useEffect(() => {
        if (isStreaming) {
            setOpen(true);
        } else {
            // ストリーミングが終了した瞬間に閉じる
            setOpen(false);
        }
    }, [isStreaming]);

    // タイトルの決定：最新の太字があればそれを採用、なければ「思考中...」
    const currentStep = useMemo(() => extractLatestStep(content), [content]);
    const displayTitle = currentStep || "思考中...";

    return (
        <div className={cn("w-full my-1 text-left", className)}>
            <Collapsible open={open} onOpenChange={setOpen} className="w-full">
                <CollapsibleTrigger className="flex items-center gap-1.5 py-1 px-1 rounded-md hover:opacity-70 transition-opacity text-sm text-muted-foreground group">
                    <AnimatePresence mode="wait">
                        <motion.span
                            key={displayTitle}
                            initial={{ opacity: 0, y: 4 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -4 }}
                            transition={{ duration: 0.3, ease: "easeOut" }}
                            className="font-bold text-foreground font-sans"
                        >
                            {displayTitle}
                        </motion.span>
                    </AnimatePresence>
                    <ChevronDown className={cn(
                        "h-4 w-4 transition-transform duration-200 stroke-[2.5px]",
                        open && "rotate-180"
                    )} />
                </CollapsibleTrigger>

                <CollapsibleContent className="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
                    <div className="mt-1 relative pl-4 bg-transparent border-none">
                        {/* 左側の細いアクセント線（Gemini風） */}
                        <div className="absolute left-1 top-0 bottom-0 w-0.5 bg-muted-foreground/20 rounded-full" />

                        <div className="py-1">
                            {/* 思考ログのフォントを本文に合わせる（斜体・Serif削除） */}
                            <div className="text-sm text-muted-foreground leading-relaxed">
                                <Markdown
                                    className="prose prose-sm dark:prose-invert max-w-none text-muted-foreground/90 border-none shadow-none prose-p:my-1"
                                >
                                    {content}
                                </Markdown>
                            </div>
                        </div>
                    </div>
                </CollapsibleContent>
            </Collapsible>
        </div>
    );
}
