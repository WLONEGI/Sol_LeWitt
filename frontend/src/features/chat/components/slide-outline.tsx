"use client"

import { cn } from "@/lib/utils"
import { LayoutTemplate, ChevronDown, CheckCircle2, MessageSquareText } from "lucide-react"
import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"

interface Slide {
    slide_number: number;
    title: string;
    description?: string;
    bullet_points: string[];
    key_message?: string;
}

interface SlideOutlineProps {
    slides: Slide[];
    title?: string;
}

export function SlideOutline({ slides, title = "Slides Outline" }: SlideOutlineProps) {
    const [isExpanded, setIsExpanded] = useState(true);

    const containerVariants = {
        hidden: { opacity: 0 },
        visible: {
            opacity: 1,
            transition: {
                staggerChildren: 0.1,
                delayChildren: 0.2
            }
        }
    };

    const itemVariants = {
        hidden: { opacity: 0, x: -10 },
        visible: { opacity: 1, x: 0 }
    };

    return (
        <div className="w-full max-w-3xl my-6">
            <div className="flex flex-col">
                {/* Header */}
                <div
                    onClick={() => setIsExpanded(!isExpanded)}
                    className="flex items-center justify-between mb-8 cursor-pointer group"
                >
                    <div className="flex items-center gap-4">
                        <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-zinc-900 text-white shadow-lg group-hover:scale-105 transition-transform">
                            <LayoutTemplate className="h-6 w-6" />
                        </div>
                        <div className="flex flex-col">
                            <h2 className="text-xl font-bold text-gray-900 tracking-tight">{title}</h2>
                            <p className="text-sm text-gray-400 font-medium">Narrative Map • {slides.length} Slides</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-3 pr-2">
                        <span className="text-xs font-bold uppercase tracking-widest text-gray-400">
                            {isExpanded ? "Minimize" : "View Map"}
                        </span>
                        <div className={cn(
                            "w-6 h-6 rounded-full flex items-center justify-center border border-gray-200 transition-transform duration-300",
                            !isExpanded && "-rotate-180"
                        )}>
                            <ChevronDown className="h-4 w-4 text-gray-400" />
                        </div>
                    </div>
                </div>

                <AnimatePresence>
                    {isExpanded && (
                        <motion.div
                            variants={containerVariants}
                            initial="hidden"
                            animate="visible"
                            exit="hidden"
                            className="relative pl-6 ml-6 border-l-2 border-gray-100 space-y-12 pb-4"
                        >
                            {slides.map((slide, idx) => (
                                <motion.div
                                    key={idx}
                                    variants={itemVariants}
                                    className="relative"
                                >
                                    {/* Connection Point (The Dot) */}
                                    <div className="absolute -left-[35px] top-1 w-4 h-4 rounded-full bg-white border-4 border-zinc-900 z-10 shadow-sm" />

                                    <div className="flex flex-col gap-3 group">
                                        <div className="flex flex-col">
                                            <div className="flex items-center gap-3">
                                                <span className="text-[10px] font-black text-zinc-300 uppercase tracking-widest leading-none">
                                                    Slide {slide.slide_number || idx + 1}
                                                </span>
                                                <div className="h-[1px] flex-1 bg-gray-50 group-hover:bg-gray-100 transition-colors" />
                                            </div>
                                            <h3 className="text-lg font-bold text-gray-900 mt-1 group-hover:text-zinc-700 transition-colors">
                                                {slide.title}
                                            </h3>
                                        </div>

                                        {slide.description && (
                                            <p className="text-[15px] text-gray-500 leading-relaxed font-normal max-w-2xl">
                                                {slide.description}
                                            </p>
                                        )}

                                        {slide.key_message && (
                                            <div className="mt-1 flex items-start gap-3 p-3.5 rounded-xl bg-zinc-50 border border-zinc-100 group-hover:bg-zinc-100/50 transition-colors">
                                                <div className="mt-1 p-1 rounded-md bg-zinc-900/5">
                                                    <MessageSquareText className="h-3.5 w-3.5 text-zinc-600" />
                                                </div>
                                                <div className="flex flex-col">
                                                    <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider mb-0.5">Key Message</span>
                                                    <span className="text-sm font-medium text-zinc-800 leading-snug">
                                                        {slide.key_message}
                                                    </span>
                                                </div>
                                            </div>
                                        )}

                                        {/* Optional: Show bullet points as subtle tags if expanded/requested */}
                                        {slide.bullet_points && slide.bullet_points.length > 0 && (
                                            <div className="flex flex-wrap gap-2 mt-2 opacity-60 group-hover:opacity-100 transition-opacity">
                                                {slide.bullet_points.map((point, pIdx) => (
                                                    <span key={pIdx} className="text-[11px] font-medium text-gray-400 px-2 py-0.5 rounded-full border border-gray-100 bg-white">
                                                        • {point}
                                                    </span>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                </motion.div>
                            ))}
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    )
}
