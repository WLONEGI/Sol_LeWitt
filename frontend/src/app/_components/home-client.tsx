"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { v4 as uuidv4 } from "uuid"
import { useShallow } from "zustand/react/shallow"

import { SidebarProvider } from "@/components/ui/sidebar"
import { cn } from "@/lib/utils"
import { useChatStore } from "@/features/chat/stores/chat"
import { useAuth } from "@/providers/auth-provider"
import { ChatSidebar } from "@/features/chat/components/chat-sidebar"
import { ChatInput } from "@/features/chat/components/chat-input"
import { MainHeader } from "@/app/_components/main-header"
import { QUICK_ACTIONS, type QuickActionId } from "@/features/chat/constants/quick-actions"
import { AuthRequiredDialog } from "@/features/auth/components/auth-required-dialog"

export function HomeClient() {
  const router = useRouter()
  const { user, token, loading: authLoading, error: authError, signInWithGoogle } = useAuth()
  const [input, setInput] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showAuthDialog, setShowAuthDialog] = useState(false)

  const {
    createSession,
    setCurrentThreadId,
    setPendingMessage,
    consumePendingHomeInput,
    selectedActionId,
    setSelectedActionId,
  } = useChatStore(
    useShallow((state) => ({
      createSession: state.createSession,
      setCurrentThreadId: state.setCurrentThreadId,
      setPendingMessage: state.setPendingMessage,
      consumePendingHomeInput: state.consumePendingHomeInput,
      selectedActionId: state.selectedActionId,
      setSelectedActionId: state.setSelectedActionId,
    }))
  )

  // Reset session on mount to ensure "New Chat" logic works
  useEffect(() => {
    createSession()
    setSelectedActionId(null)
    const pending = consumePendingHomeInput()
    if (pending) setInput(pending)
  }, [consumePendingHomeInput, createSession, setSelectedActionId])

  const selectedAction = useMemo(
    () => QUICK_ACTIONS.find((action) => action.id === selectedActionId) ?? null,
    [selectedActionId]
  )

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
  }, [])

  const requestLogin = useCallback(async () => {
    await signInWithGoogle()
  }, [signInWithGoogle])

  const startChatFromHome = useCallback(
    (value: string) => {
      const threadId = uuidv4()
      setCurrentThreadId(threadId)
      setPendingMessage(threadId, value)
      setIsSubmitting(true)
      setInput("")
      router.push(`/chat/${threadId}`)
    },
    [router, setCurrentThreadId, setPendingMessage]
  )

  const handleSend = useCallback(
    async (value: string) => {
      if (!value.trim()) return
      if (!user || !token) {
        setShowAuthDialog(true)
        return
      }
      startChatFromHome(value)
    },
    [startChatFromHome, token, user]
  )

  useEffect(() => {
    if (!showAuthDialog) return
    if (authLoading || !user || !token) return
    setShowAuthDialog(false)
  }, [authLoading, showAuthDialog, token, user])

  const handleSelectAction = useCallback(
    (actionId: QuickActionId) => {
      setSelectedActionId(actionId)
    },
    [setSelectedActionId]
  )

  const handlePromptClick = useCallback((prompt: string) => {
    setInput(prompt)
  }, [])

  return (
    <main className="h-screen w-screen overflow-hidden bg-background relative selection:bg-primary/20 flex">
      <SidebarProvider defaultOpen={true}>
        {user ? <ChatSidebar /> : null}
        <div className="flex flex-col flex-1 min-w-0 h-full">
          {!user ? <MainHeader /> : null}
          <div className="relative z-10 flex-1 w-full min-h-0 overflow-auto">
            <div className="mx-auto flex w-full max-w-5xl flex-col items-center px-6 py-20 md:py-32">
              <div className="flex w-full flex-col items-center gap-12">
                <div className="text-center max-w-2xl px-4">
                  <h1 className="text-4xl md:text-6xl font-semibold text-foreground tracking-tight">
                    What can I do for you?
                  </h1>
                  <p className="mt-4 text-muted-foreground text-base md:text-lg">
                    Bring a goal or a rough idea. Spell will shape it into something real.
                  </p>
                </div>

                <div className="w-full max-w-3xl">
                  <ChatInput
                    value={input}
                    onChange={handleInputChange}
                    onSend={handleSend}
                    isLoading={isSubmitting}
                    placeholder="Assign a task or ask anything"
                    actionPill={
                      selectedAction
                        ? { label: selectedAction.pillLabel, icon: selectedAction.icon }
                        : undefined
                    }
                    onClearAction={() => setSelectedActionId(null)}
                  />
                </div>

                {!selectedAction ? (
                  <div className="flex w-full max-w-xl justify-center gap-12 md:gap-20">
                    {QUICK_ACTIONS.map((action) => {
                      const ActionIcon = action.icon
                      return (
                        <button
                          key={action.id}
                          type="button"
                          onClick={() => handleSelectAction(action.id)}
                          className="group flex flex-col items-center gap-3 transition-all hover:scale-105 active:scale-95"
                        >
                          <div
                            className={cn(
                              "flex h-16 w-16 items-center justify-center rounded-full transition-shadow duration-300",
                              "bg-white border border-transparent shadow-none hover:shadow-md", // No border/border-transparent
                              action.bubbleClassName
                            )}
                          >
                            <ActionIcon className="h-7 w-7" />
                          </div>
                          <span className="text-sm font-medium text-muted-foreground group-hover:text-foreground transition-colors">
                            {action.title}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                ) : (
                  <div className="w-full max-w-3xl animate-in fade-in slide-in-from-top-4 duration-500">
                    <div className="flex items-center justify-between px-2 mb-4">
                      <div className="flex items-center gap-2">
                        <selectedAction.icon className="h-4 w-4 text-primary" />
                        <span className="text-sm font-semibold">{selectedAction.title} Samples</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setSelectedActionId(null)}
                        className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                      >
                        Back to categories
                      </button>
                    </div>
                    <div className="grid grid-cols-1 gap-3">
                      {selectedAction.prompts.map((prompt) => (
                        <button
                          key={prompt}
                          type="button"
                          onClick={() => handlePromptClick(prompt)}
                          className="rounded-2xl border border-gray-100 bg-white/50 backdrop-blur-sm px-5 py-4 text-left text-sm text-gray-700 shadow-sm transition-all hover:border-primary/20 hover:bg-white hover:shadow-md"
                        >
                          {prompt}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </SidebarProvider>
      <AuthRequiredDialog
        open={showAuthDialog}
        onOpenChange={setShowAuthDialog}
        onLogin={requestLogin}
        isLoading={authLoading}
        error={authError}
      />
    </main>
  )
}
