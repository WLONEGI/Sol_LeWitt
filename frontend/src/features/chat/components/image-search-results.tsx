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
    const visibleCandidates = candidates.slice(0, 8)

    return (
        <div className="flex flex-col gap-3 my-2 ml-2">
            <div className="rounded-2xl border border-border bg-card px-4 py-3">
                <div className="text-sm font-semibold">Using Tool | Image Search {query}</div>
            </div>
            {visibleCandidates.length === 0 ? (
                <div className="text-xs text-muted-foreground px-2">画像候補が見つかりませんでした。</div>
            ) : (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {visibleCandidates.map((candidate, idx) => {
                        const isSelected = selectedUrls.includes(candidate.image_url)
                        return (
                            <button
                                key={`${candidate.image_url}-${idx}`}
                                type="button"
                                onClick={() => onToggleSelect(candidate)}
                                className={cn(
                                    "relative rounded-xl overflow-hidden border bg-muted/20 transition-all text-left",
                                    isSelected
                                        ? "border-primary ring-2 ring-primary/40"
                                        : "border-border hover:border-primary/40"
                                )}
                            >
                                <div className="aspect-[4/3] bg-muted/40">
                                    <img
                                        src={candidate.image_url}
                                        alt={candidate.caption || `image-${idx + 1}`}
                                        className="h-full w-full object-cover"
                                    />
                                </div>
                                <div className="p-2">
                                    <div className="text-[10px] text-muted-foreground truncate">
                                        {candidate.source_url}
                                    </div>
                                    <div className="text-[10px] text-muted-foreground truncate">
                                        {candidate.license_note}
                                    </div>
                                </div>
                                <div
                                    className={cn(
                                        "absolute top-2 right-2 px-2 py-0.5 rounded-full text-[10px] font-semibold",
                                        isSelected
                                            ? "bg-primary text-primary-foreground"
                                            : "bg-black/60 text-white"
                                    )}
                                >
                                    {isSelected ? "選択中" : "選択"}
                                </div>
                            </button>
                        )
                    })}
                </div>
            )}
        </div>
    )
}
