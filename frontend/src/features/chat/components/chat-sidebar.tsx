"use client"

import { useEffect, useState } from "react"
import { useChatStore } from "../store/chat"
import { Button } from "@/components/ui/button"
import { Plus, MessageSquare, PanelLeftClose } from "lucide-react"
import { cn } from "@/lib/utils"
import { useRouter } from "next/navigation"

export function ChatSidebar() {
    const router = useRouter()
    const {
        threads,
        currentThreadId,
        setCurrentThreadId,
        fetchHistory,
        createSession,
        isSidebarOpen,
        setSidebarOpen
    } = useChatStore()

    const [hasMounted, setHasMounted] = useState(false)

    useEffect(() => {
        setHasMounted(true)
        fetchHistory()
    }, [fetchHistory])

    if (!hasMounted || !isSidebarOpen) return null

    return (
        <div className="w-[260px] h-full bg-sidebar border-r border-sidebar-border flex flex-col shrink-0 transition-all duration-300">
            <div className="p-4 flex flex-col gap-4">
                <div className="flex justify-between items-center">
                    <span className="font-semibold text-sm pl-2">Chat History</span>
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setSidebarOpen(false)}
                        className="h-8 w-8 text-gray-400 hover:text-foreground hover:bg-gray-100"
                    >
                        <PanelLeftClose className="h-4 w-4" />
                    </Button>
                </div>
                <Button
                    variant="outline"
                    className="w-full justify-start gap-2 h-10 rounded-lg bg-white text-foreground border border-gray-200 hover:bg-gray-50 transition-all font-normal"
                    onClick={() => {
                        createSession();
                        router.push('/');
                    }}
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
                                "w-full justify-start gap-3 font-medium truncate transition-all duration-200 h-10 rounded-lg px-3 mb-1",
                                currentThreadId === thread.id
                                    ? "bg-gray-200/60 text-foreground font-semibold"
                                    : "bg-transparent text-gray-500 hover:bg-gray-100/50 hover:text-gray-700"
                            )}
                            onClick={() => {
                                setCurrentThreadId(thread.id);
                                router.push(`/chat/${thread.id}`);
                            }}
                        >
                            <MessageSquare className={cn("h-4 w-4 shrink-0", currentThreadId === thread.id ? "opacity-100" : "opacity-70")} />
                            <span className="truncate text-sm">{thread.title || "New Chat"}</span>
                        </Button>
                    ))}
                </div>
            </div>
        </div>
    )
}
