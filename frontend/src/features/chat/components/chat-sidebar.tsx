"use client"
import { useEffect, useState } from "react"
import { useChatStore } from "../stores/chat"
import { useShallow } from 'zustand/react/shallow'
import { Loader2, MessageSquare, PanelLeft, SquarePen, History, Presentation, Palette, BookOpen } from "lucide-react"
import { cn } from "@/lib/utils"

const getIconForProduct = (productType?: string) => {
    switch (productType) {
        case "slide_infographic":
            return Presentation;
        case "document_design":
            return Palette;
        case "comic":
            return BookOpen;
        default:
            return MessageSquare;
    }
}
import Link from "next/link"
import { useRouter } from "next/navigation"
import { UserAccountMenu } from "@/features/chat/components/user-account-menu"
import { useAuth } from "@/providers/auth-provider"
import {
    Sidebar,
    SidebarContent,
    SidebarGroup,
    SidebarGroupContent,
    SidebarGroupLabel,
    SidebarHeader,
    SidebarFooter,
    SidebarMenu,
    SidebarMenuButton,
    SidebarMenuItem,

    SidebarTrigger,
    useSidebar,
} from "@/components/ui/sidebar"

export function ChatSidebar() {
    const router = useRouter()
    const {
        threads,
        historyLoading,
        historyError,
        currentThreadId,
        setCurrentThreadId,
        fetchHistory,
        createSession,
        resetForAuthBoundary,
    } = useChatStore(
        useShallow((state) => ({
            threads: state.threads,
            historyLoading: state.historyLoading,
            historyError: state.historyError,
            currentThreadId: state.currentThreadId,
            setCurrentThreadId: state.setCurrentThreadId,
            fetchHistory: state.fetchHistory,
            createSession: state.createSession,
            resetForAuthBoundary: state.resetForAuthBoundary,
        }))
    )
    const { token, loading: authLoading } = useAuth()
    const { state } = useSidebar()
    const isCollapsed = state === "collapsed"

    const [hasMounted, setHasMounted] = useState(false)
    const [historyPopoverOpen, setHistoryPopoverOpen] = useState(false)

    // Close history popover when clicking outside
    useEffect(() => {
        if (!historyPopoverOpen) return
        const handleClickOutside = (e: MouseEvent) => {
            const target = e.target as HTMLElement
            if (!target.closest('[data-history-popover]')) {
                setHistoryPopoverOpen(false)
            }
        }
        document.addEventListener('click', handleClickOutside)
        return () => document.removeEventListener('click', handleClickOutside)
    }, [historyPopoverOpen])
    useEffect(() => {
        setHasMounted(true)
    }, [])

    useEffect(() => {
        if (authLoading) return
        if (!token) {
            resetForAuthBoundary()
            return
        }
        void fetchHistory(token)
    }, [authLoading, fetchHistory, resetForAuthBoundary, token])

    const handleRetryHistory = () => {
        if (!token || authLoading) return
        void fetchHistory(token)
    }

    if (!hasMounted) return null

    return (
        <Sidebar collapsible="icon" className="border-r border-sidebar-border bg-sidebar shrink-0">
            {/* 1. Header Area: Toggle & New Chat */}
            <SidebarHeader className={cn("px-1 pt-2", isCollapsed && "px-0")}>
                <div className="flex flex-col gap-1">
                    <div className={cn("flex items-center h-10 w-full", isCollapsed ? "justify-center" : "justify-between pl-3 pr-2")}>
                        {!isCollapsed ? (
                            <Link href="/" className="text-base font-semibold tracking-[0.2em] text-foreground hover:opacity-80 transition-opacity">
                                SPELL
                            </Link>
                        ) : null}
                        <SidebarTrigger className={cn("h-10 w-10 text-muted-foreground hover:text-foreground hover:bg-black/5 rounded-lg transition-colors flex items-center justify-center", isCollapsed && "mx-auto")}>
                            <PanelLeft className="h-6 w-6 shrink-0" aria-label="Toggle Sidebar" />
                        </SidebarTrigger>
                    </div>

                    {/* New Chat Button */}
                    <SidebarMenu className={cn(isCollapsed && "items-center")}>
                        <SidebarMenuItem>
                            <SidebarMenuButton
                                onClick={() => {
                                    createSession();
                                    router.push('/');
                                }}
                                tooltip="New Chat"
                                className={cn(
                                    "h-10 w-full rounded-md text-foreground/80 hover:bg-black/5 hover:text-foreground font-medium transition-all duration-200",
                                    isCollapsed ? "w-10 !p-0 justify-center" : "justify-start gap-4 px-3"
                                )}
                            >
                                <SquarePen className="h-6 w-6 shrink-0" aria-hidden="true" />
                                <span>New Chat</span>
                            </SidebarMenuButton>
                        </SidebarMenuItem>
                    </SidebarMenu>
                </div>
            </SidebarHeader>

            {/* 2. Content Area: History */}
            <SidebarContent className={cn("mt-2 px-1", isCollapsed && "px-0")}>
                <SidebarGroup className={cn("p-0", isCollapsed && "items-center")}>
                    <SidebarGroupLabel className="px-3 mb-1 text-[11px] uppercase tracking-[0.1em] text-muted-foreground/60 font-bold">
                        History
                    </SidebarGroupLabel>
                    <SidebarGroupContent>
                        {isCollapsed ? (
                            <SidebarMenu className="gap-0.5">
                                <SidebarMenuItem data-history-popover className="relative group/history">
                                    <SidebarMenuButton
                                        onClick={() => setHistoryPopoverOpen(!historyPopoverOpen)}
                                        className="h-10 w-10 flex items-center justify-center rounded-md text-muted-foreground hover:bg-black/5 hover:text-foreground mx-auto"
                                    >
                                        <History className="h-6 w-6 shrink-0" aria-label="Show History" />
                                    </SidebarMenuButton>
                                    {historyPopoverOpen && (
                                        <div data-history-popover className="absolute left-full top-0 ml-3 w-80 z-50">
                                            <div className="rounded-xl border border-sidebar-border bg-background shadow-xl">
                                                <div className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-[0.12em] text-muted-foreground/70 font-semibold">
                                                    History
                                                </div>
                                                <div className="flex flex-col gap-1 p-2 pt-1 max-h-[60vh] overflow-auto">
                                                    {historyLoading ? (
                                                        <div className="px-2 py-3 text-[12px] text-muted-foreground inline-flex items-center gap-2">
                                                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                                            Loading history...
                                                        </div>
                                                    ) : historyError ? (
                                                        <div className="px-2 py-2 flex flex-col gap-2">
                                                            <div className="text-[12px] text-rose-600">{historyError}</div>
                                                            <button
                                                                type="button"
                                                                onClick={handleRetryHistory}
                                                                className="w-fit rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700 hover:bg-rose-100"
                                                            >
                                                                Retry
                                                            </button>
                                                        </div>
                                                    ) : threads.length > 0 ? (
                                                        threads.map((thread) => {
                                                            const Icon = getIconForProduct(thread.product_type);
                                                            return (
                                                                <button
                                                                    key={thread.id}
                                                                    onClick={() => {
                                                                        setCurrentThreadId(thread.id);
                                                                        router.push(`/chat/${thread.id}`);
                                                                    }}
                                                                    className={cn(
                                                                        "flex items-center gap-2 rounded-md px-3 py-1.5 text-left text-sm transition-colors",
                                                                        currentThreadId === thread.id
                                                                            ? "bg-primary/10 text-primary font-semibold"
                                                                            : "text-muted-foreground hover:bg-black/5 hover:text-foreground"
                                                                    )}
                                                                >
                                                                    <Icon className={cn("h-4 w-4 shrink-0", currentThreadId === thread.id ? "text-primary" : "opacity-60")} />
                                                                    <span className="truncate">{thread.title || "New Chat"}</span>
                                                                </button>
                                                            )
                                                        })
                                                    ) : (
                                                        <div className="px-3 py-3 text-[12px] text-muted-foreground/40 italic">No history yet</div>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </SidebarMenuItem>
                            </SidebarMenu>
                        ) : (
                            <SidebarMenu className="gap-1">
                                {historyLoading ? (
                                    <div className="px-4 py-4 text-[13px] text-muted-foreground inline-flex items-center gap-2">
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                        Loading history...
                                    </div>
                                ) : historyError ? (
                                    <div className="px-4 py-3 flex flex-col gap-2">
                                        <div className="text-[12px] text-rose-600">{historyError}</div>
                                        <button
                                            type="button"
                                            onClick={handleRetryHistory}
                                            className="w-fit rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700 hover:bg-rose-100"
                                        >
                                            Retry
                                        </button>
                                    </div>
                                ) : threads.length > 0 ? (
                                    threads.map((thread) => {
                                        const Icon = getIconForProduct(thread.product_type);
                                        return (
                                            <SidebarMenuItem key={thread.id}>
                                                <SidebarMenuButton
                                                    isActive={currentThreadId === thread.id}
                                                    onClick={() => {
                                                        setCurrentThreadId(thread.id);
                                                        router.push(`/chat/${thread.id}`);
                                                    }}
                                                    tooltip={thread.title || "New Chat"}
                                                    className={cn(
                                                        "w-full h-8 rounded-md transition-all duration-200 justify-start gap-3 px-2",
                                                        currentThreadId === thread.id
                                                            ? "bg-primary/10 text-primary font-semibold"
                                                            : "text-foreground hover:bg-black/5 font-medium"
                                                    )}
                                                >
                                                    <Icon className={cn("h-4 w-4 shrink-0", currentThreadId === thread.id ? "text-primary" : "opacity-70")} />
                                                    <span className="truncate">{thread.title || "New Chat"}</span>
                                                </SidebarMenuButton>
                                            </SidebarMenuItem>
                                        )
                                    })
                                ) : (
                                    <div className="px-4 py-4 text-[13px] text-muted-foreground/40 italic">No history yet</div>
                                )}
                            </SidebarMenu>
                        )}
                    </SidebarGroupContent>
                </SidebarGroup>
            </SidebarContent>

            <SidebarFooter className={cn("relative px-1 pb-4", isCollapsed && "px-0 items-center")}>
                <UserAccountMenu collapsed={isCollapsed} />
            </SidebarFooter>


        </Sidebar>
    )
}
