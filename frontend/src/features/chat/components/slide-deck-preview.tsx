"use client"

import { Layout, Loader2, Maximize2 } from "lucide-react"
import { useArtifactStore } from "@/features/preview/stores/artifact"
import { cn } from "@/lib/utils"
import { motion } from "framer-motion"
import { getAspectRatioClass } from "@/features/preview/utils/aspect-ratio"

export interface SlideDeckItem {
    slide_number: number;
    image_url: string;
    title: string;
    status?: "generating" | "completed" | "failed";
}

interface SlideDeckPreviewProps {
    artifactId: string;
    slides: SlideDeckItem[];
    title?: string;
    isStreaming?: boolean;
    aspectRatio?: string;
    compact?: boolean;
}

const CHAT_PREVIEW_MAX_WIDTH_BY_ASPECT: Record<string, string> = {
    "21:9": "max-w-[58rem]",
    "16:9": "max-w-[52rem]",
    "4:3": "max-w-[46rem]",
    "1:1": "max-w-[40rem]",
    "4:5": "max-w-[34rem]",
    "3:4": "max-w-[32rem]",
    "2:3": "max-w-[30rem]",
    "9:16": "max-w-[24rem]",
};

function resolveChatPreviewContainerClass(aspectRatio?: string): string {
    if (!aspectRatio) return CHAT_PREVIEW_MAX_WIDTH_BY_ASPECT["16:9"];
    return CHAT_PREVIEW_MAX_WIDTH_BY_ASPECT[aspectRatio] || CHAT_PREVIEW_MAX_WIDTH_BY_ASPECT["16:9"];
}

export function SlideDeckPreview({
    artifactId,
    slides,
    title = "Slides",
    isStreaming,
    aspectRatio,
    compact = false,
}: SlideDeckPreviewProps) {
    const { setActiveContextId, setPreviewOpen } = useArtifactStore();

    if (!slides || slides.length === 0) return null;

    const handleSlideClick = (slideIndex: number) => {
        setActiveContextId(artifactId);
        setPreviewOpen(true);
    };

    return (
        <div
            className={cn(
                "my-4 w-full",
                compact
                    ? "flex flex-wrap items-start gap-3 max-w-[560px]"
                    : cn("flex flex-col gap-6", resolveChatPreviewContainerClass(aspectRatio))
            )}
        >
            {slides.map((slide, idx) => (
                <motion.div
                    key={`${slide.slide_number}-${idx}`}
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.4, delay: idx * 0.1 }}
                    className={cn(
                        "group relative flex flex-col bg-white/5 border border-white/10 overflow-hidden shadow-sm hover:shadow-md transition-shadow active:scale-[0.99]",
                        compact ? "w-[170px] rounded-xl" : "rounded-2xl"
                    )}
                    onClick={() => handleSlideClick(idx)}
                >
                    {/* Header: Title + Page Number */}
                    <div className={cn("flex items-center justify-between bg-white/5 border-b border-white/10", compact ? "px-2.5 py-2" : "px-5 py-3")}>
                        <div className={cn("flex items-center min-w-0", compact ? "gap-1.5" : "gap-3")}>
                            <div className={cn("rounded-lg bg-primary/10 border border-primary/20", compact ? "p-1" : "p-1.5")}>
                                <Layout className={cn("text-primary", compact ? "w-3 h-3" : "w-4 h-4")} />
                            </div>
                            <span className={cn("font-semibold text-foreground/90 truncate", compact ? "text-[11px]" : "text-sm")}>
                                {slide.title || title}
                            </span>
                        </div>
                        <div className={cn("flex items-center shrink-0", compact ? "gap-1" : "gap-3")}>
                            {!compact && aspectRatio && (
                                <span
                                    className="rounded-md border border-white/10 bg-black/20 px-2 py-1 text-[11px] font-mono font-semibold tracking-tight text-muted-foreground"
                                    title={`Aspect ratio: ${aspectRatio}`}
                                >
                                    {aspectRatio}
                                </span>
                            )}
                            {slide.status === "generating" && (
                                <Loader2 className={cn("animate-spin text-primary/60", compact ? "w-3 h-3" : "w-3.5 h-3.5")} />
                            )}
                            <span className={cn(
                                "font-mono font-bold tracking-tighter text-muted-foreground bg-black/20 rounded-md border border-white/5",
                                compact ? "text-[10px] px-1.5 py-0.5" : "text-xs px-2 py-1"
                            )}>
                                {slide.slide_number} / {slides.length}
                            </span>
                        </div>
                    </div>

                    {/* Content: Main Image */}
                    <div className={cn("relative w-full bg-muted/20 cursor-pointer overflow-hidden group", getAspectRatioClass(aspectRatio))}>
                        {slide.image_url ? (
                            <img
                                src={slide.image_url}
                                alt={`Slide ${slide.slide_number}`}
                                className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-[1.02]"
                            />
                        ) : slide.status === "failed" ? (
                            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-destructive/5 text-destructive">
                                <Maximize2 className="w-8 h-8 opacity-50 rotate-45" />
                                <span className="text-xs font-semibold">Generation Failed</span>
                            </div>
                        ) : (
                            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
                                <Loader2 className="w-8 h-8 animate-spin text-primary/40" />
                                <span className="text-xs text-muted-foreground animate-pulse">Generating Slide...</span>
                            </div>
                        )}

                        {/* Hover Overlay */}
                        <div className="absolute inset-0 bg-black/10 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-all duration-300">
                            <div className="p-3 rounded-full bg-white/10 backdrop-blur-md border border-white/20 shadow-xl transform translate-y-4 group-hover:translate-y-0 transition-transform duration-300">
                                <Maximize2 className="w-5 h-5 text-white" />
                            </div>
                        </div>
                    </div>
                </motion.div>
            ))}

        </div>
    )
}
