"use client"

import { useState } from "react"
import { AlertTriangle, ChevronDown, ChevronUp, Loader2, Search } from "lucide-react"
import { cn } from "@/lib/utils"
import { Markdown } from "@/components/ui/markdown"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"

interface ResearchTaskCardProps {
    taskId: string;
    perspective: string;
    status: 'running' | 'completed' | 'failed';
    searchMode?: string;
    report?: string;
    sources?: string[];
    className?: string;
}

export function ResearchTaskCard({
    taskId,
    perspective,
    status,
    searchMode: _searchMode,
    report,
    sources = [],
    className,
}: ResearchTaskCardProps) {
    void taskId
    void sources
    const [open, setOpen] = useState(status !== "completed")

    return (
        <Collapsible open={open} onOpenChange={setOpen} className={cn("w-full", className)}>
            <div className="w-full rounded-2xl border border-border bg-card px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2">
                        {status === "running" ? (
                            <Loader2 className="h-4 w-4 animate-spin text-amber-600" />
                        ) : status === "failed" ? (
                            <AlertTriangle className="h-4 w-4 text-rose-600" />
                        ) : (
                            <Search className="h-4 w-4 text-muted-foreground" />
                        )}
                        <div className="truncate text-sm font-semibold">{perspective || "Research Task"}</div>
                    </div>
                    <div className="flex items-center gap-2">
                        <CollapsibleTrigger
                            className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-muted"
                            aria-label={open ? "Collapse report" : "Expand report"}
                        >
                            {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                        </CollapsibleTrigger>
                    </div>
                </div>

                <CollapsibleContent className="min-w-0 overflow-hidden">
                    {report ? (
                        <div className="mt-3 min-w-0 overflow-hidden rounded-xl border border-border/70 bg-background px-3 py-2">
                            <Markdown
                                className="prose prose-sm max-w-none text-foreground [overflow-wrap:anywhere] break-words [&_a]:break-all [&_a]:whitespace-normal"
                            >
                                {report}
                            </Markdown>
                        </div>
                    ) : null}
                </CollapsibleContent>
            </div>
        </Collapsible>
    )
}
