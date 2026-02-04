"use client"

import { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"
import { Check, ChevronDown, Loader2, Sparkles, FileText, Globe, AlertCircle, Terminal, Search } from "lucide-react"
import { ProcessStep, ProcessLog, ProcessSubTask } from "../../preview/types/process"
import { useArtifactStore } from "@/features/preview/stores/artifact"
import { ActionPill } from "./action-pill"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"

interface TaskAccordionProps {
    steps: ProcessStep[];
}

export function TaskAccordion({ steps }: TaskAccordionProps) {
    if (steps.length === 0) return null;

    return (
        <div className="w-full max-w-3xl mx-auto my-4">
            <div className="w-full space-y-0">
                {steps.map((step, index) => (
                    <TaskStepItem
                        key={step.id}
                        step={step}
                        isLast={index === steps.length - 1}
                    />
                ))}
            </div>
        </div>
    )
}

function TaskStepItem({ step, isLast }: { step: ProcessStep, isLast: boolean }) {
    const [open, setOpen] = useState(step.status === 'running' || Boolean(step.expanded));

    useEffect(() => {
        if (step.expanded) {
            setOpen(true);
            return;
        }
        if (step.status === 'running') {
            setOpen(true);
            return;
        }
        if (step.status === 'completed' || step.status === 'failed') {
            setOpen(false);
        }
    }, [step.expanded, step.status]);

    const getStatusIcon = () => {
        if (step.status === 'running') return <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
        if (step.status === 'completed') return <Check className="h-4 w-4 text-green-600" strokeWidth={3} />
        if (step.status === 'failed') return <AlertCircle className="h-4 w-4 text-red-600" />
        return <div className="h-2 w-2 rounded-full bg-gray-300" />
    }

    const getStatusContainerClass = () => {
        if (step.status === 'running') return "bg-blue-50 border-blue-200"
        if (step.status === 'completed') return "bg-green-50 border-green-200"
        if (step.status === 'failed') return "bg-red-50 border-red-200"
        return "bg-gray-100 border-gray-200"
    }

    const statusBadge = () => {
        if (step.status === 'running') return { label: '思考中', className: 'bg-muted text-muted-foreground border-muted-foreground/20' }
        if (step.status === 'completed') return { label: '完了', className: 'bg-muted/70 text-muted-foreground border-muted-foreground/10' }
        if (step.status === 'failed') return { label: '失敗', className: 'bg-destructive/10 text-destructive border-destructive/20' }
        return { label: '待機中', className: 'bg-muted/70 text-muted-foreground border-muted-foreground/10' }
    }

    const { label, className } = statusBadge();

    return (
        <Collapsible
            open={open}
            onOpenChange={setOpen}
            className="border-none relative group"
        >
            <div className="flex gap-4">
                {/* Left side: Icon and Spine */}
                <div className="flex flex-col items-center shrink-0 pt-1.5">
                    <div className={cn(
                        "flex items-center justify-center w-7 h-7 rounded-full border transition-colors duration-300 shadow-sm z-10 bg-white",
                        getStatusContainerClass()
                    )}>
                        {getStatusIcon()}
                    </div>
                    {!isLast && (
                        <div className="w-px grow border-l-2 border-dashed border-gray-100 mt-2" />
                    )}
                </div>

                {/* Right side: Header and Content */}
                <div className="flex-1 min-w-0">
                    <CollapsibleTrigger className="py-2 hover:bg-muted/50 px-2 -ml-2 rounded-lg transition-colors hover:no-underline w-full text-left flex items-start justify-between gap-3">
                        <div className="flex flex-col text-left min-w-0">
                            <div className="flex items-center gap-2">
                                <span className={cn(
                                    "text-base font-bold tracking-tight",
                                    step.status === 'completed' ? "text-gray-700" : "text-gray-900"
                                )}>
                                    {step.title}
                                </span>
                                <Badge variant="outline" className={cn("border", className)}>
                                    {label}
                                </Badge>
                            </div>
                            {step.description && (
                                <span className="text-sm text-muted-foreground mt-1 line-clamp-1 font-normal leading-relaxed">
                                    {step.description}
                                </span>
                            )}
                        </div>
                        <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 group-data-[state=open]:rotate-180" />
                    </CollapsibleTrigger>

                    <CollapsibleContent className="pt-1 pb-6 overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
                        <div className="space-y-1.5 text-left">
                            {/* Stream of Thought */}
                            {step.thought && (
                                <div className="mb-4">
                                    <div className="flex items-center gap-2 mb-2">
                                        <Sparkles className="h-3.5 w-3.5 text-muted-foreground" />
                                        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Thought Log</span>
                                    </div>
                                    <ThoughtStream content={step.thought} isRunning={step.status === 'running'} />
                                </div>
                            )}

                            {step.subTasks?.map((subTask) => (
                                <SubTaskItem key={subTask.id} subTask={subTask} />
                            ))}

                            {/* Logs / Actions */}
                            {step.logs.map((log) => (
                                <TaskLogItem key={log.id} log={log} />
                            ))}

                            {step.logs.length === 0 && !step.thought && step.status === 'running' && (
                                <div className="flex items-center gap-2 text-sm text-muted-foreground italic pl-1">
                                    <div className="h-2 w-2 rounded-full bg-muted-foreground/40 animate-pulse" />
                                    Waiting for output...
                                </div>
                            )}
                        </div>
                    </CollapsibleContent>
                </div>
            </div>
        </Collapsible>
    )
}

function TaskLogItem({ log }: { log: ProcessLog }) {
    const { setActiveContextId, setPreviewOpen } = useArtifactStore()
    const isClickable = log.type === 'artifact' || (log.type === 'tool' && log.title.toLowerCase().includes('search'));

    const handleClick = () => {
        if (!isClickable) return;
        const contextId = log.metadata?.id || log.runId || log.id;
        setActiveContextId(contextId);
        if (log.type === 'artifact') setPreviewOpen(true);
    }

    const isAction = log.type === 'tool' || log.type === 'artifact' || log.title.includes("生成") || log.title.includes("search");

    if (isAction) {
        let label = log.title;
        let value = "";

        if (log.title.includes(":")) {
            const parts = log.title.split(/:(.+)/);
            label = parts[0].trim();
            value = parts[1]?.trim() || "";
        }

        let Icon = Terminal;
        if (label.toLowerCase().includes("search") || label.toLowerCase().includes("閲覧")) Icon = Search;
        if (log.type === 'artifact' || label.includes("ファイル") || label.includes("画像")) Icon = FileText;
        if (label.toLowerCase().includes("page") || label.toLowerCase().includes("browse")) Icon = Globe;

        return (
            <div onClick={handleClick} className={cn("py-0.5 text-left", isClickable && "cursor-pointer")}>
                <ActionPill
                    icon={Icon}
                    label={label}
                    value={value || undefined}
                    className={cn(
                        "bg-gray-100 border-gray-200 text-gray-700",
                        log.status === 'running' && "animate-pulse border-blue-200 bg-blue-50/50"
                    )}
                />
            </div>
        )
    }

    return (
        <div className="py-1 pl-1 pr-4 text-left">
            <p className="text-[13px] text-gray-600 leading-snug whitespace-pre-wrap">
                {log.title}
            </p>
        </div>
    )
}

function ThoughtStream({ content, isRunning }: { content: string, isRunning: boolean }) {
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ block: "end" });
    }, [content]);

    return (
        <div className="relative group rounded-lg border border-muted bg-muted/50">
            <ScrollArea className="max-h-[180px]">
                <div className="px-3 py-2 pr-4 text-xs leading-relaxed text-muted-foreground font-mono whitespace-pre-wrap break-words">
                    {content}
                    {isRunning && <span className="inline-block w-1 h-3 ml-1 bg-muted-foreground/70 animate-pulse align-middle" />}
                    <span ref={bottomRef} />
                </div>
            </ScrollArea>
        </div>
    )
}

function SubTaskItem({ subTask }: { subTask: ProcessSubTask }) {
    const { setArtifact, setPreviewOpen } = useArtifactStore()
    const isCompleted = subTask.status === 'completed';

    const handleClick = () => {
        if (!isCompleted) return;
        setArtifact({
            id: subTask.id,
            type: 'markdown',
            title: `Report: ${subTask.title}`,
            content: subTask.content,
            version: 1,
            status: 'completed'
        });
        setPreviewOpen(true);
    }

    const Icon = isCompleted ? FileText : Loader2;

    return (
        <div onClick={handleClick} className={cn("py-1 flex items-center gap-2", isCompleted && "cursor-pointer")}>
            <ActionPill
                icon={Icon}
                label={subTask.title}
                value={isCompleted ? "Research Report" : "Searching..."}
                className={cn(
                    "bg-gray-50 border-gray-100 text-gray-700",
                    !isCompleted && "border-blue-100 bg-blue-50/30",
                    isCompleted && "hover:bg-gray-100 hover:border-gray-200"
                )}
            />
        </div>
    )
}
