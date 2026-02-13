"use client"

import { useMemo, useState } from "react"
import { AlertTriangle, BookText, ChevronDown, ChevronUp, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { normalizeStoryFrameworkContent } from "@/features/preview/lib/writer-output-normalizers"

interface WriterStoryFrameworkCardProps {
    title?: string;
    status?: string;
    content?: any;
    className?: string;
}

type TaskStatus = "running" | "completed" | "failed";

function normalizeTaskStatus(status?: string, hasContent?: boolean): TaskStatus {
    const normalized = (status || "").toLowerCase();
    if (normalized === "failed" || normalized === "error") return "failed";
    if (normalized === "completed" || normalized === "success") return "completed";
    if (normalized === "running" || normalized === "streaming" || normalized === "in_progress" || normalized === "pending") {
        return "running";
    }
    return hasContent ? "completed" : "running";
}

function CompactField({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-md border border-border/70 bg-background px-2 py-1.5">
            <div className="text-[10px] text-muted-foreground">{label}</div>
            <div className="mt-0.5 text-[12px] leading-snug whitespace-pre-wrap break-words">
                {value || "未設定"}
            </div>
        </div>
    );
}

export function WriterStoryFrameworkCard({
    title,
    status,
    content,
    className,
}: WriterStoryFrameworkCardProps) {
    const normalized = useMemo(() => normalizeStoryFrameworkContent(content), [content]);
    const taskStatus = useMemo(() => normalizeTaskStatus(status, normalized.hasContent), [status, normalized.hasContent]);
    const [open, setOpen] = useState(taskStatus !== "completed");

    const formatTags = [
        normalized.format.seriesType,
        normalized.format.medium,
        normalized.format.readingDirection,
        normalized.format.pageBudgetText,
    ].filter((item) => item.length > 0);
    const worldTags = [
        normalized.world.era,
        ...normalized.world.primaryLocations,
        ...normalized.world.socialRules,
    ].filter((item) => item.length > 0);

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
                            <BookText className="h-4 w-4 text-muted-foreground" />
                        )}
                        <div className="truncate text-[13px] font-semibold">
                            {title || "Story Framework"}
                        </div>
                    </div>
                    <CollapsibleTrigger
                        className="inline-flex h-6 w-6 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-muted"
                        aria-label={open ? "Collapse details" : "Expand details"}
                    >
                        {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                    </CollapsibleTrigger>
                </div>

                <CollapsibleContent className="min-w-0 overflow-hidden">
                    <div className="mt-2 space-y-2">
                        <div className="grid gap-1.5 sm:grid-cols-2">
                            <CompactField label="コンセプト" value={normalized.concept} />
                            <CompactField label="テーマ" value={normalized.theme} />
                            <CompactField label="コア対立" value={normalized.coreConflict} />
                            <CompactField label="世界観" value={worldTags.join(" / ")} />
                        </div>

                        {formatTags.length > 0 ? (
                            <div className="rounded-md border border-border/70 bg-background px-2 py-1.5">
                                <div className="text-[10px] text-muted-foreground">フォーマット</div>
                                <div className="mt-1 flex flex-wrap gap-1">
                                    {formatTags.map((tag, index) => (
                                        <span key={`format-${index}`} className="rounded-full bg-muted px-2 py-0.5 text-[11px]">
                                            {tag}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        ) : null}

                        {normalized.arcOverview.length > 0 ? (
                            <div className="rounded-md border border-border/70 bg-background px-2 py-1.5">
                                <div className="mb-1 text-[10px] text-muted-foreground">物語アーク</div>
                                <div className="space-y-1">
                                    {normalized.arcOverview.map((step, index) => (
                                        <div key={`arc-${index}`} className="grid grid-cols-[auto_1fr] gap-2 text-[12px] leading-snug">
                                            <span className="text-muted-foreground">{step.phase}.</span>
                                            <span className="break-words">{step.purpose}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ) : null}

                        {normalized.artStylePolicy.negativeConstraints.length > 0 ? (
                            <div className="rounded-md border border-border/70 bg-background px-2 py-1.5">
                                <div className="text-[10px] text-muted-foreground">禁止事項</div>
                                <div className="mt-1 flex flex-wrap gap-1">
                                    {normalized.artStylePolicy.negativeConstraints.map((item, index) => (
                                        <span key={`neg-${index}`} className="rounded-full bg-muted px-2 py-0.5 text-[11px]">
                                            {item}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        ) : null}
                    </div>
                </CollapsibleContent>
            </div>
        </Collapsible>
    )
}
