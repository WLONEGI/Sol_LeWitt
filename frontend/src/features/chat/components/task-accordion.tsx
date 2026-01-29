"use client"

import { useState, useEffect, useRef } from "react"
import { cn } from "@/lib/utils"
import { Check, ChevronDown, ChevronRight, Loader2, Sparkles, FileText, Code, Globe, AlertCircle, Terminal, Search, File } from "lucide-react"
import { ProcessStep, ProcessLog, ProcessSubTask } from "../../preview/types/process"
import { motion, AnimatePresence } from "framer-motion"
import { useArtifactStore } from "../../preview/store/artifact"
import { ActionPill } from "./action-pill"

interface TaskAccordionProps {
    steps: ProcessStep[];
    isRunning?: boolean;
}

export function TaskAccordion({ steps, isRunning }: TaskAccordionProps) {
    if (steps.length === 0) return null;

    return (
        <div className="w-full max-w-3xl mx-auto my-4 transition-all duration-500 ease-in-out">
            <div className="flex flex-col space-y-0">
                {steps.map((step, index) => (
                    <TaskStepItem key={step.id} step={step} isLast={index === steps.length - 1} />
                ))}
            </div>
        </div>
    )
}

function TaskStepItem({ step, isLast }: { step: ProcessStep, isLast: boolean }) {
    const [isExpanded, setIsExpanded] = useState(step.expanded || step.status === 'running')

    useEffect(() => {
        if (step.status === 'running') setIsExpanded(true);
    }, [step.status])

    const getStatusIcon = () => {
        if (step.status === 'running') return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
        if (step.status === 'completed') return <Check className="h-4 w-4 text-white" />
        if (step.status === 'failed') return <AlertCircle className="h-4 w-4 text-white" />
        return <div className="h-2 w-2 rounded-full bg-gray-300" />
    }

    const getStatusContainerClass = () => {
        if (step.status === 'running') return "bg-white border-2 border-blue-100"
        if (step.status === 'completed') return "bg-gray-200 border-2 border-gray-100" // Completed Node: bg-gray-200 + white check (as requested)
        if (step.status === 'failed') return "bg-red-500 border-2 border-red-400"
        return "bg-gray-100 border-2 border-gray-50"
    }

    return (
        <div className="relative group">
            {/* Header: Parent Node */}
            <div className="flex items-start gap-4 py-2">
                {/* Status Indicator (The Node on the Spine) */}
                <div className="relative z-10 flex flex-col items-center mt-1">
                    <div className={cn(
                        "flex items-center justify-center w-6 h-6 rounded-full transition-colors duration-300",
                        getStatusContainerClass()
                    )}>
                        {getStatusIcon()}
                    </div>
                </div>

                {/* Content Header */}
                <button
                    onClick={() => setIsExpanded(!isExpanded)}
                    className="flex-1 flex items-center justify-between text-left group-hover:bg-gray-50/50 p-1.5 -ml-1.5 rounded-md transition-colors cursor-pointer"
                >
                    <div className="flex flex-col">
                        <span className={cn(
                            "text-sm font-bold tracking-tight transition-colors", // Parent Typography: Bold
                            step.status === 'completed' ? "text-gray-700" : "text-gray-900"
                        )}>
                            {step.title}
                        </span>
                        {step.description && (
                            <span className="text-xs text-gray-500 mt-0.5 line-clamp-1 font-normal leading-relaxed">
                                {step.description}
                            </span>
                        )}
                    </div>

                    <div className="flex items-center gap-2">

                        <ChevronDown className={cn("h-4 w-4 text-gray-400 transition-transform duration-200", !isExpanded && "-rotate-90")} />
                    </div>
                </button>
            </div>

            {/* Body: Connector Line & Children */}
            <div className="flex">
                {/* The Spine (Dashed Line) */}
                {/* Using a separate div for the line to strictly control position */}
                <div className="w-6 flex justify-center shrink-0">
                    {/* 
                       Line logic: 
                       - Connected to the node above.
                       - Dashed as requested.
                       - Should stop if it's the last item AND collapsed? 
                       - Actually, if it's open, line continues to cover children.
                       - If there are multiple steps, the line connects to the NEXT step using the parent's context?
                       - Current design: This line handles the "Child" connection for THIS step.
                     */}
                    <div className={cn(
                        "w-px h-full border-l-2 border-dashed border-gray-200 -ml-[2px]", // Adjust styling to match request
                        !isExpanded && "h-0 hidden" // Hide line if collapsed (unless we want it to connect to next sibling?)
                        // Note: If we want a continuous spine across siblings, that requires a parent container line.
                        // Im implementing the "Nested Indentation" line here.
                    )} />
                </div>

                {/* Children Content */}
                <AnimatePresence>
                    {isExpanded && (
                        <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            exit={{ opacity: 0, height: 0 }}
                            transition={{ duration: 0.2 }}
                            className="flex-1 overflow-hidden"
                        >
                            <div className="pb-6 pl-2 space-y-3 pt-1">
                                {/* Stream of Thought */}
                                {step.thought && (
                                    <div className="mb-4">
                                        <div className="flex items-center gap-2 mb-2">
                                            <Sparkles className="h-3 w-3 text-gray-400" />
                                            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Reasoning</span>
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
                                    <div className="flex items-center gap-2 text-xs text-gray-400 italic pl-1">
                                        <div className="h-1.5 w-1.5 rounded-full bg-gray-300 animate-pulse" />
                                        Waiting for output...
                                    </div>
                                )}
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>

            {/* Connector to next sibling if not last? 
                If we want a continuous spine across steps, we need an overlay or a line in the parent container.
                But based on the "Nested Indentation", the Line usually implies hierarchy.
                Let's add a subtle connector for siblings if needed, but for now focusing on the "Child" indentation line.
            */}
        </div>
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

    // Determine if this is a "System Action" (Pill) or "Text Log" (Paragraph)
    const isAction = log.type === 'tool' || log.type === 'artifact' || log.title.includes("生成") || log.title.includes("search");

    if (isAction) {
        // Parse Title for ActionPill (e.g., "google_search: query" -> Label: google_search, Value: query)
        let label = log.title;
        let value = "";

        // Simple heuristic parsing
        if (log.title.includes(":")) {
            const parts = log.title.split(/:(.+)/);
            label = parts[0].trim();
            value = parts[1]?.trim() || "";
        } else if (log.title.includes(" ")) {
            // Maybe "Generating image..." -> Label: Generating, Value: image... (Optional, keeping simple for now)
        }

        // Map icons
        let Icon = Terminal;
        if (label.toLowerCase().includes("search") || label.toLowerCase().includes("閲覧")) Icon = Search;
        if (log.type === 'artifact' || label.includes("ファイル") || label.includes("画像")) Icon = FileText;
        if (label.toLowerCase().includes("page") || label.toLowerCase().includes("browse")) Icon = Globe;

        return (
            <div onClick={handleClick} className={cn("py-1", isClickable && "cursor-pointer")}>
                <ActionPill
                    icon={Icon}
                    label={label}
                    value={value || undefined}
                    className={cn(
                        "bg-gray-100 border-gray-200 text-gray-700",
                        log.status === 'running' && "animate-pulse border-blue-200 bg-blue-50/50"
                    )}
                />
                {log.progress?.message && (
                    <div className="ml-8 mt-1 text-xs text-gray-400">
                        {log.progress.message}
                    </div>
                )}
            </div>
        )
    }

    // Default: Text Log (Paragraph style as per reference image for "Browsing timeout..." etc.)
    return (
        <div className="py-2 pl-1 pr-4">
            <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap font-normal">
                {log.title}
            </p>
            {log.progress?.message && (
                <span className="text-xs text-gray-400 mt-1 block">— {log.progress.message}</span>
            )}
        </div>
    )
}

function ThoughtStream({ content, isRunning }: { content: string, isRunning: boolean }) {
    const scrollRef = useRef<HTMLDivElement>(null);
    const [userHasScrolled, setUserHasScrolled] = useState(false);

    useEffect(() => {
        const el = scrollRef.current;
        if (!el) return;
        if (!userHasScrolled) {
            el.scrollTop = el.scrollHeight;
        }
    }, [content, userHasScrolled]);

    const handleScroll = () => {
        const el = scrollRef.current;
        if (!el) return;
        const isAtBottom = Math.abs(el.scrollHeight - el.scrollTop - el.clientHeight) < 20;
        setUserHasScrolled(!isAtBottom);
    }

    return (
        <div className="relative group">
            <div className="absolute left-0 top-0 bottom-0 w-1 bg-gray-100 rounded-full" />
            <div
                ref={scrollRef}
                onScroll={handleScroll}
                className="max-h-[150px] overflow-y-auto overflow-x-hidden pl-4 text-xs leading-relaxed text-gray-500 font-mono scrollbar-thin scrollbar-thumb-gray-200 hover:scrollbar-thumb-gray-300 pr-2"
            >
                <div className="whitespace-pre-wrap break-words">
                    {content}
                    {isRunning && <span className="inline-block w-1.5 h-3 ml-1 bg-blue-400 animate-pulse align-middle" />}
                </div>
            </div>
        </div>
    )
}

function SubTaskItem({ subTask }: { subTask: ProcessSubTask }) {
    const { setArtifact, setPreviewOpen } = useArtifactStore()
    const isCompleted = subTask.status === 'completed';

    const handleClick = () => {
        if (!isCompleted) return;

        // Setup artifact for preview
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

    return (
        <div onClick={handleClick} className={cn("py-1 flex items-center gap-2", isCompleted && "cursor-pointer")}>
            <ActionPill
                icon={isCompleted ? FileText : Loader2}
                label={subTask.title}
                value={isCompleted ? "Research Report" : "Searching..."}
                className={cn(
                    "bg-gray-100 border-gray-200 text-gray-700",
                    !isCompleted && "animate-pulse border-blue-200 bg-blue-50/50",
                    isCompleted && "hover:bg-gray-200 hover:border-gray-300"
                )}
            />
        </div>
    )
}
