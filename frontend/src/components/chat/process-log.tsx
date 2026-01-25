"use client"

import { useState, useEffect, useRef } from "react"
import { cn } from "@/lib/utils"
import { Check, ChevronDown, ChevronRight, Loader2, Search, FileText, Code, Database, Globe } from "lucide-react"
import { ProcessStep, ProcessLog } from "@/types/process"
import { Button } from "@/components/ui/button"

interface ProcessLogListProps {
    steps: ProcessStep[];
    onArtifactClick: (artifactId: string) => void;
}

import { motion } from "framer-motion";

export function ProcessLogList({ steps, onArtifactClick }: ProcessLogListProps) {
    // Auto-scroll logic or expand logic could go here
    return (
        <div className="flex flex-col gap-2 w-full max-w-2xl mx-auto my-4 px-2">
            {steps.map((step, index) => (
                <motion.div
                    key={step.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.05 }}
                >
                    <ProcessStepItem step={step} onArtifactClick={onArtifactClick} />
                </motion.div>
            ))}
        </div>
    )
}

function ProcessStepItem({ step, onArtifactClick }: { step: ProcessStep, onArtifactClick: (id: string) => void }) {
    const [isExpanded, setIsExpanded] = useState(step.expanded || step.status === 'running')

    // Auto-expand if requested by parent (e.g. running or manually set)
    useEffect(() => {
        setIsExpanded(step.expanded)
    }, [step.expanded])

    const getIcon = () => {
        if (step.status === 'running') return <Loader2 className="h-4 w-4 animate-spin text-primary" />
        if (step.status === 'completed') return <Check className="h-4 w-4 text-green-500" />
        return <div className="h-2 w-2 rounded-full bg-muted-foreground/30" />
    }

    return (
        <div className="border rounded-lg bg-card/50 overflow-hidden shadow-sm transition-all duration-200">
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="flex items-center w-full p-3 text-sm hover:bg-muted/50 transition-colors gap-3"
            >
                <div className="shrink-0 flex items-center justify-center w-6 h-6">
                    {getIcon()}
                </div>

                <span className={cn("font-medium flex-1 text-left", step.status === 'running' && "text-primary")}>
                    {step.title}
                </span>

                {isExpanded ? <ChevronDown className="h-4 w-4 opacity-50" /> : <ChevronRight className="h-4 w-4 opacity-50" />}
            </button>

            {isExpanded && (
                <div className="px-3 pb-3 pt-0 space-y-1 ml-9 border-l border-dashed border-muted-foreground/20 pl-4 animate-in slide-in-from-top-2 duration-200">
                    {step.logs.map((log) => (
                        <ProcessLogItem key={log.id} log={log} onArtifactClick={onArtifactClick} />
                    ))}
                    {step.logs.length === 0 && <span className="text-xs text-muted-foreground italic">Pending...</span>}
                </div>
            )}
        </div>
    )
}

function ProcessLogItem({ log, onArtifactClick }: { log: ProcessLog, onArtifactClick: (id: string) => void }) {
    const isArtifact = log.type === 'artifact'

    const getIcon = () => {
        if (log.title.includes("search") || log.title.includes("Search")) return <Globe className="h-3 w-3" />
        if (log.type === 'artifact') return <FileText className="h-3 w-3" />
        return <Code className="h-3 w-3" />
    }

    return (
        <div className={cn(
            "flex items-center gap-2 text-xs py-1.5 px-2 rounded-md group transition-colors",
            isArtifact ? "bg-primary/5 hover:bg-primary/10 cursor-pointer border border-primary/10" : "text-muted-foreground"
        )}
            onClick={() => isArtifact && onArtifactClick(log.metadata?.id)}
        >
            <div className={cn("shrink-0", log.status === 'running' && "animate-pulse")}>
                {log.status === 'running' ? <Loader2 className="h-3 w-3 animate-spin" /> : getIcon()}
            </div>

            <div className="flex-1 truncate flex items-center gap-2">
                <span className="font-medium">{log.title}</span>
                {log.progress?.message && (
                    <span className="text-muted-foreground/80 font-normal">
                        - {log.progress.message}
                    </span>
                )}
            </div>

            {isArtifact && <ChevronRight className="h-3 w-3 opacity-0 group-hover:opacity-50 transition-opacity" />}
        </div>
    )
}
