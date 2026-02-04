import { useEffect, useState } from "react"
import { useChatStore } from "../stores/chat"
import { Plus, MessageSquare } from "lucide-react"
import { cn } from "@/lib/utils"
import { useRouter } from "next/navigation"
import {
    Sidebar,
    SidebarContent,
    SidebarGroup,
    SidebarGroupContent,
    SidebarGroupLabel,
    SidebarHeader,
    SidebarMenu,
    SidebarMenuButton,
    SidebarMenuItem,
    SidebarRail,
    SidebarTrigger,
    useSidebar,
} from "@/components/ui/sidebar"

export function ChatSidebar() {
    const router = useRouter()
    const {
        threads,
        currentThreadId,
        setCurrentThreadId,
        fetchHistory,
        createSession,
    } = useChatStore()
    const { state } = useSidebar()
    const isCollapsed = state === "collapsed"

    const [hasMounted, setHasMounted] = useState(false)

    useEffect(() => {
        setHasMounted(true)
        fetchHistory()
    }, [fetchHistory])

    if (!hasMounted) return null

    return (
        <Sidebar collapsible="icon" className="border-r border-sidebar-border bg-sidebar shrink-0">
            {/* 1. Header Area: Toggle & New Chat */}
            <SidebarHeader className="px-3 pt-4">
                <div className="flex flex-col gap-2">
                    {/* Toggle Button - Using shadcn's Trigger for accessibility */}
                    <div className="flex items-center justify-start h-8 px-1">
                        <SidebarTrigger className="h-8 w-8 text-muted-foreground hover:text-foreground hover:bg-black/5 rounded-lg transition-colors" />
                    </div>

                    {/* New Chat Button */}
                    <SidebarMenu>
                        <SidebarMenuItem>
                            <SidebarMenuButton
                                onClick={() => {
                                    createSession();
                                    router.push('/');
                                }}
                                tooltip="New Chat"
                                className="h-9 w-full justify-start gap-3 rounded-md text-foreground/80 hover:bg-black/5 hover:text-foreground font-medium"
                            >
                                <Plus className="h-4 w-4 shrink-0" />
                                <span>New Chat</span>
                            </SidebarMenuButton>
                        </SidebarMenuItem>
                    </SidebarMenu>
                </div>
            </SidebarHeader>

            {/* 2. Content Area: History */}
            <SidebarContent className="mt-4 px-2">
                <SidebarGroup>
                    <SidebarGroupLabel className="px-4 mb-2 text-[10px] uppercase tracking-[0.1em] text-muted-foreground/60 font-bold">
                        History
                    </SidebarGroupLabel>
                    <SidebarGroupContent>
                        <SidebarMenu className="gap-0.5">
                            {threads.length > 0 ? (
                                threads.map((thread) => (
                                    <SidebarMenuItem key={thread.id}>
                                        <SidebarMenuButton
                                            isActive={currentThreadId === thread.id}
                                            onClick={() => {
                                                setCurrentThreadId(thread.id);
                                                router.push(`/chat/${thread.id}`);
                                            }}
                                            tooltip={thread.title || "New Chat"}
                                            className={cn(
                                                "w-full h-9 rounded-md transition-all duration-200",
                                                currentThreadId === thread.id
                                                    ? "bg-primary/10 text-primary font-semibold"
                                                    : "text-muted-foreground hover:bg-black/5 hover:text-foreground font-medium"
                                            )}
                                        >
                                            <MessageSquare className={cn("h-3.5 w-3.5 shrink-0", currentThreadId === thread.id ? "text-primary" : "opacity-60")} />
                                            <span className="truncate">{thread.title || "New Chat"}</span>
                                        </SidebarMenuButton>
                                    </SidebarMenuItem>
                                ))
                            ) : (
                                <div className="px-4 py-4 text-[12px] text-muted-foreground/40 italic">No history yet</div>
                            )}
                        </SidebarMenu>
                    </SidebarGroupContent>
                </SidebarGroup>
            </SidebarContent>

            <SidebarRail />
        </Sidebar>
    )
}
