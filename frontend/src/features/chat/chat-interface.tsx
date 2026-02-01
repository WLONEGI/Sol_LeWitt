"use client"

import { useChat } from '@ai-sdk/react'
import { type UIMessage } from 'ai'
import { ChatList } from "./components/chat-list"
import { ChatInput } from "./components/chat-input"
import { useChatStore } from "./store/chat"
import { useArtifactStore } from "../preview/store/artifact"
import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { v4 as uuidv4 } from 'uuid'

import { ChatSidebar } from "./components/chat-sidebar"
import { useChatTimeline } from "./hooks/use-chat-timeline"
import { AgentStatusIndicator } from "./components/agent-status-indicator"
import { PanelLeftOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useRouter } from "next/navigation"

// Custom data events from backend
interface CustomDataEvent {
    type: string
    [key: string]: unknown
}

export function ChatInterface({ threadId }: { threadId?: string | null }) {
    const router = useRouter()
    const [input, setInput] = useState("")
    const [pendingFile, setPendingFile] = useState<File | null>(null)
    const [pendingFileBase64, setPendingFileBase64] = useState<string | null>(null)
    // DEBUG: Mock status for testing AgentStatusIndicator
    const [debugStatus, setDebugStatus] = useState<{
        stepId: string;
        status: 'in_progress' | 'completed';
        label: string;
        details?: string;
        agentName?: string;
    } | null>(null)
    const { setArtifact } = useArtifactStore()
    const { currentThreadId, setCurrentThreadId, isSidebarOpen, setSidebarOpen, updateThreadTitle } = useChatStore()

    // Stable ID for the session to prevent useChat resets on URL change
    const stableIdRef = useRef(threadId || uuidv4())
    const stableId = threadId || stableIdRef.current

    // Sync threadId from prop to store
    useEffect(() => {
        if (threadId && threadId !== currentThreadId) {
            setCurrentThreadId(threadId)
        }
    }, [threadId, currentThreadId, setCurrentThreadId])

    // Setup useChat with standard configuration (removing DefaultChatTransport)
    const {
        messages,
        setMessages,
        append,
        // Note: useChat returns 'append', 'reload', 'stop', etc. 
        // The original code used 'sendMessage' which likely was destructured from 'append' or mapped? 
        // Let's check original code: 'sendMessage' was mapped from... wait the original code destructured { sendMessage } from useChat. 
        // Standard useChat has 'append'. If 'sendMessage' was used, maybe it was an alias?
        // Let's use 'append' and alias it or check if sendMessage exists in this version.
        // Actually, typically it is 'append'. I will stick to 'append' and rename usage or check if I can rename here.
        status,
        error,
        data,
    } = useChat({
        id: stableId, // Use stable ID
        body: {
            thread_id: stableId, // Use stableId to ensure consistency
            ...(pendingFileBase64 && { pptx_template_base64: pendingFileBase64 }),
        },
        onError: (error: Error) => {
            console.error("Chat error:", error)
        },
        onFinish: (message: any) => {
            console.log("Chat finished:", message)
        }
    } as any) as any

    // Alias append to sendMessage for compatibility with existing code
    const sendMessage = append;

    // Use custom hook for timeline management
    const { timeline, currentAgentStatus } = useChatTimeline(messages, data, stableId)

    // History Loading
    useEffect(() => {
        const loadHistory = async () => {
            if (!threadId) { // Only load if we have a real threadId from prop
                setMessages([])
                return
            }

            try {
                const res = await fetch(`/api/threads/${threadId}/messages`)
                if (res.ok) {
                    const history = await res.json()
                    const mappedMessages: UIMessage[] = history.map((msg: any) => ({
                        id: msg.id || uuidv4(),
                        role: msg.role || 'assistant',
                        parts: msg.parts || [{ type: 'text', text: msg.content || '' }],
                        metadata: msg.metadata,
                    }))
                    setMessages(mappedMessages)
                }
            } catch (err) {
                console.error("Failed to load history:", err)
            }
        }
        loadHistory()
    }, [threadId, setMessages])

    const isLoading = status === 'streaming' || status === 'submitted'

    const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
        setInput(e.target.value)
    }, [])

    const handleFileSelect = useCallback((file: File) => {
        setPendingFile(file)
        const reader = new FileReader()
        reader.onloadend = () => {
            const base64 = reader.result as string
            const base64Clean = base64.split(',')[1] || base64
            setPendingFileBase64(base64Clean)
        }
        reader.readAsDataURL(file)
    }, [])

    const handleSend = useCallback((value: string) => {
        if (!value.trim()) return

        // If this is a new chat (no prop threadId), commit the stableId
        if (!threadId) {
            setCurrentThreadId(stableId)
            // Silent URL update to persist the ID visually without reloading
            window.history.replaceState(null, '', `/chat/${stableId}`)
        }

        // Use SDK v6 sendMessage API
        sendMessage({ parts: [{ type: 'text', text: value }] })

        setPendingFile(null)
        setPendingFileBase64(null)
        setInput("")
    }, [sendMessage, threadId, stableId, setCurrentThreadId])

    return (
        <div className="flex w-full h-full relative">
            <ChatSidebar />

            <div className="flex flex-col flex-1 h-full w-full min-w-0 relative">
                {!isSidebarOpen && (
                    <div className="absolute top-4 left-4 z-50">
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setSidebarOpen(true)}
                            className="h-8 w-8 text-gray-400 hover:text-foreground bg-white/50 backdrop-blur-sm border border-gray-200 shadow-sm"
                        >
                            <PanelLeftOpen className="h-4 w-4" />
                        </Button>
                    </div>
                )}

                <div className="flex-1 overflow-hidden relative z-10">
                    <ChatList
                        timeline={timeline}
                        isLoading={isLoading}
                        className="h-full"
                    />
                </div>

                <div className="p-4 relative z-30 pointer-events-none flex flex-col items-center gap-3">
                    {/* DEBUG: Development-only test panel for AgentStatusIndicator */}
                    {process.env.NODE_ENV === 'development' && (
                        <div className="pointer-events-auto mb-2 p-2 bg-slate-900/90 border border-slate-700 rounded-xl shadow-2xl flex flex-wrap gap-2 text-[10px] items-center">
                            <span className="font-bold text-slate-400 px-1 border-r border-slate-700 mr-1 uppercase tracking-wider">Debug UI</span>
                            <button
                                onClick={() => setDebugStatus({
                                    stepId: 'debug-coordinator',
                                    status: 'in_progress',
                                    label: 'Analyzing Request...',
                                    details: 'Decomposing user intent and specialized context...',
                                    agentName: 'coordinator'
                                })}
                                className="px-2 py-1 bg-indigo-600/20 text-indigo-300 border border-indigo-500/30 rounded hover:bg-indigo-600/40 transition-colors"
                            >
                                1. Coordinator
                            </button>
                            <button
                                onClick={() => setDebugStatus({
                                    stepId: 'debug-planner',
                                    status: 'in_progress',
                                    label: 'Planning Execution...',
                                    details: 'Generating step-by-step resolution strategy...',
                                    agentName: 'planner'
                                })}
                                className="px-2 py-1 bg-purple-600/20 text-purple-300 border border-purple-500/30 rounded hover:bg-purple-600/40 transition-colors"
                            >
                                2. Planner
                            </button>
                            <button
                                onClick={() => setDebugStatus({
                                    stepId: 'debug-researcher',
                                    status: 'in_progress',
                                    label: 'Researcher Working...',
                                    details: 'Fetching deep market analytics and processing multi-source data for a very long comprehensive report summary check',
                                    agentName: 'supervisor' // Using supervisor for a different icon
                                })}
                                className="px-2 py-1 bg-blue-600/20 text-blue-300 border border-blue-500/30 rounded hover:bg-blue-600/40 transition-colors"
                            >
                                3. Long Name
                            </button>
                            <button
                                onClick={() => setDebugStatus({
                                    stepId: 'debug-complete',
                                    status: 'completed',
                                    label: 'Completed',
                                    details: 'Success: Output finalized and ready.',
                                    agentName: 'coordinator'
                                })}
                                className="px-2 py-1 bg-emerald-600/20 text-emerald-300 border border-emerald-500/30 rounded hover:bg-emerald-600/40 transition-colors"
                            >
                                4. Finalize
                            </button>
                            <button
                                onClick={() => setDebugStatus(null)}
                                className="px-2 py-1 bg-slate-700/50 text-slate-300 border border-slate-600 rounded hover:bg-slate-700 hover:text-white transition-colors"
                            >
                                Clear
                            </button>
                        </div>
                    )}

                    {/* Agent Status Indicator */}
                    {(isLoading && currentAgentStatus || debugStatus) && (
                        <AgentStatusIndicator
                            status={(debugStatus || currentAgentStatus) as any}
                            isActive={isLoading || !!debugStatus}
                            className="pointer-events-auto"
                        />
                    )}

                    {error && (
                        <div className="w-full max-w-3xl pointer-events-auto mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">
                            {error.message || "An error occurred during the session."}
                        </div>
                    )}
                    <div className="w-full max-w-3xl pointer-events-auto">
                        <ChatInput
                            value={input}
                            onChange={handleInputChange}
                            onSend={handleSend}
                            isLoading={isLoading}
                            onFileSelect={handleFileSelect}
                            selectedFile={pendingFile}
                            onClearFile={() => { setPendingFile(null); setPendingFileBase64(null) }}
                        />
                    </div>
                </div>
            </div>
        </div>
    )
}
