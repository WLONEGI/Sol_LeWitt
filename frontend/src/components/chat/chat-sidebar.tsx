"use client"

import { useEffect, useState } from "react"
import { useChatStore } from "@/store/chat"
import { Button } from "@/components/ui/button"
import { Plus, MessageSquare } from "lucide-react"
import { cn } from "@/lib/utils"

export function ChatSidebar() {
    const {
        threads,
        currentThreadId,
        setCurrentThreadId,
        fetchHistory,
        createSession,
        isSidebarOpen
    } = useChatStore()

    const [hasMounted, setHasMounted] = useState(false)

    useEffect(() => {
        setHasMounted(true)
        fetchHistory()
    }, [fetchHistory])

    if (!hasMounted || !isSidebarOpen) return null

    return (
        <div className="w-[260px] h-full bg-background/20 backdrop-blur-md border-r border-white/5 flex flex-col shrink-0">
            <div className="p-4">
                <Button
                    variant="outline"
                    className="w-full justify-start gap-2 glass-button bg-white/10 hover:bg-white/20 border-white/20"
                    onClick={createSession}
                >
                    <Plus className="h-4 w-4" />
                    New Chat
                </Button>
            </div>

            <div className="flex-1 overflow-y-auto px-2">
                <div className="space-y-1">
                    {threads.map((thread) => (
                        <Button
                            key={thread.id}
                            variant="ghost"
                            className={cn(
                                "w-full justify-start gap-2 font-normal truncate transition-all duration-200",
                                currentThreadId === thread.id
                                    ? "bg-white/10 text-primary-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground hover:bg-white/5"
                            )}
                            onClick={() => setCurrentThreadId(thread.id)}
                        >
                            <MessageSquare className="h-4 w-4 shrink-0" />
                            <span className="truncate text-xs">{thread.title || "New Chat"}</span>
                        </Button>
                    ))}
                </div>
            </div>
        </div>
    )
}
