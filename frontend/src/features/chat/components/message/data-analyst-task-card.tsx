"use client"

import { useMemo, useState } from "react"
import { AlertTriangle, ChevronDown, ChevronUp, Loader2, TerminalSquare } from "lucide-react"
import { cn } from "@/lib/utils"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { DataAnalystViewer } from "@/features/preview/viewers/data-analyst-viewer"

interface DataAnalystTaskCardProps {
    title?: string;
    status?: string;
    content?: any;
    className?: string;
}

type TaskStatus = "running" | "completed" | "failed";

function normalizeTaskStatus(status?: string): TaskStatus {
    const normalized = (status || "").toLowerCase();
    if (normalized === "completed" || normalized === "success") return "completed";
    if (normalized === "failed" || normalized === "error") return "failed";
    return "running";
}

export function DataAnalystTaskCard({
    title,
    status,
    content,
    className,
}: DataAnalystTaskCardProps) {
    const taskStatus = useMemo(() => normalizeTaskStatus(status), [status]);
    const [open, setOpen] = useState(taskStatus !== "completed");

    return (
        <Collapsible open={open} onOpenChange={setOpen} className={cn("w-full", className)}>
            <div className="w-full rounded-2xl border border-border bg-card px-3 py-2.5">
                <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-1.5">
                        {taskStatus === "running" ? (
                            <Loader2 className="h-4 w-4 animate-spin text-indigo-600" />
                        ) : taskStatus === "failed" ? (
                            <AlertTriangle className="h-4 w-4 text-rose-600" />
                        ) : (
                            <TerminalSquare className="h-4 w-4 text-muted-foreground" />
                        )}
                        <div className="truncate text-[13px] font-semibold">
                            {title || "Data Analyst"}
                        </div>
                    </div>
                    <div className="flex items-center gap-1">
                        <CollapsibleTrigger
                            className="inline-flex h-6 w-6 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-muted"
                            aria-label={open ? "Collapse details" : "Expand details"}
                        >
                            {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                        </CollapsibleTrigger>
                    </div>
                </div>

                <CollapsibleContent className="min-w-0 overflow-hidden">
                    <div className="mt-2">
                        <DataAnalystViewer content={content} embedded />
                    </div>
                </CollapsibleContent>
            </div>
        </Collapsible>
    )
}
