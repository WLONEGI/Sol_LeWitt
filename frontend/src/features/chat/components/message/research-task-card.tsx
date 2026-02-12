"use client"

import { useState } from "react"
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, Loader2, Search } from "lucide-react"
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
}

export function ResearchTaskCard({
    taskId,
    perspective,
    status,
    searchMode: _searchMode,
    report,
    sources = [],
}: ResearchTaskCardProps) {
    const [open, setOpen] = useState(status !== "completed")

    return (
        <Collapsible open={open} onOpenChange={setOpen}>
            <div className="w-full rounded-2xl border border-border bg-card px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2">
                        <Search className="h-4 w-4 text-muted-foreground" />
                        <div className="truncate text-sm font-semibold">{perspective || "Research Task"}</div>
                    </div>
                    <div className="flex items-center gap-2">
                        <div
                            className={cn(
                                "inline-flex h-6 w-6 items-center justify-center rounded-full",
                                status === "running" && "bg-amber-100 text-amber-700",
                                status === "completed" && "bg-emerald-100 text-emerald-700",
                                status === "failed" && "bg-rose-100 text-rose-700",
                            )}
                            aria-label={status}
                            title={status}
                        >
                            {status === "running" ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : status === "failed" ? (
                                <AlertTriangle className="h-3.5 w-3.5" />
                            ) : (
                                <CheckCircle2 className="h-3.5 w-3.5" />
                            )}
                        </div>
                        <CollapsibleTrigger
                            className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-muted"
                            aria-label={open ? "Collapse report" : "Expand report"}
                        >
                            {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                        </CollapsibleTrigger>
                    </div>
                </div>

                <CollapsibleContent>
                    {report ? (
                        <div className="mt-3 rounded-xl border border-border/70 bg-background px-3 py-2">
                            <Markdown className="prose prose-sm max-w-none text-foreground">
                                {report}
                            </Markdown>
                        </div>
                    ) : null}

                    {sources.length > 0 ? (
                        <div className="mt-3">
                            <div className="mb-1 text-xs font-semibold text-muted-foreground">Sources</div>
                            <div className="flex flex-col gap-1">
                                {sources.map((source, idx) => (
                                    <a
                                        key={`${taskId}-source-${idx}`}
                                        href={source}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="truncate text-xs text-sky-700 hover:underline"
                                    >
                                        {source}
                                    </a>
                                ))}
                            </div>
                        </div>
                    ) : null}
                </CollapsibleContent>
            </div>
        </Collapsible>
    )
}
