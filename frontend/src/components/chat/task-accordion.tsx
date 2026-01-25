"use client"

import { useState, useEffect } from "react"
import { cn } from "@/lib/utils"
import { Check, ChevronDown, ChevronRight, Loader2, Sparkles, FileText, Code, Globe, AlertCircle } from "lucide-react"
import { ProcessStep, ProcessLog } from "@/types/process"
import { motion, AnimatePresence } from "framer-motion"
import { useArtifactStore } from "@/store/artifact"

interface TaskAccordionProps {
    steps: ProcessStep[];
    isRunning?: boolean;
}

export function TaskAccordion({ steps, isRunning }: TaskAccordionProps) {
    // If there are no steps, don't render anything
    if (steps.length === 0) return null;

    return (
        <div className="w-full max-w-3xl mx-auto my-6 px-4">
            <div className="border border-white/10 rounded-xl bg-black/20 backdrop-blur-sm overflow-hidden">
                {/* Header / Summary */}
                <div className="p-3 bg-white/5 border-b border-white/5 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                        <Sparkles className={cn("h-4 w-4", isRunning ? "text-primary animate-pulse" : "text-muted-foreground")} />
                        <span>AI Process</span>
                    </div>
                    {isRunning && <span className="text-xs text-primary animate-pulse">Running...</span>}
                </div>

                {/* Steps List */}
                <div className="flex flex-col">
                    {steps.map((step, index) => (
                        <TaskStepItem key={step.id} step={step} isLast={index === steps.length - 1} />
                    ))}
                </div>
            </div>
        </div>
    )
}

function TaskStepItem({ step, isLast }: { step: ProcessStep, isLast: boolean }) {
    const [isExpanded, setIsExpanded] = useState(step.expanded || step.status === 'running')

    // Auto-expand/collapse based on status
    useEffect(() => {
        if (step.status === 'running') setIsExpanded(true);
        // We generally default to keeping it expanded if it has interesting logs, 
        // but can collapse on complete if it's too long. For now, respect `step.expanded`.
    }, [step.status])

    const getIcon = () => {
        if (step.status === 'running') return <Loader2 className="h-4 w-4 animate-spin text-primary" />
        if (step.status === 'completed') return <Check className="h-4 w-4 text-green-500" />
        if (step.status === 'failed') return <AlertCircle className="h-4 w-4 text-red-500" />
        return <div className="h-2 w-2 rounded-full bg-muted-foreground/30" />
    }

    return (
        <div className={cn("flex flex-col transition-colors", !isLast && "border-b border-white/5")}>
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="flex items-center w-full p-3 text-sm hover:bg-white/5 transition-colors gap-3 select-none"
            >
                <div className="shrink-0 flex items-center justify-center w-6 h-6">
                    {getIcon()}
                </div>

                <div className="flex-1 text-left flex flex-col">
                    <span className={cn("font-medium", step.status === 'running' && "text-foreground", step.status === 'completed' && "text-muted-foreground")}>
                        {step.title}
                    </span>
                    {step.description && (
                        <span className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                            {step.description}
                        </span>
                    )}
                    {step.status === 'running' && (
                        <span className="text-xs text-primary/80 animate-pulse">Processing...</span>
                    )}
                </div>

                <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform duration-200", !isExpanded && "-rotate-90")} />
            </button>

            <AnimatePresence>
                {isExpanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden bg-black/10"
                    >
                        <div className="px-3 pb-3 pt-0 ml-9 border-l border-white/5 pl-4 space-y-1">
                            {step.logs.map((log) => (
                                <TaskLogItem key={log.id} log={log} />
                            ))}
                            {step.logs.length === 0 && step.status === 'running' && (
                                <span className="text-xs text-muted-foreground italic pl-2">Waiting for output...</span>
                            )}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    )
}

function TaskLogItem({ log }: { log: ProcessLog }) {
    const { setActiveContextId, setPreviewOpen } = useArtifactStore()
    const isClickable = log.type === 'artifact' || (log.type === 'tool' && log.title.toLowerCase().includes('search'));

    const handleClick = () => {
        if (!isClickable) return;

        // Manual Priority: Set active context ID
        // If it's an artifact, use its metadata ID.
        // If it's a tool, use its runId or logId.
        const contextId = log.metadata?.id || log.runId || log.id;
        setActiveContextId(contextId);

        // If it's an artifact, ensure preview is open
        if (log.type === 'artifact') {
            setPreviewOpen(true);
        }
    }

    const getIcon = () => {
        if (log.title.toLowerCase().includes("search")) return <Globe className="h-3 w-3" />
        if (log.type === 'artifact') return <FileText className="h-3 w-3" />
        return <Code className="h-3 w-3" />
    }

    return (
        <div
            onClick={handleClick}
            className={cn(
                "flex items-center gap-2 text-xs py-1.5 px-2 rounded-md group transition-all duration-200 border border-transparent",
                isClickable
                    ? "cursor-pointer hover:bg-primary/10 hover:border-primary/20 hover:shadow-sm"
                    : "text-muted-foreground"
            )}
        >
            <div className={cn("shrink-0", log.status === 'running' && "animate-pulse")}>
                {log.status === 'running' ? <Loader2 className="h-3 w-3 animate-spin" /> : getIcon()}
            </div>

            <div className="flex-1 truncate flex items-center gap-2">
                <span className={cn("font-medium", isClickable && "text-primary/90 group-hover:text-primary")}>
                    {log.title}
                </span>
                {log.progress?.message && (
                    <span className="text-muted-foreground/80 font-normal">
                        - {log.progress.message}
                    </span>
                )}
            </div>

            {isClickable && <ChevronRight className="h-3 w-3 opacity-0 group-hover:opacity-100 text-primary transition-opacity" />}
        </div>
    )
}
