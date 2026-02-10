"use client"

import { useState } from "react";
import { CheckCircle2, Circle, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Card, CardContent } from "@/components/ui/card";
import type { PlanStep, PlanStepStatus, PlanUpdateData } from "@/features/chat/types/plan";
import { normalizePlanUpdateData } from "@/features/chat/types/plan";
const PLAN_STATUS_LABEL: Record<PlanStepStatus, string> = {
    pending: "待機",
    in_progress: "実行中",
    completed: "完了",
    blocked: "要確認",
};

interface FixedPlanOverlayProps {
    data: PlanUpdateData;
    className?: string;
    isInitialExpanded?: boolean;
}

export function FixedPlanOverlay({
    data,
    className,
    isInitialExpanded = false
}: FixedPlanOverlayProps) {
    const [isExpanded, setIsExpanded] = useState(isInitialExpanded);

    const steps = normalizePlanUpdateData(data).plan as Array<PlanStep & { status: PlanStepStatus }>;
    const totalSteps = steps.length;

    // Find the relevant step to show in the header
    const activeStep = steps.find(s => s.status === "in_progress") ||
        steps.find(s => s.status === "pending") ||
        steps[steps.length - 1];

    // Find the current index for the progress status
    const activeStepIndex = steps.indexOf(activeStep) + 1;

    if (!data || !steps || steps.length === 0) return null;

    return (
        <div className={cn("w-full max-w-5xl mx-auto", className)}>
            <Card className="overflow-hidden border-none shadow-2xl rounded-2xl bg-white dark:bg-slate-900 transition-all duration-300 ease-in-out">
                <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="flex flex-col-reverse">
                    {/* Collapsed/Header View (Bottom position) */}
                    <div className="flex items-center justify-between py-0 px-4 gap-4 bg-white dark:bg-slate-900">
                        {/* Status Icon Area */}
                        <div className="flex items-center gap-3 flex-1 min-w-0">
                            {/* Unified Header Text */}
                            <div className="flex items-center gap-2">
                                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tight shrink-0">
                                    Progress:
                                </span>
                                <span className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
                                    {activeStep.title || "Task"}
                                </span>
                            </div>
                        </div>

                        {/* Progress and Toggle Area */}
                        <div className="flex items-center gap-4 shrink-0">
                            <span className="text-sm font-medium text-slate-500 dark:text-slate-400">
                                {activeStepIndex} / {totalSteps}
                            </span>
                            <CollapsibleTrigger asChild>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    aria-label={isExpanded ? "Collapse plan" : "Expand plan"}
                                    className="h-8 w-8 p-0 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 transition-colors shrink-0"
                                >
                                    {isExpanded ? (
                                        <ChevronDown className="h-4 w-4" />
                                    ) : (
                                        <ChevronUp className="h-4 w-4" />
                                    )}
                                </Button>
                            </CollapsibleTrigger>
                        </div>
                    </div>

                    {/* Expanded Content (Top position) */}
                    <CollapsibleContent>
                        <CardContent className="pb-2 pt-0 px-0">
                            {/* Normal Order List (Step 1 -> N) */}
                            <div className="max-h-[30vh] overflow-y-auto px-4 pb-4 space-y-1 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent">
                                {steps.map((step, index) => (
                                    <div
                                        key={step.id}
                                        className={cn(
                                            "flex items-start gap-3 p-2 rounded-lg transition-all",
                                            step.status === "in_progress" && "bg-indigo-50/50 dark:bg-indigo-950/30"
                                        )}
                                    >
                                        <div className="mt-1 flex-shrink-0">
                                            {step.status === "completed" ? (
                                                <div className="h-5 w-5 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
                                                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                                                </div>
                                            ) : step.status === "in_progress" ? (
                                                <div className="relative flex items-center justify-center h-5 w-5">
                                                    <div className="absolute inset-0 rounded-full bg-indigo-500/20 animate-ping" />
                                                    <div className="h-2.5 w-2.5 rounded-full bg-indigo-600 animate-pulse" />
                                                </div>
                                            ) : (
                                                <div className="h-5 w-5 rounded-full border-2 border-slate-200 dark:border-slate-700 flex items-center justify-center text-[10px] font-medium text-slate-400">
                                                    {index + 1}
                                                </div>
                                            )}
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center justify-between gap-2">
                                                <span className={cn(
                                                    "text-sm font-medium",
                                                    step.status === "completed" ? "text-slate-500 line-through" : "text-slate-900 dark:text-slate-100"
                                                )}>
                                                    {step.title || "Task"}
                                                </span>
                                            </div>
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
