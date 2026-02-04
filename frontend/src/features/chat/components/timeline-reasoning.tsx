"use client"

import { useEffect, useState } from "react";
import { Brain, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Markdown } from "@/components/ui/markdown";

interface TimelineReasoningProps {
    content: string;
    isLastInSequence: boolean;
    isStreaming?: boolean;
    className?: string;
}

export function TimelineReasoning({ content, isLastInSequence, isStreaming = false, className }: TimelineReasoningProps) {
    const [open, setOpen] = useState(isStreaming);

    useEffect(() => {
        if (isStreaming) {
            setOpen(true);
            return;
        }
        setOpen(false);
    }, [isStreaming]);

    const statusLabel = isStreaming ? "思考中" : "完了";

    return (
        <div className={cn("w-full my-2 text-left", className)}>
            <Collapsible open={open} onOpenChange={setOpen} className="w-full group">
                <CollapsibleTrigger className="flex items-center justify-between gap-3 py-2 px-2 rounded-md hover:bg-muted/50 transition-colors text-sm text-muted-foreground">
                    <div className="flex items-center gap-2">
                        <div className="flex items-center justify-center w-6 h-6 rounded-md bg-muted border shrink-0">
                            <Brain className="h-3.5 w-3.5" />
                        </div>
                        <span className="font-medium">思考ログ</span>
                        <Badge variant="outline" className="border-muted-foreground/20 text-muted-foreground bg-muted/60">
                            {statusLabel}
                        </Badge>
                    </div>
                    <ChevronDown className="h-4 w-4 transition-transform duration-200 group-data-[state=open]:rotate-180" />
                </CollapsibleTrigger>
                <CollapsibleContent className="mt-1 overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
                    <div className="rounded-lg border border-muted bg-muted/50">
                        <ScrollArea className="max-h-[200px]">
                            <div className="px-3 py-2 text-xs leading-relaxed text-muted-foreground font-mono whitespace-pre-wrap break-words">
                                <Markdown className="prose prose-sm dark:prose-invert max-w-none text-muted-foreground font-mono prose-p:my-1">
                                    {content}
                                </Markdown>
                            </div>
                        </ScrollArea>
                    </div>
                </CollapsibleContent>
            </Collapsible>
        </div>
    );
}
