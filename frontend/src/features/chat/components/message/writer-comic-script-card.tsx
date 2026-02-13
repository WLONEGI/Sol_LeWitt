"use client"

import { useMemo, useState } from "react"
import { AlertTriangle, BookOpen, ChevronDown, ChevronUp, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { normalizeComicScriptContent } from "@/features/preview/lib/writer-output-normalizers"

interface WriterComicScriptCardProps {
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

export function WriterComicScriptCard({
    title,
    status,
    content,
    className,
}: WriterComicScriptCardProps) {
    const normalized = useMemo(() => normalizeComicScriptContent(content), [content]);
    const taskStatus = useMemo(() => normalizeTaskStatus(status, normalized.hasContent), [status, normalized.hasContent]);
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
                            <BookOpen className="h-4 w-4 text-muted-foreground" />
                        )}
                        <div className="truncate text-[13px] font-semibold">
                            {title || "Comic Script"}
                        </div>
                    </div>
                    <CollapsibleTrigger
                        className="inline-flex h-6 w-6 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-muted"
                        aria-label={open ? "Collapse details" : "Expand details"}
                    >
                        {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                    </CollapsibleTrigger>
                </div>

                <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-muted-foreground">
                    <span className="rounded-full border border-border px-2 py-0.5">{normalized.pageCount}ページ</span>
                    <span className="rounded-full border border-border px-2 py-0.5">{normalized.panelCount}コマ</span>
                </div>

                <CollapsibleContent className="min-w-0 overflow-hidden">
                    <div className="mt-2">
                        {normalized.pages.length === 0 ? (
                            <div className="rounded-md border border-border/70 bg-background px-2 py-1.5 text-[12px] text-muted-foreground">
                                コマ情報の生成を待機しています。
                            </div>
                        ) : (
                            <Accordion type="multiple" className="space-y-1">
                                {normalized.pages.map((page, pageIndex) => (
                                    <AccordionItem
                                        key={`page-${page.pageNumber}-${pageIndex}`}
                                        value={`page-${page.pageNumber}-${pageIndex}`}
                                        className="rounded-md border border-border/70 bg-background px-2 last:border-b"
                                    >
                                        <AccordionTrigger className="py-2 text-left text-[12px] leading-snug hover:no-underline">
                                            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                                                <span className="rounded-full bg-muted px-2 py-0.5 text-[10px]">
                                                    Page {page.pageNumber}
                                                </span>
                                                {page.pageGoal ? (
                                                    <span className="min-w-0 break-words text-[12px] font-medium">{page.pageGoal}</span>
                                                ) : null}
                                                <span className="text-[10px] text-muted-foreground">{page.panels.length}コマ</span>
                                            </div>
                                        </AccordionTrigger>
                                        <AccordionContent className="pb-2">
                                            <div className="space-y-1.5">
                                                {page.panels.map((panel, panelIndex) => {
                                                    const primaryLine = [panel.foreground, panel.background]
                                                        .filter((item) => item.length > 0)
                                                        .join(" / ");
                                                    const detailLine = [panel.composition, panel.camera, panel.lighting]
                                                        .filter((item) => item.length > 0)
                                                        .join(" / ");
                                                    return (
                                                        <div
                                                            key={`panel-${page.pageNumber}-${panel.panelNumber}-${panelIndex}`}
                                                            className="rounded-md border border-border/70 px-2 py-1.5"
                                                        >
                                                            <div className="flex flex-wrap items-center gap-1.5">
                                                                <span className="rounded-full bg-muted px-2 py-0.5 text-[10px]">
                                                                    Panel {panel.panelNumber}
                                                                </span>
                                                            </div>
                                                            {primaryLine ? (
                                                                <div className="mt-1 text-[12px] leading-snug break-words">{primaryLine}</div>
                                                            ) : null}
                                                            {detailLine ? (
                                                                <div className="mt-1 text-[11px] leading-snug text-muted-foreground break-words">
                                                                    {detailLine}
                                                                </div>
                                                            ) : null}
                                                            {panel.dialogue.length > 0 ? (
                                                                <div className="mt-1 space-y-0.5">
                                                                    {panel.dialogue.slice(0, 2).map((line, lineIndex) => (
                                                                        <div
                                                                            key={`dialogue-${panel.panelNumber}-${lineIndex}`}
                                                                            className="rounded bg-muted/70 px-1.5 py-1 text-[11px] leading-snug break-words"
                                                                        >
                                                                            {line}
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            ) : null}
                                                            {panel.negativeConstraints.length > 0 ? (
                                                                <div className="mt-1 flex flex-wrap gap-1">
                                                                    {panel.negativeConstraints.slice(0, 4).map((constraint, constraintIndex) => (
                                                                        <span
                                                                            key={`constraint-${panel.panelNumber}-${constraintIndex}`}
                                                                            className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground"
                                                                        >
                                                                            {constraint}
                                                                        </span>
                                                                    ))}
                                                                </div>
                                                            ) : null}
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </AccordionContent>
                                    </AccordionItem>
                                ))}
                            </Accordion>
                        )}
                    </div>
                </CollapsibleContent>
            </div>
        </Collapsible>
    )
}
