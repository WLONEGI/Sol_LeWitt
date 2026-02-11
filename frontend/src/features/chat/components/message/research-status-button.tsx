
"use client"

import { Button } from "@/components/ui/button"
import { Search } from "lucide-react"
import { cn } from "@/lib/utils"
import { useArtifactStore } from "@/features/preview/stores/artifact"

interface ResearchStatusButtonProps {
    taskId: string;
    perspective: string;
    status: 'running' | 'completed';
}

export function ResearchStatusButton({ taskId, perspective, status }: ResearchStatusButtonProps) {
    const { setActiveContextId, setPreviewOpen } = useArtifactStore()

    const handleClick = () => {
        setActiveContextId(taskId)
        setPreviewOpen(true)
    }

    return (
        <>
            <style>{`
                @keyframes searching-flow {
                    0% { background-position: -200% center; }
                    100% { background-position: 200% center; }
                }
                .animate-searching-flow {
                    background: linear-gradient(
                        90deg,
                        currentColor 0%,
                        currentColor 40%,
                        #9F7AEA 50%,
                        currentColor 60%,
                        currentColor 100%
                    );
                    background-size: 200% auto;
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    animation: searching-flow 2s linear infinite;
                }
            `}</style>
            <Button
                variant="secondary"
                className={cn(
                    "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                    "bg-white hover:bg-white/90 border-muted-foreground/20 text-muted-foreground",
                    status === 'running' ? "opacity-100" : "opacity-80"
                )}
                onClick={handleClick}
            >
                <Search className="h-3.5 w-3.5" />
                <span className={cn(
                    "tracking-wide",
                    status === 'running' && "animate-searching-flow"
                )}>
                    Searching
                </span>
                <span className="text-foreground">{perspective}</span>
            </Button>
        </>
    )
}
