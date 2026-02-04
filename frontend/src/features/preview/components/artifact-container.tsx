"use client"

import { ReactNode } from "react"
import { Button } from "@/components/ui/button"
import { X, Monitor, Maximize2, Minus, MoreHorizontal } from "lucide-react"
import { useArtifactStore } from "@/features/preview/stores/artifact"
import { cn } from "@/lib/utils"
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
} from "@/components/ui/tooltip"

interface ArtifactContainerProps {
    title: string
    subtitle?: string
    children: ReactNode
    footer?: ReactNode
    status?: string
}

export function ArtifactContainer({
    title,
    subtitle,
    children,
    footer,
    status
}: ArtifactContainerProps) {
    const { setPreviewOpen } = useArtifactStore()

    return (
        <div className="h-full w-full p-4 lg:p-6 flex flex-col min-w-0">
            <div className="flex-1 flex flex-col bg-card border border-border shadow-2xl rounded-2xl overflow-hidden relative group/window">
                {/* macOS style header */}
                <div className="h-12 border-b border-border bg-muted/30 flex items-center px-4 justify-between shrink-0">
                    <div className="flex items-center gap-3 min-w-0">
                        <div className="flex gap-1.5 px-1">
                            <div className="w-3 Valid h-3 rounded-full bg-red-500/80 cursor-pointer hover:bg-red-500 transition-colors" onClick={() => setPreviewOpen(false)} />
                            <div className="w-3 h-3 rounded-full bg-amber-500/80" />
                            <div className="w-3 h-3 rounded-full bg-emerald-500/80" />
                        </div>
                        <div className="h-4 w-px bg-border mx-1" />
                        <div className="flex items-center gap-2 min-w-0">
                            <Monitor className="h-4 w-4 text-muted-foreground shrink-0" />
                            <div className="flex flex-col min-w-0">
                                <span className="text-xs font-semibold truncate leading-none mb-0.5">{title}</span>
                                {subtitle && <span className="text-[10px] text-muted-foreground truncate leading-none">{subtitle}</span>}
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center gap-2">
                        {status === 'streaming' && (
                            <div className="flex items-center gap-1.5 mr-2">
                                <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                                <span className="text-[10px] font-medium text-primary uppercase tracking-wider">Live</span>
                            </div>
                        )}
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-7 w-7 rounded-md hover:bg-muted opacity-0 group-hover/window:opacity-100 transition-opacity">
                                    <MoreHorizontal className="h-4 w-4" />
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent>Options</TooltipContent>
                        </Tooltip>

                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 rounded-md hover:bg-destructive/10 hover:text-destructive opacity-0 group-hover/window:opacity-100 transition-opacity"
                                    onClick={() => setPreviewOpen(false)}
                                >
                                    <X className="h-4 w-4" />
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent>Close Preview</TooltipContent>
                        </Tooltip>
                    </div>
                </div>

                {/* Content Area */}
                <div className="flex-1 min-h-0 relative bg-background">
                    {children}
                </div>

                {/* Footer / Status Bar (Optional) */}
                {footer ? (
                    <div className="shrink-0 border-t border-border bg-muted/30 px-4 py-2 flex items-center justify-between text-[10px] text-muted-foreground">
                        {footer}
                    </div>
                ) : (
                    status && (
                        <div className="shrink-0 border-t border-border bg-muted/10 px-4 py-1.5 flex items-center justify-between">
                            <div className="text-[10px] text-muted-foreground uppercase tracking-widest font-semibold flex items-center gap-2">
                                <span className="w-1 h-1 rounded-full bg-muted-foreground/40" />
                                {status}
                            </div>
                        </div>
                    )
                )}
            </div>
        </div>
    )
}
