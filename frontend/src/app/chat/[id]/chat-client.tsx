"use client"

import { Loader2 } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"

import { Header } from "@/features/chat/components/header"
import { ChatInterface } from "@/features/chat/components/chat-interface"
import { ArtifactView } from "@/features/preview/components/artifact-view"
import { ChatSidebar } from "@/features/chat/components/chat-sidebar"
import { useMemo } from "react"
import { useShallow } from "zustand/react/shallow"
import { cn } from "@/lib/utils"
import { useChatStore } from "@/features/chat/stores/chat"
import { useArtifactStore } from "@/features/preview/stores/artifact"
import { QUICK_ACTIONS } from "@/features/chat/constants/quick-actions"
import { useAuth } from "@/providers/auth-provider"

export function ChatClient({ id }: { id: string }) {
    const { user, loading } = useAuth()

    const { selectedActionId } = useChatStore(
        useShallow((state) => ({
            selectedActionId: state.selectedActionId,
        }))
    )

    const { isPreviewOpen } = useArtifactStore(
        useShallow((state) => ({
            isPreviewOpen: state.isPreviewOpen,
        }))
    )

    const selectedAction = useMemo(
        () => QUICK_ACTIONS.find((action) => action.id === selectedActionId) ?? null,
        [selectedActionId]
    )

    if (loading) {
        return (
            <main className="h-screen w-screen bg-background flex items-center justify-center">
                <div className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    認証情報を確認しています...
                </div>
            </main>
        )
    }

    return (
        <main className={cn(
            "h-screen w-screen overflow-hidden relative selection:bg-primary/20 flex transition-colors duration-700",
            selectedAction ? selectedAction.gradientClassName : "bg-background"
        )}>
            {user ? <ChatSidebar /> : null}
            <div className="flex flex-col flex-1 min-w-0 h-full">
                <Header showSidebarTrigger={Boolean(user)} />
                <div className="relative z-10 flex-1 w-full min-h-0">
                    <div className="flex h-full w-full overflow-hidden">
                        {/* Chat Interface - takes remaining space */}
                        <div className="flex-1 min-w-0 h-full">
                            <ChatInterface key={id} threadId={id} />
                        </div>

                        {/* Preview Panel - appears on right when open */}
                        <AnimatePresence mode="wait">
                            {isPreviewOpen && (
                                <motion.div
                                    initial={{ width: 0, opacity: 0 }}
                                    animate={{ width: 450, opacity: 1 }}
                                    exit={{ width: 0, opacity: 0 }}
                                    transition={{ duration: 0.3, ease: "easeInOut" }}
                                    className={cn(
                                        "shrink-0 overflow-hidden border-l border-border",
                                        "bg-background"
                                    )}
                                >
                                    <ArtifactView />
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                </div>
            </div>
        </main>
    )
}
