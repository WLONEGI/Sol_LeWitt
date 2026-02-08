"use client"

import { ReactNode } from "react"
import { Button } from "@/components/ui/button"
import { X, Monitor, MoreHorizontal } from "lucide-react"
import { useArtifactStore } from "@/features/preview/stores/artifact"
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
}

export function ArtifactContainer({
    title,
    subtitle,
    children,
    footer
}: ArtifactContainerProps) {
    const { setPreviewOpen } = useArtifactStore()

    return (
        <div className="h-full w-full flex flex-col min-w-0">
            <div className="flex-1 flex flex-col bg-transparent overflow-hidden relative group/window">
                {/* Minimalist header - Matched to Chat Header style */}
                <div className="h-12 border-b border-border/50 bg-background/80 backdrop-blur-sm flex items-center px-4 justify-between shrink-0">
                    <div className="flex items-center gap-3 min-w-0">
                        <div className="flex items-center gap-2 min-w-0">
                            <Monitor className="h-4 w-4 text-muted-foreground shrink-0" />
                            <div className="flex flex-col min-w-0 justify-center">
                                <span className="text-sm font-medium text-foreground/80 truncate leading-none mb-0.5">{title}</span>
                                {subtitle && <span className="text-[10px] text-muted-foreground truncate leading-none">{subtitle}</span>}
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center gap-2">
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg hover:bg-muted opacity-0 group-hover/window:opacity-100 transition-opacity">
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
                                    className="h-8 w-8 rounded-lg hover:bg-destructive/10 hover:text-destructive opacity-0 group-hover/window:opacity-100 transition-opacity"
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
                <div className="flex-1 min-h-0 relative bg-transparent flex flex-col">
                    {children}
                </div>

                {/* Footer / Status Bar (Optional) */}
                {footer ? (
                    <div className="shrink-0 border-t border-border/50 bg-background/50 backdrop-blur-sm px-3 py-1.5 flex items-center justify-between text-[10px] text-muted-foreground">
                        {footer}
                    </div>
                ) : null}
            </div>
        </div>
    )
}
