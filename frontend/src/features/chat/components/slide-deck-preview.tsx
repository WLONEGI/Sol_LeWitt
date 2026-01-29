"use client"

import { Image as ImageIcon, Maximize2, Loader2, CheckCircle2 } from "lucide-react"
import { useArtifactStore } from "../../preview/store/artifact"
import { cn } from "@/lib/utils"

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

export function SlideDeckPreview({ artifactId, slides, title = "Generated Slides", isStreaming }: SlideDeckPreviewProps) {
    const { setActiveContextId, setPreviewOpen } = useArtifactStore();

    if (!slides || slides.length === 0) return null;

    const handleSlideClick = (slideIndex: number) => {
        // Here we might want to open the viewer at a specific index
        // For now, just open the artifact viewer
        setActiveContextId(artifactId);
        setPreviewOpen(true);
    };

    return (
        <div className="flex flex-col gap-3 my-2 w-full max-w-md">
            <div className="flex items-center justify-between px-1">
                <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider flex items-center gap-2">
                    <ImageIcon className="w-3 h-3" />
                    {title}
                </span>
                {isStreaming && (
                    <span className="flex items-center gap-1.5 text-xs text-emerald-400 animate-pulse">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        Generating...
                    </span>
                )}
            </div>

            <div className="grid grid-cols-1 gap-3">
                {slides.map((slide, idx) => (
                    <div
                        key={`${slide.slide_number}-${idx}`}
                        className="group relative flex items-center gap-4 p-3 bg-black/20 border border-white/5 rounded-lg hover:bg-white/5 hover:border-white/10 transition-all cursor-pointer overflow-hidden animate-in slide-in-from-bottom-2 duration-500 fade-in"
                        onClick={() => handleSlideClick(idx)}
                    >
                        {/* Thumbnail */}
                        <div className="relative aspect-video h-16 w-28 shrink-0 rounded-md overflow-hidden bg-muted/20 border border-white/5 shadow-sm">
                            <img
                                src={slide.image_url}
                                alt={`Slide ${slide.slide_number}`}
                                className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-110"
                            />
                            {/* Overlay Icon */}
                            <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
                                <Maximize2 className="w-4 h-4 text-white" />
                            </div>
                        </div>

                        {/* Info */}
                        <div className="flex flex-col min-w-0 flex-1 gap-1">
                            <div className="flex items-center justify-between">
                                <span className="text-xs font-semibold text-white/90 truncate pr-2">
                                    {slide.title || `Slide ${slide.slide_number}`}
                                </span>
                                <span className="text-[10px] font-mono text-muted-foreground bg-white/5 px-1.5 py-0.5 rounded-sm shrink-0 border border-white/5">
                                    {String(slide.slide_number).padStart(2, '0')}
                                </span>
                            </div>

                            <div className="flex items-center gap-2">
                                <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                                    <div className="h-full w-full bg-emerald-500/50 rounded-full" />
                                </div>
                                <CheckCircle2 className="w-3 h-3 text-emerald-500/80 shrink-0" />
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    )
}
