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
import { QUICK_ACTIONS } from "@/features/chat/constants/quick-actions"


import { useChatTimeline } from "../hooks/use-chat-timeline"
import { FixedPlanOverlay } from "./fixed-plan-overlay"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/providers/auth-provider"
import { AuthRequiredDialog } from "@/features/auth/components/auth-required-dialog"

// Custom data events from backend
interface CustomDataEvent {
    type: string
    data?: any
    __seq?: number
    __msgCount?: number
    [key: string]: unknown
}

interface ChatSnapshot {
    messages?: any[]
    artifacts?: Record<string, any>
    ui_events?: CustomDataEvent[]
}

const MAX_DATA_EVENTS = 200
const DATA_EVENTS_TO_STORE = new Set([
    'data-plan_update',
    'data-plan_step_started',
    'data-plan_step_ended',
    'data-outline',
    'data-visual-plan',
    'data-visual-prompt',
    'data-visual-image',
    'data-visual-pdf',
    'data-analyst-start',
    'data-analyst-code-delta',
    'data-analyst-log-delta',
    'data-analyst-output',
    'data-analyst-complete',
])

const normalizeMessageParts = (msg: any): any[] => {
    const parts: any[] = []
    if (Array.isArray(msg?.parts)) {
        for (const part of msg.parts) {
            if (!part || typeof part !== 'object') continue
            const type = typeof (part as any).type === 'string' ? (part as any).type : null
            if (!type) continue
            if (type === 'text' && typeof (part as any).text === 'string') {
                parts.push({ type: 'text', text: (part as any).text })
                continue
            }
            if (type === 'reasoning') {
                const text =
                    typeof (part as any).text === 'string'
                        ? (part as any).text
                        : (typeof (part as any).reasoning === 'string' ? (part as any).reasoning : '')
                if (text) {
                    parts.push({ type: 'reasoning', text })
                }
                continue
            }
            if (type.startsWith('data-')) {
                parts.push({ type, data: (part as any).data })
            }
        }
    }

    if (parts.length === 0) {
        if (typeof msg?.reasoning === 'string' && msg.reasoning.trim().length > 0) {
            parts.push({ type: 'reasoning', text: msg.reasoning })
        }
        if (typeof msg?.content === 'string') {
            parts.push({ type: 'text', text: msg.content })
        }
    }

    return parts
}

const mapHistoryMessageToUIMessage = (msg: any): UIMessage => {
    const parts = normalizeMessageParts(msg)
    let toolInvocations: any[] | undefined

    if (Array.isArray(msg?.tool_calls)) {
        toolInvocations = msg.tool_calls.map((tc: any) => {
            let args = {}
            try {
                args = JSON.parse(tc?.function?.arguments || '{}')
            } catch {
                args = {}
            }
            return {
                toolCallId: tc?.id,
                toolName: tc?.function?.name,
                args,
                state: 'call'
            }
        })
    }

    return {
        id: msg?.id || uuidv4(),
        role: msg?.role || 'assistant',
        parts,
        metadata: msg?.metadata,
        toolInvocations,
    } as UIMessage
}

export function ChatInterface({ threadId }: { threadId?: string | null }) {
    const [input, setInput] = useState("")
    const [pendingFile, setPendingFile] = useState<File | null>(null)
    const [pendingFileBase64, setPendingFileBase64] = useState<string | null>(null)
    const [historyReady, setHistoryReady] = useState(false)

    const { registerTask, appendContent, completeTask } = useResearchStore(
        useShallow((state) => ({
            registerTask: state.registerTask,
            appendContent: state.appendContent,
            completeTask: state.completeTask,
        }))
    )
    const { currentThreadId, setCurrentThreadId, updateThreadTitle, consumePendingMessage, selectedActionId, setSelectedActionId } = useChatStore(
        useShallow((state) => ({
            currentThreadId: state.currentThreadId,
            setCurrentThreadId: state.setCurrentThreadId,
            updateThreadTitle: state.updateThreadTitle,
            consumePendingMessage: state.consumePendingMessage,
            selectedActionId: state.selectedActionId,
            setSelectedActionId: state.setSelectedActionId,
        }))
    )
    const { upsertArtifact } = useArtifactStore(
        useShallow((state) => ({
            upsertArtifact: state.upsertArtifact,
        }))
    )
    const { user, token, loading: authLoading, error: authError, signInWithGoogle } = useAuth()
    const [showAuthDialog, setShowAuthDialog] = useState(false)
    const [pendingAuthMessage, setPendingAuthMessage] = useState<string | null>(null)

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
    const activePlanStepRef = useRef<{ stepId: string | number; title: string; key: string } | null>(null)
    const dataSequenceRef = useRef(0)
    const messageCountRef = useRef(0)

    const flushData = useCallback(() => {
        dataFlushRef.current = null
        setData([...dataRef.current])
    }, [])

    const stampDataEvent = useCallback((event: CustomDataEvent, messageCountOverride?: number): CustomDataEvent => {
        const seq = dataSequenceRef.current++
        const msgCount = (typeof messageCountOverride === 'number' && Number.isFinite(messageCountOverride))
            ? messageCountOverride
            : messageCountRef.current
        return {
            ...event,
            __seq: seq,
            __msgCount: msgCount,
        }
    }, [])

    const enqueueData = useCallback((event: CustomDataEvent) => {
        if (!DATA_EVENTS_TO_STORE.has(event.type)) return
        const stamped = stampDataEvent(event)
        const next = [...dataRef.current, stamped]
        dataRef.current = next.length > MAX_DATA_EVENTS ? next.slice(-MAX_DATA_EVENTS) : next
        if (dataFlushRef.current == null) {
            dataFlushRef.current = window.requestAnimationFrame(flushData)
        }
    }, [flushData, stampDataEvent])

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

    const upsertDataAnalystArtifact = useCallback((
        payload: any,
        eventType: 'start' | 'code' | 'log' | 'output' | 'complete'
    ) => {
        if (!payload) return
        const artifactId = typeof payload.artifact_id === 'string'
            ? payload.artifact_id
            : `data_analyst_${stableId}`

        const state = useArtifactStore.getState()
        const existing = state.artifacts[artifactId]
        const existingContent = (existing?.content && typeof existing.content === 'object') ? existing.content : {}

        const nextContent: Record<string, any> = { ...existingContent }
        if (eventType === 'start' && payload.input) {
            nextContent.input = payload.input
        }
        if (eventType === 'code' && typeof payload.delta === 'string') {
            nextContent.code = `${existingContent.code || ''}${payload.delta}`
        }
        if (eventType === 'log' && typeof payload.delta === 'string') {
            nextContent.log = `${existingContent.log || ''}${payload.delta}`
        }
        if (eventType === 'output' && payload.output) {
            nextContent.output = payload.output
        }

        const nextStatus =
            payload.status ||
            (eventType === 'complete' ? 'completed' : (existing?.status || 'streaming'))

        upsertArtifact({
            id: artifactId,
            type: "data_analyst",
            title: payload.title || existing?.title || "Data Analyst",
            content: nextContent,
            version: (existing?.version ?? 0) + 1,
            status: nextStatus,
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

            if (data?.type === 'data-plan_update') {
                const payload = data.data as { plan?: Array<{ id?: string | number; title?: string; status?: string }> } | undefined
                const steps = Array.isArray(payload?.plan) ? payload.plan : []
                const inProgressIndex = steps.findIndex((step) => step?.status === 'in_progress')

                if (inProgressIndex >= 0) {
                    const step = steps[inProgressIndex]
                    const stepTitle = typeof step?.title === 'string' && step.title.trim().length > 0
                        ? step.title.trim()
                        : `Step ${inProgressIndex + 1}`
                    const stepId = step?.id ?? inProgressIndex
                    const nextStepKey = `${String(stepId)}:${stepTitle}`
                    const currentStep = activePlanStepRef.current

                    if (nextStepKey !== currentStep?.key) {
                        if (currentStep) {
                            enqueueData({
                                type: 'data-plan_step_ended',
                                data: { step_id: currentStep.stepId },
                            })
                        }
                        activePlanStepRef.current = { stepId, title: stepTitle, key: nextStepKey }
                        enqueueData({
                            type: 'data-plan_step_started',
                            data: { step_id: stepId, title: stepTitle },
                        })
                    }
                } else {
                    const currentStep = activePlanStepRef.current
                    if (currentStep) {
                        enqueueData({
                            type: 'data-plan_step_ended',
                            data: { step_id: currentStep.stepId },
                        })
                    }
                    activePlanStepRef.current = null
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
            if (data?.type === 'data-analyst-start') {
                upsertDataAnalystArtifact(data.data, 'start')
            }
            if (data?.type === 'data-analyst-code-delta') {
                upsertDataAnalystArtifact(data.data, 'code')
            }
            if (data?.type === 'data-analyst-log-delta') {
                upsertDataAnalystArtifact(data.data, 'log')
            }
            if (data?.type === 'data-analyst-output') {
                upsertDataAnalystArtifact(data.data, 'output')
            }
            if (data?.type === 'data-analyst-complete') {
                upsertDataAnalystArtifact(data.data, 'complete')
            }
        },
        onError: (error: Error) => {
            console.error("Chat error:", error)
        }
    })

    useEffect(() => {
        messageCountRef.current = messages.length
    }, [messages.length])

    const { timeline, latestOutline, latestPlan, latestSlideDeck } = useChatTimeline(messages, data, stableId)

    const selectedAction = QUICK_ACTIONS.find((action) => action.id === selectedActionId) ?? null

    useEffect(() => {
        let isCancelled = false
        const loadHistory = async () => {
            if (!stableId) return
            if (authLoading) return

            if (!token) {
                setMessages([])
                dataRef.current = []
                dataSequenceRef.current = 0
                messageCountRef.current = 0
                setData([])
                activePlanStepRef.current = null
                const artifactState = useArtifactStore.getState()
                artifactState.setArtifacts({})
                artifactState.setActiveContextId(null)
                artifactState.setArtifact(null)
                setHistoryReady(true)
                return
            }

            setHistoryReady(false)
            setMessages([])
            dataRef.current = []
            dataSequenceRef.current = 0
            messageCountRef.current = 0
            setData([])
            activePlanStepRef.current = null
            const artifactState = useArtifactStore.getState()
            artifactState.setArtifacts({})
            artifactState.setActiveContextId(null)
            artifactState.setArtifact(null)

            try {
                const res = await fetch(`/api/threads/${stableId}/snapshot`, {
                    headers: {
                        Authorization: `Bearer ${token}`,
                    },
                    cache: 'no-store',
                })
                if (isCancelled) return
                if (res.ok) {
                    const snapshot = await res.json() as ChatSnapshot
                    if (isCancelled) return
                    const historyMessages = Array.isArray(snapshot?.messages) ? snapshot.messages : []
                    const mappedMessages: UIMessage[] = historyMessages.map(mapHistoryMessageToUIMessage)
                    setMessages(mappedMessages)
                    if (snapshot?.artifacts && typeof snapshot.artifacts === 'object') {
                        artifactState.setArtifacts(snapshot.artifacts)
                    }

                    const snapshotEvents = Array.isArray(snapshot?.ui_events) ? snapshot.ui_events : []
                    const stampedSnapshotEvents = snapshotEvents.map((event) => {
                        const existingMsgCount = typeof event?.__msgCount === 'number' && Number.isFinite(event.__msgCount)
                            ? event.__msgCount
                            : mappedMessages.length
                        return stampDataEvent(event, existingMsgCount)
                    })
                    dataRef.current = stampedSnapshotEvents.length > MAX_DATA_EVENTS
                        ? stampedSnapshotEvents.slice(-MAX_DATA_EVENTS)
                        : stampedSnapshotEvents
                    setData([...dataRef.current])
                    return
                }

                const fallbackRes = await fetch(`/api/threads/${stableId}/messages`, {
                    headers: {
                        Authorization: `Bearer ${token}`,
                    },
                    cache: 'no-store',
                })
                if (isCancelled) return
                if (fallbackRes.ok) {
                    const history = await fallbackRes.json()
                    if (isCancelled) return
                    const mappedMessages: UIMessage[] = Array.isArray(history)
                        ? history.map(mapHistoryMessageToUIMessage)
                        : []
                    setMessages(mappedMessages)
                    return
                }
            } catch (err) {
                if (!isCancelled) {
                    console.error("Failed to load history:", err)
                }
            } finally {
                if (!isCancelled) {
                    setHistoryReady(true)
                }
            }
        }
        loadHistory()
        return () => { isCancelled = true }
    }, [stableId, setMessages, authLoading, token, setData, stampDataEvent])

    useEffect(() => {
        if (!stableId || !historyReady) return
        if (authLoading || !token) return
        const pendingText = consumePendingMessage(stableId)
        if (!pendingText) return
        sendMessage(
            { text: pendingText },
            {
                headers: {
                    Authorization: `Bearer ${token}`,
                },
                body: {
                    thread_id: stableId,
                },
            }
        )
    }, [stableId, historyReady, authLoading, token, consumePendingMessage, sendMessage])

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


    const submitMessage = useCallback((value: string) => {
        if (!value.trim()) return
        if (!threadId && stableId !== currentThreadId) {
            setCurrentThreadId(stableId)
            window.history.replaceState(null, '', `/chat/${stableId}`)
        }
        sendMessage(
            { text: value },
            {
                headers: token
                    ? {
                        Authorization: `Bearer ${token}`,
                    }
                    : undefined,
                body: {
                    thread_id: stableId,
                    ...(pendingFileBase64 && { pptx_template_base64: pendingFileBase64 }),
                }
            }
        )
        setPendingFile(null)
        setPendingFileBase64(null)
        setInput("")
    }, [sendMessage, threadId, stableId, currentThreadId, setCurrentThreadId, pendingFileBase64, token])

    const handleSend = useCallback((value: string) => {
        if (!value.trim()) return
        if (authLoading || !historyReady || isLoading) return
        if (!user || !token) {
            setPendingAuthMessage(value)
            setShowAuthDialog(true)
            return
        }
        submitMessage(value)
    }, [authLoading, historyReady, isLoading, user, token, submitMessage])

    useEffect(() => {
        if (!showAuthDialog || !pendingAuthMessage) return
        if (authLoading || !user || !token || !historyReady || isLoading) return
        submitMessage(pendingAuthMessage)
        setPendingAuthMessage(null)
        setShowAuthDialog(false)
    }, [authLoading, historyReady, isLoading, pendingAuthMessage, showAuthDialog, submitMessage, token, user])

    useEffect(() => {
        if (!showAuthDialog) {
            setPendingAuthMessage(null)
        }
    }, [showAuthDialog])

    const inputDisabledReason = authLoading
        ? "Checking authentication..."
        : !historyReady
            ? null
            : isLoading
                ? "Generating response..."
                : null

    return (
        <div className="flex w-full h-full relative">
            <div className="flex flex-col flex-1 h-full w-full min-w-0 relative">
                <div className="flex-1 overflow-hidden relative z-10">
                    <ChatList
                        timeline={timeline}
                        latestPlan={latestPlan}
                        latestOutline={latestOutline}
                        latestSlideDeck={latestSlideDeck}
                        isLoading={isLoading}
                        status={status}
                        className="h-full"
                    />
                </div>

                <div className="p-4 pt-0 relative z-30 pointer-events-none flex flex-col items-center gap-1">
                    {/* Active Researcher Status */}

                    {/* Agent Status Indicator - Removed legacy ui_step_update support */}

                    {error && (
                        <div className="w-full max-w-5xl pointer-events-auto mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">
                            {error.message || "An error occurred during the chat session."}
                        </div>
                    )}

                    {/* Fixed Execution Plan Overlay */}
                    {latestPlan && (
                        <FixedPlanOverlay
                            data={latestPlan}
                            className="pointer-events-auto"
                        />
                    )}

                    <div className="w-full max-w-5xl pointer-events-auto">
                        <ChatInput
                            value={input}
                            onChange={handleInputChange}
                            onSend={handleSend}
                            isLoading={isLoading || authLoading || !historyReady}
                            disabledReason={inputDisabledReason}
                            onFileSelect={handleFileSelect}
                            selectedFile={pendingFile}
                            onClearFile={() => { setPendingFile(null); setPendingFileBase64(null) }}
                            actionPill={
                                selectedAction
                                    ? { label: selectedAction.pillLabel, icon: selectedAction.icon }
                                    : undefined
                            }
                            onClearAction={() => setSelectedActionId(null)}
                        />
                    </div>

                </div>
            </div>
            <AuthRequiredDialog
                open={showAuthDialog}
                onOpenChange={setShowAuthDialog}
                onLogin={signInWithGoogle}
                isLoading={authLoading}
                error={authError}
            />
        </div>
    )
}
