"use client"

import { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronUp } from "lucide-react";
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

interface FixedPlanOverlayProps {
    data: PlanUpdateData;
    className?: string;
    isInitialExpanded?: boolean;
}

const getStepRowClass = (status: PlanStepStatus) =>
    cn(
        "flex gap-3 rounded-xl px-3 py-2 transition-all",
        "items-start",
        status === "in_progress"
            ? "bg-indigo-50/70 dark:bg-indigo-950/30"
            : status === "completed"
                ? "bg-transparent"
                : "bg-slate-50/60 dark:bg-slate-900/40",
    );

const PLAIN_STEP_ROW_CLASS =
    "flex gap-3 rounded-xl px-3 py-2 bg-transparent";

const StepStatusIcon = ({
    status,
    index,
    animated = true,
    align = "top",
    tone = "default",
    animationDelayMs = 0,
}: {
    status: PlanStepStatus;
    index: number;
    animated?: boolean;
    align?: "top" | "center";
    tone?: "default" | "plain";
    animationDelayMs?: number;
}) => (
    <div className={cn("flex-shrink-0", align === "top" ? "mt-1" : "mt-0")}>
        {status === "completed" ? (
            <div
                className={cn(
                    "h-5 w-5 rounded-full flex items-center justify-center",
                    tone === "plain"
                        ? "border border-slate-300 dark:border-slate-600"
                        : "bg-emerald-100 dark:bg-emerald-900/30",
                )}
            >
                <CheckCircle2
                    className={cn(
                        "h-3.5 w-3.5",
                        tone === "plain" ? "text-slate-500 dark:text-slate-400" : "text-emerald-600 dark:text-emerald-400",
                    )}
                />
            </div>
        ) : status === "in_progress" ? (
            animated ? (
                <div className="relative flex items-center justify-center h-5 w-5">
                    <div
                        className="absolute inset-0 rounded-full animate-ping bg-indigo-500/20"
                        style={{ animationDelay: `${animationDelayMs}ms` }}
                    />
                    <div
                        className="h-2.5 w-2.5 rounded-full animate-pulse bg-indigo-600"
                        style={{ animationDelay: `${animationDelayMs}ms` }}
                    />
                </div>
            ) : (
                <div className="h-5 w-5 flex items-center justify-center">
                    <div className="h-2.5 w-2.5 rounded-full bg-indigo-600" />
                </div>
            )
        ) : (
            <div className="h-5 w-5 rounded-full border-2 border-slate-200 dark:border-slate-700 flex items-center justify-center text-[10px] font-medium text-slate-400">
                {index}
            </div>
        )}
    </div>
);

export function FixedPlanOverlay({
    data,
    className,
    isInitialExpanded = false
}: FixedPlanOverlayProps) {
    const [isExpanded, setIsExpanded] = useState(isInitialExpanded);
    const [dotAnimationSyncDelayMs] = useState(() => -(Date.now() % 2000));

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
            <Card className="overflow-hidden py-0 gap-0 border border-slate-200/70 dark:border-slate-800 shadow-xl rounded-2xl bg-white dark:bg-slate-900 transition-all duration-300 ease-in-out">
                <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="flex flex-col-reverse">
                    {/* Collapsed/Header View (Bottom position) */}
                    <div className="px-3 py-1.5 bg-white dark:bg-slate-900">
                        <div className={cn(PLAIN_STEP_ROW_CLASS, "items-center")}>
                            <StepStatusIcon
                                status={activeStep.status}
                                index={activeStepIndex}
                                animated
                                align="center"
                                tone="plain"
                                animationDelayMs={dotAnimationSyncDelayMs}
                            />
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between gap-2">
                                    <span
                                        className={cn(
                                            "text-sm font-medium truncate",
                                            activeStep.status === "completed"
                                                ? "text-slate-500"
                                                : "text-slate-900 dark:text-slate-100",
                                        )}
                                    >
                                        {activeStep.title || "Task"}
                                    </span>
                                </div>
                            </div>
                            <div className="flex items-center shrink-0 gap-2.5">
                                <span className="font-medium text-slate-500 dark:text-slate-400 text-xs">
                                    {activeStepIndex} / {totalSteps}
                                </span>
                                <CollapsibleTrigger asChild>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        aria-label={isExpanded ? "Collapse plan" : "Expand plan"}
                                        className="h-7 w-7 p-0 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 transition-colors shrink-0"
                                    >
                                        {isExpanded ? (
                                            <ChevronDown className="h-3.5 w-3.5" />
                                        ) : (
                                            <ChevronUp className="h-3.5 w-3.5" />
                                        )}
                                    </Button>
                                </CollapsibleTrigger>
                            </div>
                        </div>
                    </div>


                    {/* Expanded Content (Top position) */}
                    <CollapsibleContent className="border-b border-slate-200/70 dark:border-slate-800">
                        <CardContent className="px-3 pb-2 pt-1">
                            {/* Normal Order List (Step 1 -> N) */}
                            <div className="max-h-[240px] overflow-y-auto pr-1 space-y-1 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent">
                                {steps.map((step, index) => (
                                    <div
                                        key={step.id}
                                        className={getStepRowClass(step.status)}
                                    >
                                        <StepStatusIcon
                                            status={step.status}
                                            index={index + 1}
                                            animationDelayMs={dotAnimationSyncDelayMs}
                                        />
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center justify-between gap-2">
                                                <span className={cn(
                                                    "text-sm font-medium",
                                                    step.status === "completed" ? "text-slate-500" : "text-slate-900 dark:text-slate-100"
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
