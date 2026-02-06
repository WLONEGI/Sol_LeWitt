"use client"

import { Presentation, ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"
import {
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from "@/components/ui/accordion"

interface Slide {
    slide_number: number
    title: string
    description?: string
    bullet_points?: string[]
    key_message?: string
}

interface SlideOutlineProps {
    slides: Slide[]
    title?: string
    className?: string
    approvalStatus?: 'loading' | 'idle';
}

export function SlideOutline({
    slides,
    title = "Slides outline",
    className,
    approvalStatus = 'idle'
}: SlideOutlineProps) {
    return (
        <div className={cn("w-full max-w-2xl my-4", className)}>
            <Accordion type="single" collapsible defaultValue="outline" className="border rounded-xl bg-card text-card-foreground shadow-sm overflow-hidden">
                <AccordionItem value="outline" className="border-none">
                    <AccordionTrigger className="flex items-center justify-between p-4 transition-colors hover:no-underline pointer-events-auto">
                        <div className="flex items-center gap-3">
                            <div className="flex items-center justify-center w-8 h-8 rounded-lg shadow-sm bg-primary text-primary-foreground">
                                <Presentation className="w-4 h-4" />
                            </div>
                            <div className="flex flex-col text-left">
                                <span className="text-sm font-semibold leading-none">{title}</span>
                                <span className="text-xs text-muted-foreground mt-1 truncate max-w-[300px]">
                                    {slides.length > 0 ? (slides[0].description ? slides[0].description.slice(0, 60) + "..." : "Generated presentation structure") : "Generated presentation structure"}
                                </span>
                            </div>
                        </div>
                    </AccordionTrigger>
                    <AccordionContent className="px-4 pb-4 pt-2">
                        <div className="flex flex-col gap-6 pl-1 pt-2">
                            {slides.map((slide, index) => (
                                <div key={index} className="flex gap-4 items-start group">
                                    <div className="flex-shrink-0 mt-0.5">
                                        <div className={cn(
                                            "flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold transition-colors",
                                            "bg-foreground text-background"
                                        )}>
                                            {slide.slide_number}
                                        </div>
                                    </div>
                                    <div className="flex flex-col gap-1.5 text-left">
                                        <h4 className="text-sm font-bold text-foreground leading-none">
                                            {slide.title}
                                        </h4>
                                        {slide.description && (
                                            <p className="text-sm text-muted-foreground leading-relaxed">
                                                {slide.description}
                                            </p>
                                        )}
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

