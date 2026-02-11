"use client"

import { cn } from "@/lib/utils"
import type { ImageSearchCandidate } from "../types/timeline"

interface ImageSearchResultsProps {
    query: string
    candidates: ImageSearchCandidate[]
    selectedUrls: string[]
    onToggleSelect: (candidate: ImageSearchCandidate) => void
}

export function ImageSearchResults({
    query,
    candidates,
    selectedUrls,
    onToggleSelect,
}: ImageSearchResultsProps) {
    const visibleCandidates = candidates

    const tileClassByIndex = (index: number) => {
        const pattern = index % 7
        if (pattern === 0) return "md:col-span-2 md:row-span-2"
        if (pattern === 3) return "md:col-span-2"
        if (pattern === 5) return "md:row-span-2"
        return "md:col-span-1 md:row-span-1"
    }

    return (
        <div className="my-2 ml-2">
            {visibleCandidates.length === 0 ? (
                <div className="text-xs text-muted-foreground px-2">画像候補が見つかりませんでした。</div>
            ) : (
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4 md:auto-rows-[96px]">
                    {visibleCandidates.map((candidate, idx) => {
                        const isSelected = selectedUrls.includes(candidate.image_url)
                        return (
                            <button
                                key={`${candidate.image_url}-${idx}`}
                                type="button"
                                onClick={() => onToggleSelect(candidate)}
                                className={cn(
                                    "relative overflow-hidden rounded-xl border bg-muted/20 text-left transition-all",
                                    tileClassByIndex(idx),
                                    isSelected
                                        ? "border-primary ring-2 ring-primary/40"
                                        : "border-border hover:border-primary/40"
                                )}
                            >
                                <div className="h-full w-full bg-muted/40">
                                    <img
                                        src={candidate.image_url}
                                        alt={candidate.caption || query || `image-${idx + 1}`}
                                        className="h-full w-full object-cover"
                                    />
                                </div>
                            </button>
                        )
                    })}
                </div>
            )}
        </div>
    )
}
