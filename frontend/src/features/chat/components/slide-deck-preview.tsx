"use client"

import { Layout, Loader2, Maximize2 } from "lucide-react"
import { useArtifactStore } from "@/features/preview/stores/artifact"
import { cn } from "@/lib/utils"
import { motion } from "framer-motion"

export interface SlideDeckItem {
    slide_number: number;
    image_url: string;
    title: string;
    status?: "generating" | "completed";
}

interface SlideDeckPreviewProps {
    artifactId: string;
    slides: SlideDeckItem[];
    title?: string;
    isStreaming?: boolean;
}

export function SlideDeckPreview({ artifactId, slides, title = "Slides", isStreaming }: SlideDeckPreviewProps) {
    const { setActiveContextId, setPreviewOpen } = useArtifactStore();

    if (!slides || slides.length === 0) return null;

    const handleSlideClick = (slideIndex: number) => {
        setActiveContextId(artifactId);
        setPreviewOpen(true);
    };

    return (
        <div className="flex flex-col gap-6 my-4 w-full max-w-2xl">
            {slides.map((slide, idx) => (
                <motion.div
                    key={`${slide.slide_number}-${idx}`}
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.4, delay: idx * 0.1 }}
                    className="group relative flex flex-col bg-white/5 border border-white/10 rounded-2xl overflow-hidden shadow-sm hover:shadow-md transition-shadow active:scale-[0.99]"
                    onClick={() => handleSlideClick(idx)}
                >
                    {/* Header: Title + Page Number */}
                    <div className="flex items-center justify-between px-5 py-3 bg-white/5 border-b border-white/10">
                        <div className="flex items-center gap-3 min-w-0">
                            <div className="p-1.5 rounded-lg bg-primary/10 border border-primary/20">
                                <Layout className="w-4 h-4 text-primary" />
                            </div>
                            <span className="text-sm font-semibold text-foreground/90 truncate">
                                {slide.title || title}
                            </span>
                        </div>
                        <div className="flex items-center gap-3 shrink-0">
                            {slide.status === "generating" && (
                                <Loader2 className="w-3.5 h-3.5 animate-spin text-primary/60" />
                            )}
                            <span className="text-xs font-mono font-bold tracking-tighter text-muted-foreground bg-black/20 px-2 py-1 rounded-md border border-white/5">
                                {slide.slide_number} / {slides.length}
                            </span>
                        </div>
                    </div>

                    {/* Content: Main Image */}
                    <div className="relative aspect-video w-full bg-muted/20 cursor-pointer overflow-hidden group">
                        {slide.image_url ? (
                            <img
                                src={slide.image_url}
                                alt={`Slide ${slide.slide_number}`}
                                className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-[1.02]"
                            />
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
