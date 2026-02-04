"use client"

import { Brain, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Markdown } from "@/components/ui/markdown";

interface TimelineReasoningProps {
    content: string;
    isLastInSequence: boolean;
    className?: string;
}

export function TimelineReasoning({ content, isLastInSequence, className }: TimelineReasoningProps) {
    return (
        <div className={cn("w-full my-3", className)}>
            <Collapsible className="w-full group">
                <CollapsibleTrigger className="flex items-center gap-2 py-2 px-3 rounded-lg hover:bg-muted/50 transition-colors text-sm font-medium text-muted-foreground hover:text-foreground">
                    <div className="flex items-center justify-center w-6 h-6 rounded-md bg-muted border shrink-0">
                        <Brain className="h-3.5 w-3.5" />
                    </div>
                    <span>Thought Process</span>
                    <ChevronDown className="h-4 w-4 transition-transform duration-200 group-data-[state=open]:rotate-180" />
                </CollapsibleTrigger>
                <CollapsibleContent className="mt-2 overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
                    <div className="pl-6 ml-3 border-l-2 border-muted py-2">
                        <Markdown className="prose prose-sm dark:prose-invert max-w-none text-muted-foreground/90 leading-relaxed italic">
                            {content}
                        </Markdown>
                    </div>
                </CollapsibleContent>
            </Collapsible>
        </div>
    );
}
