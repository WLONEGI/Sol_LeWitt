"use client"

import { useChatStore } from "@/features/chat/stores/chat"
import { cn } from "@/lib/utils"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { PanelLeft } from "lucide-react"

export function Header({
    className,
    showSidebarTrigger = true,
}: {
    className?: string
    showSidebarTrigger?: boolean
}) {
    const { currentThreadId, threads } = useChatStore()

    // Find current title from store
    const currentThread = threads.find(t => t.id === currentThreadId)
    const title = currentThread?.title || "New Chat"

    return (
        <header className={cn(
            "w-full h-12 flex items-center shrink-0 border-b-0 select-none",
            "bg-background/80 backdrop-blur-sm z-50",
            className
        )}>
            <div className="grid grid-cols-[1fr_auto_1fr] items-center w-full px-4">
                <div className="flex items-center">
                    {showSidebarTrigger ? (
                        <SidebarTrigger className="h-8 w-8 md:hidden text-muted-foreground hover:text-foreground hover:bg-black/5 rounded-lg">
                            <PanelLeft className="h-4 w-4" />
                        </SidebarTrigger>
                    ) : null}
                </div>
                <div className="flex items-center justify-center">
                    <span className="font-medium text-sm text-foreground/80 truncate">
                        {title}
                    </span>
                </div>
                <div />
            </div>
        </header>
    )
}
