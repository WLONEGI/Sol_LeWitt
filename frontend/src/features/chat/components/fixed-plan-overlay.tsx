"use client"

import { useState, useEffect } from "react";
import { CheckCircle2, Circle, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Card, CardContent } from "@/components/ui/card";

interface PlanStep {
    id: number;
    role: string;
    instruction: string;
    title: string;
    description: string;
    status: "pending" | "in_progress" | "completed";
    result_summary?: string | null;
}

interface PlanData {
    plan: PlanStep[];
    title?: string;
    description?: string;
    ui_type?: string;
}

interface FixedPlanOverlayProps {
    data: PlanData;
    className?: string;
    isInitialExpanded?: boolean;
}

export function FixedPlanOverlay({
    data,
    className,
    isInitialExpanded = false
}: FixedPlanOverlayProps) {
    const [isExpanded, setIsExpanded] = useState(isInitialExpanded);

    const steps = data.plan;
    const totalSteps = steps.length;

    // Find the relevant step to show in the header
    const activeStep = steps.find(s => s.status === "in_progress") ||
        steps.find(s => s.status === "pending") ||
        steps[steps.length - 1];

    if (!data || !steps || steps.length === 0) return null;

    return (
        <div className={cn("w-full max-w-3xl mx-auto mb-2 px-4", className)}>
            <Card className="overflow-hidden border-indigo-100/50 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm transition-all duration-300 ease-in-out">
                <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="flex flex-col-reverse">
                    {/* Collapsed/Header View (Bottom position) */}
                    <div className="flex items-center justify-between py-1 px-3 gap-3">
                        {/* Status Icon Area */}
                        <div className="flex items-center gap-2.5 flex-1 min-w-0">
                            <div className="flex-shrink-0">
                                {activeStep.status === "in_progress" ? (
                                    <div className="relative flex items-center justify-center w-4 h-4">
                                        <div className="absolute inset-0 rounded-full bg-indigo-500/20 animate-ping" />
                                        <Circle className="h-3 w-3 text-indigo-600 animate-pulse fill-indigo-100" />
                                    </div>
                                ) : activeStep.status === "completed" ? (
                                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                                ) : (
                                    <Circle className="h-3.5 w-3.5 text-slate-300" />
                                )}
                            </div>

                            {/* Unified Header Text: Always show Step X: Title */}
                            <div className="min-w-0 flex items-center gap-2">
                                <span className="text-[11px] font-bold text-slate-700 dark:text-slate-200 truncate">
                                    Step {activeStep.id}: {activeStep.title}
                                </span>
                                <span className="text-[9px] text-slate-400 font-medium whitespace-nowrap">
                                    ({activeStep.id}/{totalSteps})
                                </span>
                            </div>
                        </div>

                        {/* Toggle Button */}
                        <CollapsibleTrigger asChild>
                            <Button
                                variant="ghost"
                                size="sm"
                                aria-label={isExpanded ? "Collapse plan" : "Expand plan"}
                                className="h-5 w-5 p-0 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 transition-colors shrink-0"
                            >
                                {isExpanded ? (
                                    <ChevronDown className="h-3 w-3" />
                                ) : (
                                    <ChevronUp className="h-3 w-3" />
                                )}
                            </Button>
                        </CollapsibleTrigger>
                    </div>

                    {/* Expanded Content (Top position) */}
                    <CollapsibleContent>
                        <CardContent className="pb-0 pt-2 px-2 border-b border-indigo-50/50 dark:border-indigo-900/10 mb-0.5">
                            {/* Normal Order List (Step 1 -> N) */}
                            <div className="max-h-[30vh] overflow-y-auto space-y-0.5 mb-2 pr-1 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent">
                                {steps.map((step) => (
                                    <div
                                        key={step.id}
                                        className={cn(
                                            "flex items-start gap-3 p-1.5 rounded-md transition-all",
                                            step.status === "in_progress" && "bg-indigo-50/50 dark:bg-indigo-950/30",
                                            step.status === "completed" && "opacity-60"
                                        )}
                                    >
                                        <div className="mt-0.5 flex-shrink-0">
                                            {step.status === "completed" ? (
                                                <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                                            ) : step.status === "in_progress" ? (
                                                <Circle className="h-3 w-3 text-indigo-500 animate-pulse fill-indigo-500/10" />
                                            ) : (
                                                <Circle className="h-3 w-3 text-slate-300 dark:text-slate-700" />
                                            )}
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center justify-between gap-2">
                                                <span className={cn(
                                                    "text-[11px] font-medium",
                                                    step.status === "completed" ? "text-slate-500" : "text-slate-800 dark:text-slate-200"
                                                )}>
                                                    {step.title}
                                                </span>
                                            </div>
                                            <p className="text-[9px] text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-1 leading-tight">
                                                {step.description}
                                            </p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </CollapsibleContent>
                </Collapsible>
            </Card>
        </div>
    );
}
