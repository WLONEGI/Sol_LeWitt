"use client"

import { useChat } from '@ai-sdk/react'
import { type UIMessage } from 'ai'
import { ChatList } from "./chat-list"
import { ChatInput } from "./chat-input"
import { useChatStore } from "@/features/chat/stores/chat"
import { useArtifactStore } from "@/features/preview/stores/artifact"
import { useResearchStore } from "@/features/preview/stores/research"
import { useEffect, useState, useCallback, useRef } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { v4 as uuidv4 } from 'uuid'


import { useChatTimeline } from "../hooks/use-chat-timeline"
import { FixedPlanOverlay } from "./fixed-plan-overlay"
import { PanelLeftOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useRouter } from "next/navigation"

// Custom data events from backend
interface CustomDataEvent {
    type: string
    data?: any
    [key: string]: unknown
}

const MAX_DATA_EVENTS = 200
const DATA_EVENTS_TO_STORE = new Set([
    'data-plan_update',
    'data-outline',
    'data-visual-plan',
    'data-visual-prompt',
    'data-visual-image',
    'data-visual-pdf',
])

export function ChatInterface({ threadId }: { threadId?: string | null }) {
    const router = useRouter()
    const [input, setInput] = useState("")
    const [pendingFile, setPendingFile] = useState<File | null>(null)
    const [pendingFileBase64, setPendingFileBase64] = useState<string | null>(null)

    const { registerTask, appendContent, completeTask } = useResearchStore(
        useShallow((state) => ({
            registerTask: state.registerTask,
            appendContent: state.appendContent,
            completeTask: state.completeTask,
        }))
    )
    const { currentThreadId, setCurrentThreadId, updateThreadTitle } = useChatStore(
        useShallow((state) => ({
            currentThreadId: state.currentThreadId,
            setCurrentThreadId: state.setCurrentThreadId,
            updateThreadTitle: state.updateThreadTitle,
        }))
    )
    const { upsertArtifact } = useArtifactStore(
        useShallow((state) => ({
            upsertArtifact: state.upsertArtifact,
        }))
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

    const upsertSlideDeck = useCallback((payload: any) => {
        if (!payload) return
        const artifactId = typeof payload.artifact_id === 'string'
            ? payload.artifact_id
            : `visual_deck_${stableId}`

        const state = useArtifactStore.getState()
        const existing = state.artifacts[artifactId]
        const existingSlides = Array.isArray(existing?.content?.slides) ? existing?.content?.slides : []

        const mergeSlide = (slide_number: number, patch: any) => {
            const index = existingSlides.findIndex((s: any) => s.slide_number === slide_number)
            if (index >= 0) {
                const updated = { ...existingSlides[index], ...patch }
                return [...existingSlides.slice(0, index), updated, ...existingSlides.slice(index + 1)]
            }
            return [...existingSlides, { slide_number, ...patch }]
        }

        let nextSlides = existingSlides
        if (payload.slide_number) {
            let structuredPrompt = payload.structured_prompt
            if (typeof structuredPrompt === 'string') {
                try {
                    structuredPrompt = JSON.parse(structuredPrompt)
                } catch {
                    // keep as string if parsing fails
                }
            }
            const slidePatch: Record<string, any> = {
                slide_number: payload.slide_number,
                title: payload.title,
                image_url: payload.image_url,
                prompt_text: payload.prompt_text,
                structured_prompt: structuredPrompt,
                rationale: payload.rationale,
                layout_type: payload.layout_type,
                status: payload.status,
                selected_inputs: payload.selected_inputs,
            }
            Object.keys(slidePatch).forEach((key) => {
                if (slidePatch[key] === undefined || slidePatch[key] === null) {
                    delete slidePatch[key]
                }
            })
            nextSlides = mergeSlide(payload.slide_number, slidePatch)
        }

        const nextContent = {
            ...(existing?.content ?? {}),
            slides: nextSlides,
            pdf_url: payload.pdf_url ?? existing?.content?.pdf_url,
            plan: payload.plan ?? existing?.content?.plan,
        }

        const deckTitle = payload.deck_title || payload.title || existing?.title || "Generated Slides"
        const status = payload.status || existing?.status || "streaming"

        upsertArtifact({
            id: artifactId,
            type: "slide_deck",
            title: deckTitle,
            content: nextContent,
            version: (existing?.version ?? 0) + 1,
            status,
        })
    }, [stableId, upsertArtifact])

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

            if (data?.type === 'data-title-update' && stableId) {
                const directTitle = typeof (data as any)?.title === 'string' ? (data as any).title : null
                const nestedTitle = typeof (data as any)?.data?.title === 'string' ? (data as any).data.title : null
                const title = directTitle || nestedTitle
                if (title) {
                    updateThreadTitle(stableId, title)
                }
            }

            if (data?.type === 'data-research-start' && data.data) {
                const d = data.data as { task_id: string; perspective: string }
                registerTask(d.task_id, d.perspective)
            }
            if (data?.type === 'data-research-token' && data.data) {
                const d = data.data as { task_id: string; token: string }
                appendContent(d.task_id, d.token)
            }
            if (data?.type === 'data-research-complete' && data.data) {
                const d = data.data as { task_id: string }
                completeTask(d.task_id)
            }
            if (data?.type === 'data-visual-plan') {
                upsertSlideDeck(data.data)
            }
            if (data?.type === 'data-visual-prompt') {
                upsertSlideDeck(data.data)
            }
            if (data?.type === 'data-visual-image') {
                upsertSlideDeck(data.data)
            }
            if (data?.type === 'data-visual-pdf') {
                upsertSlideDeck({ ...(data.data as Record<string, any>), status: 'completed' })
            }
        },
        onError: (error: Error) => {
            console.error("Chat error:", error)
        }
    })

    const { timeline, latestOutline, latestPlan, latestSlideDeck } = useChatTimeline(messages, data, stableId)

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
                        latestSlideDeck={latestSlideDeck}
                        isLoading={isLoading}
                        status={status}
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
