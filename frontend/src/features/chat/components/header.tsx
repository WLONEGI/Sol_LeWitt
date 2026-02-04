"use client"

import { useChatStore } from "@/features/chat/stores/chat"
import { cn } from "@/lib/utils"

export function Header({ className }: { className?: string }) {
    const { currentThreadId, threads } = useChatStore()

    // Find current title from store
    const currentThread = threads.find(t => t.id === currentThreadId)
    const title = currentThread?.title || "New Chat"

    return (
        <header className={cn(
            "w-full h-12 flex items-center justify-center shrink-0 border-b-0 select-none",
            "bg-background/80 backdrop-blur-sm z-50",
            className
        )}>
            <div className="flex items-center gap-2 max-w-xl mx-auto px-4 w-full justify-center">
                <span className="font-medium text-sm text-foreground/80 truncate">
                    {title}
                </span>
            </div>
        </header>
    )
}
