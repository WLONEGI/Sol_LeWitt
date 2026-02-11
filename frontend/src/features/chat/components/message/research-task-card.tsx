"use client"

import { Search } from "lucide-react"
import { cn } from "@/lib/utils"
import { Markdown } from "@/components/ui/markdown"

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
    searchMode,
    report,
    sources = [],
}: ResearchTaskCardProps) {
    const statusLabel =
        status === "running" ? "Running" : status === "failed" ? "Failed" : "Completed"

    return (
        <div className="w-full rounded-2xl border border-border bg-card px-4 py-3">
            <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                    <Search className="h-4 w-4 text-muted-foreground" />
                    <div className="truncate text-sm font-semibold">{perspective || `Task ${taskId}`}</div>
                </div>
                <div
                    className={cn(
                        "rounded-full px-2 py-0.5 text-[10px] font-semibold",
                        status === "running" && "bg-amber-100 text-amber-700",
                        status === "completed" && "bg-emerald-100 text-emerald-700",
                        status === "failed" && "bg-rose-100 text-rose-700",
                    )}
                >
                    {statusLabel}
                </div>
            </div>

            <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                <span>ID: {taskId}</span>
                {searchMode ? <span>mode: {searchMode}</span> : null}
            </div>

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
        </div>
    )
}

