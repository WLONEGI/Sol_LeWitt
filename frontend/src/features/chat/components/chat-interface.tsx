"use client"

import { useChat } from '@ai-sdk/react'
import { type UIMessage } from 'ai'
import { ChatList } from "./chat-list"
import { ChatInput } from "./chat-input"
import { useChatStore } from "@/features/chat/stores/chat"
import { useResearchStore } from "@/features/preview/stores/research"
import { useEffect, useState, useCallback, useRef } from 'react'
import { shallow } from "zustand/shallow"
import { v4 as uuidv4 } from 'uuid'


import { useChatTimeline } from "../hooks/use-chat-timeline"
import { AgentStatusIndicator } from "./agent-status-indicator"
import { FixedPlanOverlay } from "./fixed-plan-overlay"
import { PanelLeftOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useRouter } from "next/navigation"

// Custom data events from backend
interface CustomDataEvent {
    type: string
    [key: string]: unknown
}

const MAX_DATA_EVENTS = 200
const DATA_EVENTS_TO_STORE = new Set([
    'data-plan',
    'data-outline',
])

export function ChatInterface({ threadId }: { threadId?: string | null }) {
    const router = useRouter()
    const [input, setInput] = useState("")
    const [pendingFile, setPendingFile] = useState<File | null>(null)
    const [pendingFileBase64, setPendingFileBase64] = useState<string | null>(null)

    const { registerTask, appendContent, setCitations, completeTask } = useResearchStore(
        (state) => ({
            registerTask: state.registerTask,
            appendContent: state.appendContent,
            setCitations: state.setCitations,
            completeTask: state.completeTask,
        }),
        shallow
    )
    const { currentThreadId, setCurrentThreadId, updateThreadTitle } = useChatStore(
        (state) => ({
            currentThreadId: state.currentThreadId,
            setCurrentThreadId: state.setCurrentThreadId,
            updateThreadTitle: state.updateThreadTitle,
        }),
        shallow
    )

    const [generatedId] = useState(() => uuidv4())
    const stableId = threadId || currentThreadId || generatedId

    useEffect(() => {
        if (threadId && threadId !== currentThreadId) {
            setCurrentThreadId(threadId)
        }
    }, [threadId, currentThreadId, setCurrentThreadId])

    const [data, setData] = useState<CustomDataEvent[]>([])
    const dataRef = useRef<CustomDataEvent[]>([])
    const dataFlushRef = useRef<number | null>(null)

    const flushData = useCallback(() => {
        dataFlushRef.current = null
        setData([...dataRef.current])
    }, [])

    const enqueueData = useCallback((event: CustomDataEvent) => {
        if (!DATA_EVENTS_TO_STORE.has(event.type)) return
        const next = [...dataRef.current, event]
        dataRef.current = next.length > MAX_DATA_EVENTS ? next.slice(-MAX_DATA_EVENTS) : next
        if (dataFlushRef.current == null) {
            dataFlushRef.current = window.requestAnimationFrame(flushData)
        }
    }, [flushData])

    const {
        messages,
        setMessages,
        sendMessage,
        addToolResult,
        status,
        error,
    } = useChat({
        id: stableId,
        onData: (newData) => {
            const data = newData as CustomDataEvent
            enqueueData(data)

            if (data?.type === 'data-title-update' && data.title && stableId) {
                updateThreadTitle(stableId, data.title as string)
            }

            if (data?.type === 'data-research-start' && data.data) {
                registerTask(data.data.task_id, data.data.perspective)
            }
            if (data?.type === 'data-research-token' && data.data) {
                appendContent(data.data.task_id, data.data.token)
            }
            if (data?.type === 'data-citation' && data.data) {
                setCitations(data.data.task_id, data.data.sources)
            }
            if (data?.type === 'data-research-complete' && data.data) {
                completeTask(data.data.task_id)
            }
        },
        onError: (error: Error) => {
            console.error("Chat error:", error)
        }
    })

    const { timeline, latestOutline, latestPlan } = useChatTimeline(messages, data, stableId)

    useEffect(() => {
        let isCancelled = false
        const loadHistory = async () => {
            if (!stableId) return
            try {
                const res = await fetch(`/api/threads/${stableId}/messages`)
                if (isCancelled) return
                if (res.ok) {
                    const history = await res.json()
                    if (isCancelled) return
                    const mappedMessages: UIMessage[] = history.map((msg: any) => ({
                        id: msg.id || uuidv4(),
                        role: msg.role || 'assistant',
                        parts: msg.parts || [{ type: 'text', text: msg.content || '' }],
                        metadata: msg.metadata,
                        toolInvocations: msg.tool_calls ? msg.tool_calls.map((tc: any) => ({
                            toolCallId: tc.id,
                            toolName: tc.function.name,
                            args: JSON.parse(tc.function.arguments || '{}'),
                            state: 'call'
                        })) : undefined
                    }))
                    setMessages(mappedMessages)
                    dataRef.current = []
                    setData([])
                }
            } catch (err) {
                if (!isCancelled) console.error("Failed to load history:", err)
            }
        }
        loadHistory()
        return () => { isCancelled = true }
    }, [stableId, setMessages])

    useEffect(() => {
        return () => {
            if (dataFlushRef.current != null) {
                window.cancelAnimationFrame(dataFlushRef.current)
            }
        }
    }, [])

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
        if (!threadId && stableId !== currentThreadId) {
            setCurrentThreadId(stableId)
            window.history.replaceState(null, '', `/chat/${stableId}`)
        }
        sendMessage(
            { text: value },
            {
                body: {
                    thread_id: stableId,
                    ...(pendingFileBase64 && { pptx_template_base64: pendingFileBase64 }),
                }
            }
        )
        setPendingFile(null)
        setPendingFileBase64(null)
        setInput("")
    }, [sendMessage, threadId, stableId, setCurrentThreadId, pendingFileBase64])

    return (
        <div className="flex w-full h-full relative">
            <div className="flex flex-col flex-1 h-full w-full min-w-0 relative">
                <div className="flex-1 overflow-hidden relative z-10">
                    <ChatList
                        timeline={timeline}
                        latestOutline={latestOutline}
                        isLoading={isLoading}
                        className="h-full"
                    />
                </div>

                <div className="p-4 relative z-30 pointer-events-none flex flex-col items-center gap-3">
                    {/* Active Researcher Status */}

                    {/* Agent Status Indicator - Removed legacy ui_step_update support */}

                    {error && (
                        <div className="w-full max-w-3xl pointer-events-auto mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">
                            {error.message || "An error occurred during the session."}
                        </div>
                    )}

                    {/* Fixed Execution Plan Overlay */}
                    {latestPlan && (
                        <FixedPlanOverlay
                            data={latestPlan}
                            className="pointer-events-auto"
                        />
                    )}

                    <div className="w-full pointer-events-auto">
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
