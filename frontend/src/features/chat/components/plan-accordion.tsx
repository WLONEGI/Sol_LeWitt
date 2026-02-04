"use client"

import { cn } from "@/lib/utils"
import { Check, LayoutTemplate } from "lucide-react"
import {
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from "@/components/ui/accordion"

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

export function PlanAccordion({ plan, title = "Slides Outline", description }: PlanAccordionProps) {
    return (
        <div className="w-full max-w-2xl my-4">
            <Accordion type="single" collapsible defaultValue="plan" className="border border-gray-200 rounded-xl bg-white shadow-sm overflow-hidden">
                <AccordionItem value="plan" className="border-none">
                    <AccordionTrigger className="w-full p-4 flex items-center justify-between hover:bg-gray-50/50 transition-colors hover:no-underline">
                        <div className="flex items-center gap-4">
                            {/* Dark Icon Header */}
                            <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-gray-800 text-white shrink-0 shadow-sm">
                                <LayoutTemplate className="h-5 w-5" />
                            </div>

                            <div className="flex flex-col items-start">
                                <span className="text-base font-bold text-gray-900">{title}</span>
                                {description && (
                                    <span className="text-xs text-muted-foreground text-left line-clamp-1 mt-0.5">{description}</span>
                                )}
                            </div>
                        </div>
                    </AccordionTrigger>
                    <AccordionContent className="bg-white border-t border-gray-100">
                        <div className="p-4 space-y-4">
                            {plan.map((step, idx) => (
                                <div key={idx} className="flex items-start gap-4 p-2 rounded-lg hover:bg-gray-50 transition-colors group">
                                    {/* Numbered Circle */}
                                    <div className={cn(
                                        "flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold shrink-0 mt-0.5 transition-colors",
                                        step.status === 'complete' ? "bg-gray-200 text-gray-600" : "bg-gray-100 text-gray-400 group-hover:bg-gray-200 group-hover:text-gray-600"
                                    )}>
                                        {step.status === 'complete' ? <Check className="h-3 w-3" /> : idx + 1}
                                    </div>

                                    <div className="flex flex-col gap-1">
                                        <span className="text-sm font-bold text-gray-800 leading-none">
                                            {step.title || `Slide ${idx + 1}`}
                                        </span>
                                        <span className="text-sm text-gray-500 leading-relaxed font-normal">
                                            {step.instruction || step.description}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </AccordionContent>
                </AccordionItem>
            </Accordion>
        </div>
    )
}
