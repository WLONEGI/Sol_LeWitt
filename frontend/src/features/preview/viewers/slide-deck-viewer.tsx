"use client"

import { useMemo, useState } from "react"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Download } from "lucide-react"

interface SlideDeckViewerProps {
    content: {
        slides?: Array<{
            slide_number: number
            title?: string
            image_url?: string
            prompt_text?: string
            structured_prompt?: any
            rationale?: string
            layout_type?: string
            selected_inputs?: string[]
        }>
        pdf_url?: string
    }
}

export function SlideDeckViewer({ content }: SlideDeckViewerProps) {
    const [tab, setTab] = useState<"image" | "prompt" | "pdf">("image")
    const slides = useMemo(() => {
        const list = Array.isArray(content?.slides) ? content.slides : []
        return [...list].sort((a, b) => a.slide_number - b.slide_number)
    }, [content?.slides])

    return (
        <div className="flex flex-col h-full min-h-0 bg-background">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                <div className="flex items-center gap-2">
                    <button
                        className={cn(
                            "px-3 py-1.5 text-xs font-semibold rounded-md border transition-colors",
                            tab === "image"
                                ? "bg-foreground text-background border-foreground"
                                : "bg-transparent text-foreground border-border hover:bg-muted"
                        )}
                        onClick={() => setTab("image")}
                    >
                        Image
                    </button>
                    <button
                        className={cn(
                            "px-3 py-1.5 text-xs font-semibold rounded-md border transition-colors",
                            tab === "prompt"
                                ? "bg-foreground text-background border-foreground"
                                : "bg-transparent text-foreground border-border hover:bg-muted"
                        )}
                        onClick={() => setTab("prompt")}
                    >
                        Prompt
                    </button>
                    {content?.pdf_url && (
                        <button
                            className={cn(
                                "px-3 py-1.5 text-xs font-semibold rounded-md border transition-colors",
                                tab === "pdf"
                                    ? "bg-foreground text-background border-foreground"
                                    : "bg-transparent text-foreground border-border hover:bg-muted"
                            )}
                            onClick={() => setTab("pdf")}
                        >
                            PDF
                        </button>
                    )}
                </div>

                {content?.pdf_url && (
                    <a
                        href={content.pdf_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2 text-xs font-semibold px-3 py-1.5 rounded-md border border-border hover:bg-muted transition-colors"
                    >
                        <Download className="w-3 h-3" />
                        PDF
                    </a>
                )}
            </div>

            {tab === "pdf" && content?.pdf_url ? (
                <div className="flex-1 min-h-0 p-4">
                    <iframe
                        src={content.pdf_url}
                        className="w-full h-full rounded-md border border-border bg-muted/10"
                        title="Combined Slide PDF"
                    />
                </div>
            ) : (
                <ScrollArea className="flex-1 min-h-0 p-4">
                    <div className="flex flex-col gap-6">
                        {slides.map((slide) => (
                            <div key={slide.slide_number} className="flex flex-col gap-2">
                                <div className="flex items-center justify-between">
                                    <div className="text-sm font-semibold">
                                        {slide.title || `Slide ${slide.slide_number}`}
                                    </div>
                                    <div className="text-[10px] font-mono text-muted-foreground bg-muted px-2 py-0.5 rounded">
                                        {String(slide.slide_number).padStart(2, "0")}
                                    </div>
                                </div>

                                {tab === "image" ? (
                                    <div className="aspect-video w-full rounded-md overflow-hidden border border-border bg-muted/30">
                                        {slide.image_url ? (
                                            <img
                                                src={slide.image_url}
                                                alt={`Slide ${slide.slide_number}`}
                                                className="h-full w-full object-contain"
                                            />
                                        ) : (
                                            <div className="h-full w-full flex items-center justify-center text-xs text-muted-foreground">
                                                Image not available yet
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <div className="flex flex-col gap-3">
                                        {slide.prompt_text && (
                                            <div className="rounded-md border border-border bg-muted/20 p-3">
                                                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Compiled Prompt</div>
                                                <pre className="text-xs whitespace-pre-wrap break-words font-mono">{slide.prompt_text}</pre>
                                            </div>
                                        )}
                                        {slide.structured_prompt && (
                                            <div className="rounded-md border border-border bg-muted/20 p-3">
                                                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Structured Prompt</div>
                                                <pre className="text-xs whitespace-pre-wrap break-words font-mono">
                                                    {JSON.stringify(slide.structured_prompt, null, 2)}
                                                </pre>
                                            </div>
                                        )}
                                        {slide.rationale && (
                                            <div className="rounded-md border border-border bg-muted/20 p-3">
                                                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Rationale</div>
                                                <pre className="text-xs whitespace-pre-wrap break-words font-mono">{slide.rationale}</pre>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </ScrollArea>
            )}
        </div>
    )
}
