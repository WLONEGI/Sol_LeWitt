"use client"

import { cn } from "@/lib/utils"
import { Check, Circle, Loader2 } from "lucide-react"
import { useState } from "react"
import { ChevronDown } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"

interface PlanStep {
    id: number | string;
    role: string;
    instruction: string;
    status: 'pending' | 'in_progress' | 'complete';
    title?: string;
    description?: string;
}

interface PlanAccordionProps {
    plan: PlanStep[];
    title?: string;
    description?: string;
}

export function PlanAccordion({ plan, title = "Execution Plan", description }: PlanAccordionProps) {
    const [isExpanded, setIsExpanded] = useState(false);

    // Calculate progress
    const completed = plan.filter(p => p.status === 'complete').length;
    const total = plan.length;
    const progress = Math.round((completed / total) * 100);

    return (
        <div className="w-full max-w-2xl my-4 ml-2">
            <div className="border border-white/10 rounded-xl bg-black/20 backdrop-blur-sm overflow-hidden">
                <button
                    onClick={() => setIsExpanded(!isExpanded)}
                    className="w-full p-3 bg-white/5 border-b border-white/5 flex items-center justify-between hover:bg-white/10 transition-colors"
                >
                    <div className="flex flex-col items-start gap-1">
                        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                            <span>{title}</span>
                            <span className="text-xs text-muted-foreground ml-2">({completed}/{total} steps)</span>
                        </div>
                        {description && <span className="text-xs text-muted-foreground text-left line-clamp-1">{description}</span>}
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
                            className="bg-black/10"
                        >
                            <div className="p-2 space-y-1">
                                {plan.map((step, idx) => (
                                    <div key={idx} className="flex items-start gap-3 p-2 rounded-md hover:bg-white/5 text-sm">
                                        <div className="mt-1 shrink-0">
                                            {step.status === 'complete' ? (
                                                <Check className="h-3 w-3 text-green-400" />
                                            ) : step.status === 'in_progress' ? (
                                                <Loader2 className="h-3 w-3 text-primary animate-spin" />
                                            ) : (
                                                <Circle className="h-3 w-3 text-muted-foreground/30" />
                                            )}
                                        </div>
                                        <div className="flex flex-col">
                                            <span className={cn("font-medium", step.status === 'complete' ? "text-muted-foreground" : "text-foreground")}>
                                                {step.title || `Step ${idx + 1}`}
                                            </span>
                                            <span className="text-xs text-muted-foreground">{step.instruction}</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    )
}
