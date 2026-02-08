import { CheckCircle2, Circle, Loader2, ChevronDown, ChevronUp, Check, X } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import type { PlanStep, PlanStepStatus, PlanUpdateData } from "@/features/chat/types/plan";
import { getPlanStepActorLabel, normalizePlanUpdateData } from "@/features/chat/types/plan";

interface PlanStatusChecklistProps {
    data: PlanUpdateData;
    className?: string;
    approvalStatus?: 'loading' | 'idle';
}

export function PlanStatusChecklist({
    data,
    className,
    approvalStatus = 'idle'
}: PlanStatusChecklistProps) {
    // Determine overall status based on steps? 
    // Usually the last plan update reflects current state.

    const normalizedPlan = normalizePlanUpdateData(data).plan as Array<PlanStep & { status: PlanStepStatus }>;

    return (
        <Card className={cn(
            "w-full border-indigo-100 bg-indigo-50/30 dark:bg-indigo-950/10 dark:border-indigo-900/50 shadow-sm",
            className
        )}>
            <CardHeader className="pb-1 pt-2 px-3 text-center sm:text-left">
                <CardTitle className={cn(
                    "text-sm font-sans font-semibold flex items-center gap-1.5",
                    "text-indigo-900 dark:text-indigo-100"
                )}>

                    <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
                    {data.title || "Execution Plan"}
                </CardTitle>
                {data.description && (
                    <CardDescription className={cn(
                        "text-xs font-sans mt-0.5",
                        "text-indigo-600 dark:text-indigo-400"
                    )}>

                        {data.description}
                    </CardDescription>
                )}
            </CardHeader>
            <CardContent className="grid gap-1 px-2 pb-2 pt-0">
                {normalizedPlan.map((step) => (
                    <PlanStepItem key={step.id} step={step} />
                ))}
            </CardContent>
        </Card>
    );
}

function PlanStepItem({ step }: { step: PlanStep & { status: PlanStepStatus } }) {
    const [isOpen, setIsOpen] = useState(false);

    const isCompleted = step.status === "completed";
    const isInProgress = step.status === "in_progress";
    const isPending = step.status === "pending";

    return (
        <Collapsible
            open={isOpen}
            onOpenChange={setIsOpen}
            className={cn(
                "group rounded-lg border border-transparent bg-white dark:bg-slate-900 shadow-sm transition-all",
                isInProgress && "border-indigo-200 ring-1 ring-indigo-200 dark:border-indigo-800 dark:ring-indigo-800",
                isCompleted && "bg-slate-50/50 dark:bg-slate-900/50 text-slate-500"
            )}
        >
            <CollapsibleTrigger asChild>
                <div className="flex items-center gap-2 py-0.5 px-2 cursor-pointer w-full">

                    <div className="flex-shrink-0 text-slate-400">
                        {isCompleted ? (
                            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                        ) : isInProgress ? (
                            <div className="relative">
                                <Circle className="h-4 w-4 text-indigo-500" />
                                <span className="absolute inset-0 flex items-center justify-center">
                                    <span className="h-1.5 w-1.5 rounded-full bg-indigo-500 animate-pulse" />
                                </span>
                            </div>
                        ) : (
                            <Circle className="h-4 w-4 text-slate-300" />
                        )}
                    </div>

                    <div className="flex-1 text-left min-w-0">
                        <h4 className={cn(
                            "text-sm font-sans font-medium leading-none truncate",
                            isCompleted ? "text-slate-600 dark:text-slate-400 decoration-slate-400" : "text-slate-900 dark:text-slate-200"
                        )}>
                            {step.title || "タスク"}
                        </h4>
                        <p className="text-xs font-sans text-slate-500 mt-0.5 truncate">
                            {getPlanStepActorLabel(step)} • {step.description || "タスク"}
                        </p>

                    </div>


                    <Button variant="ghost" size="icon" className="h-5 w-5 shrink-0 text-slate-400">
                        {isOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                    </Button>
                </div>
            </CollapsibleTrigger>

            <CollapsibleContent>
                <div className="px-8 pb-2 pt-0.5 text-xs text-slate-600 dark:text-slate-400 space-y-1.5">
                    <div className="p-2 rounded bg-slate-50 dark:bg-slate-950 border border-slate-100 dark:border-slate-800">
                        <span className="font-semibold block mb-0.5">Instruction:</span>
                        {step.instruction || "（指示なし）"}
                    </div>
                    {step.result_summary && (
                        <div className="p-2 rounded bg-emerald-50/50 dark:bg-emerald-950/20 border border-emerald-100 dark:border-emerald-900/50">
                            <span className="font-semibold block mb-0.5 text-emerald-700 dark:text-emerald-400">Result:</span>
                            {step.result_summary}
                        </div>
                    )}
                </div>
            </CollapsibleContent>
        </Collapsible>
    );
}
