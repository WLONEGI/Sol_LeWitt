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
import { type AspectRatio } from "./aspect-ratio-selector"


import { useChatTimeline } from "../hooks/use-chat-timeline"
import { FixedPlanOverlay } from "./fixed-plan-overlay"
import { useAuth } from "@/providers/auth-provider"
import { AuthRequiredDialog } from "@/features/auth/components/auth-required-dialog"
import type { PlanUpdateData } from "@/features/chat/types/plan"
import { resolveDataEventMessageCount } from "@/features/chat/lib/data-event-order"

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
    product_type?: string
}

interface QueuedInterrupt {
    text: string
    selectedImageInputs: Array<Record<string, any>>
}

interface UploadedAttachment {
    id: string
    filename: string
    mime_type: string
    size_bytes: number
    url: string
    kind: 'image' | 'pptx' | 'pdf' | 'csv' | 'json' | 'text' | 'other'
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
    'data-writer-output',
    'data-image-search-results',
    'data-coordinator-followups',
])

const WRITER_ARTIFACT_TITLES: Record<string, string> = {
    outline: 'Slide Outline',
    writer_story_framework: 'Story Framework',
    writer_character_sheet: 'Character Sheet',
    writer_infographic_spec: 'Infographic Spec',
    writer_document_blueprint: 'Document Blueprint',
    writer_comic_script: 'Comic Script',
}

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

const buildOutlineMarkdown = (slides: any[]): string => {
    if (!Array.isArray(slides) || slides.length === 0) return ''
    const lines: string[] = []
    for (const slide of slides) {
        if (!slide || typeof slide !== 'object') continue
        const slideNo = slide.slide_number ?? '?'
        const title = typeof slide.title === 'string' ? slide.title : ''
        lines.push(`## Slide ${slideNo}: ${title}`)
        const bulletPoints = Array.isArray(slide.bullet_points) ? slide.bullet_points : []
        for (const point of bulletPoints) {
            if (typeof point === 'string' && point.trim()) {
                lines.push(`- ${point}`)
            }
        }
        if (typeof slide.description === 'string' && slide.description.trim()) {
            lines.push(slide.description.trim())
        }
        lines.push('')
    }
    return lines.join('\n').trim()
}

export function ChatInterface({ threadId }: { threadId?: string | null }) {
    const [input, setInput] = useState("")
    const [pendingFiles, setPendingFiles] = useState<File[]>([])
    const [isUploadingAttachments, setIsUploadingAttachments] = useState(false)
    const [attachmentError, setAttachmentError] = useState<string | null>(null)

    const {
        consumePendingAspectRatio,
        consumePendingProductType,
        pendingAspectRatio,
        pendingProductType
    } = useChatStore(
        useShallow((state) => ({
            consumePendingAspectRatio: state.consumePendingAspectRatio,
            consumePendingProductType: state.consumePendingProductType,
            pendingAspectRatio: state.pendingAspectRatio,
            pendingProductType: state.pendingProductType,
        }))
    )

    const [aspectRatio, setAspectRatio] = useState<AspectRatio>(() => {
        // Initialize from store if available (passed from home)
        // Casting mainly because AspectRatio type alias might not exactly match string | undefined | null in store definition
        return (pendingAspectRatio as AspectRatio) || undefined
    })

    // Clear pending aspect ratio after mount if it was used
    useEffect(() => {
        if (pendingAspectRatio) {
            consumePendingAspectRatio()
        }
    }, [pendingAspectRatio, consumePendingAspectRatio])

    const [selectedImageInputs, setSelectedImageInputs] = useState<Array<Record<string, any>>>([])
    const [queuedInterrupt, setQueuedInterrupt] = useState<QueuedInterrupt | null>(null)
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
    const dataSequenceRef = useRef(0)
    const messageCountRef = useRef(0)
    const streamEventMessageCountRef = useRef<number | null>(null)

    const flushData = useCallback(() => {
        dataFlushRef.current = null
        setData([...dataRef.current])
    }, [])

    const stampDataEvent = useCallback((event: CustomDataEvent, messageCountOverride?: number): CustomDataEvent => {
        const seq = dataSequenceRef.current++
        const msgCount = resolveDataEventMessageCount({
            messageCountOverride,
            streamMessageCount: streamEventMessageCountRef.current,
            currentMessageCount: messageCountRef.current,
        })
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

    const upsertWriterArtifact = useCallback((payload: any) => {
        if (!payload) return

        const artifactId = typeof payload.artifact_id === 'string'
            ? payload.artifact_id
            : `writer_${stableId}`
        const artifactType = typeof payload.artifact_type === 'string'
            ? payload.artifact_type
            : 'report'

        const state = useArtifactStore.getState()
        const existing = state.artifacts[artifactId]
        const rawOutput = (payload.output && typeof payload.output === 'object') ? payload.output : {}

        let nextContent: any = rawOutput
        if (artifactType === 'outline') {
            const outlineText = buildOutlineMarkdown(Array.isArray(rawOutput.slides) ? rawOutput.slides : [])
            nextContent = outlineText || JSON.stringify(rawOutput, null, 2)
        }

        upsertArtifact({
            id: artifactId,
            type: artifactType,
            title: payload.title || existing?.title || WRITER_ARTIFACT_TITLES[artifactType] || 'Writer Output',
            content: nextContent,
            version: (existing?.version ?? 0) + 1,
        })
    }, [stableId, upsertArtifact])

    const {
        messages,
        setMessages,
        sendMessage,
        stop,
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
            if (data?.type === 'data-writer-output') {
                upsertWriterArtifact(data.data)
            }
        },
        onError: (error: Error) => {
            console.error("Chat error:", error)
        }
    })

    useEffect(() => {
        messageCountRef.current = messages.length
    }, [messages.length])

    useEffect(() => {
        if (status === 'ready' || status === 'error') {
            streamEventMessageCountRef.current = null
        }
    }, [status])

    const { timeline, latestOutline, latestPlan, latestSlideDeck } = useChatTimeline(messages, data, stableId)

    const selectedAction = QUICK_ACTIONS.find((action) => action.id === selectedActionId) ?? null

    // Initialize product type from pending store (passed from home)
    // We use a ref or state because consume is one-time
    const [initialProductType] = useState<string | undefined | null>(() => {
        return pendingProductType || (messages.length === 0 ? selectedAction?.productType : undefined)
    })

    // Clear pending product type after mount if it was used
    useEffect(() => {
        if (pendingProductType) {
            consumePendingProductType()
        }
    }, [pendingProductType, consumePendingProductType])

    useEffect(() => {
        console.log(`[ChatInterface] selectedActionId: ${selectedActionId}, initialProductType: ${initialProductType}, messages.length: ${messages.length}`);
    }, [selectedActionId, initialProductType, messages.length]);

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
                streamEventMessageCountRef.current = null
                setData([])
                setSelectedImageInputs([])
                setPendingFiles([])
                setAttachmentError(null)
                setQueuedInterrupt(null)
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
            streamEventMessageCountRef.current = null
            setData([])
            setSelectedImageInputs([])
            setPendingFiles([])
            setAttachmentError(null)
            setQueuedInterrupt(null)
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

                    // Set background gradient based on product type
                    if (snapshot.product_type) {
                        const action = QUICK_ACTIONS.find(a => a.productType === snapshot.product_type)
                        if (action) {
                            setSelectedActionId(action.id)
                        } else {
                            setSelectedActionId(null)
                        }
                    } else if (Array.isArray(snapshot.messages) && snapshot.messages.length > 0) {
                        // Existing chat with content but no type -> Generic default
                        setSelectedActionId(null)
                    } else if (!initialProductType && (!snapshot.messages || snapshot.messages.length === 0)) {
                        // Empty chat, no pending product type -> Ensure generic
                        setSelectedActionId(null)
                    }

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
    }, [stableId, setMessages, authLoading, token, setData, stampDataEvent, initialProductType])

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
                    selected_image_inputs: [],
                    ...(initialProductType ? { product_type: initialProductType } : {}),
                },
            }
        )
    }, [stableId, historyReady, authLoading, token, consumePendingMessage, sendMessage, initialProductType])

    useEffect(() => {
        return () => {
            if (dataFlushRef.current != null) {
                window.cancelAnimationFrame(dataFlushRef.current)
            }
        }
    }, [])

    const isLoading = status === 'streaming' || status === 'submitted'
    const isBusy = isLoading || isUploadingAttachments

    const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
        setInput(e.target.value)
    }, [])

    const handleFilesSelect = useCallback((files: File[]) => {
        setAttachmentError(null)
        setPendingFiles((prev) => {
            const merged = [...prev]
            for (const file of files) {
                const exists = merged.some((item) =>
                    item.name === file.name &&
                    item.size === file.size &&
                    item.lastModified === file.lastModified
                )
                if (!exists) merged.push(file)
            }
            return merged
        })
    }, [])

    const handleRemovePendingFile = useCallback((index: number) => {
        setPendingFiles((prev) => prev.filter((_, i) => i !== index))
    }, [])

    const uploadPendingFiles = useCallback(async (): Promise<UploadedAttachment[]> => {
        if (pendingFiles.length === 0) return []
        if (!token) throw new Error("認証情報がありません。再ログインしてください。")

        const formData = new FormData()
        for (const file of pendingFiles) {
            formData.append('files', file)
        }
        formData.append('thread_id', stableId)

        const response = await fetch('/api/uploads', {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${token}`,
            },
            body: formData,
        })

        const payload = await response.json().catch(() => ({}))
        if (!response.ok) {
            const detail = typeof payload?.detail === 'string'
                ? payload.detail
                : (typeof payload?.error === 'string' ? payload.error : `添付アップロードに失敗しました (${response.status})`)
            throw new Error(detail)
        }

        return Array.isArray(payload?.attachments) ? payload.attachments as UploadedAttachment[] : []
    }, [pendingFiles, stableId, token])

    const mapAttachmentToSelectedInput = useCallback((item: UploadedAttachment): Record<string, any> => {
        return {
            image_url: item.url,
            source_url: item.url,
            license_note: 'User uploaded',
            provider: 'user_upload',
            caption: item.filename,
        }
    }, [])

    const submitMessage = useCallback(async (
        value: string,
        options?: {
            interruptIntent?: boolean
            selectedImageInputsOverride?: Array<Record<string, any>>
        }
    ): Promise<boolean> => {
        if (!value.trim()) return false
        if (!threadId && stableId !== currentThreadId) {
            setCurrentThreadId(stableId)
            window.history.replaceState(null, '', `/chat/${stableId}`)
        }

        const payloadSelectedImageInputs = options?.selectedImageInputsOverride ?? selectedImageInputs
        setAttachmentError(null)

        let uploadedAttachments: UploadedAttachment[] = []
        if (pendingFiles.length > 0) {
            setIsUploadingAttachments(true)
            try {
                uploadedAttachments = await uploadPendingFiles()
            } catch (error) {
                console.error("Attachment upload failed:", error)
                setAttachmentError(error instanceof Error ? error.message : "添付アップロードに失敗しました。")
                return false
            } finally {
                setIsUploadingAttachments(false)
            }
        }

        const mergedSelectedImageInputs: Array<Record<string, any>> = [
            ...payloadSelectedImageInputs,
            ...uploadedAttachments
                .filter((item) => item.kind === 'image')
                .map((item) => mapAttachmentToSelectedInput(item)),
        ]

        const dedupedImageInputs = Array.from(
            new Map(
                mergedSelectedImageInputs
                    .filter((item) => typeof item?.image_url === 'string' && item.image_url.length > 0)
                    .map((item) => [String(item.image_url), item])
            ).values()
        )

        // Optimistically update message count to current + 1 (user message)
        // This ensures early data events (like plan start) are stamped with the correct
        // message index (i.e., associated with the upcoming assistant response).
        const streamAnchorMessageCount = messages.length + 1
        messageCountRef.current = streamAnchorMessageCount
        streamEventMessageCountRef.current = streamAnchorMessageCount

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
                    attachments: uploadedAttachments,
                    selected_image_inputs: dedupedImageInputs,
                    interrupt_intent: Boolean(options?.interruptIntent),
                    aspect_ratio: aspectRatio,
                    ...(initialProductType ? { product_type: initialProductType } : {}),
                }
            }
        )
        setSelectedImageInputs([])
        setPendingFiles([])
        setInput("")
        return true
    }, [
        sendMessage,
        threadId,
        stableId,
        currentThreadId,
        setCurrentThreadId,
        token,
        selectedImageInputs,
        initialProductType,
        messages.length,
        pendingFiles,
        uploadPendingFiles,
        mapAttachmentToSelectedInput,
        aspectRatio,
    ])

    const handleToggleImageCandidate = useCallback((candidate: Record<string, any>) => {
        const imageUrl = typeof candidate?.image_url === 'string' ? candidate.image_url : ''
        if (!imageUrl) return
        setSelectedImageInputs((prev) => {
            const exists = prev.some((item) => item?.image_url === imageUrl)
            if (exists) return prev.filter((item) => item?.image_url !== imageUrl)
            return [...prev, candidate]
        })
    }, [])

    const selectedImageUrls = selectedImageInputs
        .map((item) => (typeof item?.image_url === 'string' ? item.image_url : ''))
        .filter((url) => url.length > 0)

    const handleSend = useCallback((value: string) => {
        if (!value.trim()) return
        if (authLoading || !historyReady) return
        if (!user || !token) {
            setPendingAuthMessage(value)
            setShowAuthDialog(true)
            return
        }
        if (isBusy) {
            setQueuedInterrupt({
                text: value,
                selectedImageInputs: [...selectedImageInputs],
            })
            setSelectedImageInputs([])
            setInput("")
            return
        }
        void submitMessage(value)
    }, [authLoading, historyReady, isBusy, user, token, submitMessage, selectedImageInputs])

    const handleSendFollowup = useCallback((prompt: string) => {
        if (!prompt.trim()) return
        handleSend(prompt)
    }, [handleSend])

    const handleStop = useCallback(() => {
        if (!isBusy) return
        stop()
    }, [isBusy, stop])

    useEffect(() => {
        if (!showAuthDialog || !pendingAuthMessage) return
        if (authLoading || !user || !token || !historyReady || isBusy) return
        void (async () => {
            const sent = await submitMessage(pendingAuthMessage)
            if (!sent) return
            setPendingAuthMessage(null)
            setShowAuthDialog(false)
        })()
    }, [authLoading, historyReady, isBusy, pendingAuthMessage, showAuthDialog, submitMessage, token, user])

    useEffect(() => {
        if (!showAuthDialog) {
            setPendingAuthMessage(null)
        }
    }, [showAuthDialog])

    useEffect(() => {
        if (!queuedInterrupt) return
        if (authLoading || !historyReady || isBusy) return
        if (!user || !token) return

        void (async () => {
            const sent = await submitMessage(queuedInterrupt.text, {
                interruptIntent: true,
                selectedImageInputsOverride: queuedInterrupt.selectedImageInputs,
            })
            if (!sent) return
            setQueuedInterrupt(null)
        })()
    }, [queuedInterrupt, authLoading, historyReady, isBusy, user, token, submitMessage])

    return (
        <div className="flex w-full h-full relative">
            <div className="flex flex-col flex-1 h-full w-full min-w-0 relative">
                <div className="flex-1 overflow-hidden relative z-10">
                    <ChatList
                        timeline={timeline}
                        latestPlan={latestPlan}
                        latestOutline={latestOutline}
                        latestSlideDeck={latestSlideDeck}
                        selectedImageUrls={selectedImageUrls}
                        onToggleImageCandidate={handleToggleImageCandidate}
                        queuedUserMessage={queuedInterrupt?.text || null}
                        isLoading={isLoading}
                        status={status}
                        onSendFollowup={handleSendFollowup}
                        className="h-full"
                    />
                </div>

                <div className="p-4 pt-0 relative z-30 pointer-events-none flex flex-col items-center gap-1">
                    {/* Active Researcher Status */}

                    {/* Agent Status Indicator - Removed legacy ui_step_update support */}

                    {(error || attachmentError) && (
                        <div className="w-full max-w-5xl pointer-events-auto mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">
                            {attachmentError || error?.message || "An error occurred during the chat session."}
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
                            onStop={handleStop}
                            isLoading={authLoading || !historyReady || isUploadingAttachments}
                            isProcessing={isLoading}
                            allowSendWhileLoading={!isUploadingAttachments}
                            onFilesSelect={handleFilesSelect}
                            selectedFiles={pendingFiles}
                            onRemoveFile={handleRemovePendingFile}
                            actionPill={
                                selectedAction
                                    ? { label: selectedAction.pillLabel, icon: selectedAction.icon, className: selectedAction.pillClassName }
                                    : undefined
                            }
                            onClearAction={() => setSelectedActionId(null)}
                            aspectRatio={aspectRatio}
                            onAspectRatioChange={setAspectRatio}
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
