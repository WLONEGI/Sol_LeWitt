"use client"

import { useChat } from '@ai-sdk/react'
import { DefaultChatTransport } from 'ai'
import { ChatList } from "@/components/chat/chat-list"
import { ChatInput } from "@/components/chat/chat-input"
import { useChatStore } from "@/store/chat"
import { useArtifactStore } from "@/store/artifact"
import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { v4 as uuidv4 } from 'uuid';

import { ChatSidebar } from "@/components/chat/chat-sidebar";
import { TimelineEvent, MessageTimelineItem, ProcessTimelineItem } from "@/types/timeline";
import { ProcessStep, ProcessLog } from "@/types/process";

export function ChatInterface() {
    const [input, setInput] = useState("");
    const [pendingFile, setPendingFile] = useState<File | null>(null);
    const [pendingFileBase64, setPendingFileBase64] = useState<string | null>(null);
    const { setArtifact } = useArtifactStore();

    // Timeline State
    const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
    const currentStepIdRef = useRef<string | null>(null);

    const { currentThreadId } = useChatStore();

    const chatHelpers = useChat({
        // AI SDK v6: DefaultChatTransportでAPIエンドポイントを指定
        transport: new DefaultChatTransport({
            api: '/api/chat/stream',
            body: {
                thread_id: currentThreadId
            },
        }),
        onError: (error) => {
            console.error("Chat error:", error);
        },
        // UI Message Stream Protocol のカスタムデータハンドリング
        onData: (dataPart: any) => {
            console.log("Received data part:", dataPart.type, dataPart);
            // data-* イベントをタイムラインに変換
            if (dataPart.type && dataPart.type.startsWith('data-')) {
                handleProcessEventToTimeline(
                    { type: dataPart.type.replace('data-', ''), ...dataPart },
                    setTimeline,
                    setArtifact,
                    currentStepIdRef
                );
            }
        },
        onFinish: (message) => {
            console.log("Chat finished:", message);
            // Ensure any running steps are marked completed on finish
            setTimeline(prev => prev.map(item => {
                if (item.type === 'process_step' && item.step.status === 'running') {
                    return { ...item, step: { ...item.step, status: 'completed' } };
                }
                return item;
            }));
        }
    });

    const { messages, setMessages, append, status, data, input: chatInput, handleInputChange } = chatHelpers as any;

    // -- History Loading Logic --
    useEffect(() => {
        const loadHistory = async () => {
            if (!currentThreadId) {
                setMessages([]);
                setTimeline([]);
                return;
            }

            try {
                const res = await fetch(`/api/threads/${currentThreadId}/messages`);
                if (res.ok) {
                    const history = await res.json();
                    // Basic mapping - backend returns compatible array but ensure IDs are strings
                    const mappedMessages = history.map((msg: any) => ({
                        ...msg,
                        id: msg.id || uuidv4(),
                        content: msg.content || ""
                    }));
                    setMessages(mappedMessages);
                    // Timeline will be largely rebuilt by the next effect on 'messages' change
                    // But we might want to clear it first to avoid mixing
                    setTimeline([]);
                }
            } catch (err) {
                console.error("Failed to load history:", err);
            }
        };
        loadHistory();
    }, [currentThreadId, setMessages]);


    useEffect(() => {
        console.log("ChatHelpers Keys:", Object.keys(chatHelpers));
        console.log("ChatHelpers available:", { status, messagesCount: messages.length, hasAppend: !!append });
    }, [status, messages.length, append, chatHelpers]);

    const isLoading = status === 'streaming' || status === 'submitted';

    // -- Timeline Construction Logic --

    // 1. Sync User Messages & History from SDK to Timeline
    useEffect(() => {
        if (messages.length === 0) {
            // Only clear timeline if we are truly empty (new chat)
            // But we handled setTimeline([]) in loadHistory.
            // If messages are empty but timeline has items, likely we should clear?
            // Let's rely on explicit clearing elsewhere or keep history?
            return;
        }

        setTimeline(prev => {
            const newTimeline = [...prev];

            // Map existing timeline message IDs for quick lookup
            const existingMessageIds = new Set(
                newTimeline
                    .filter(item => item.type === 'message')
                    .map(item => (item as MessageTimelineItem).message.id)
            );

            console.log("SDK Messages Update:", messages.length, messages[messages.length - 1]?.content);

            let added = false;
            messages.forEach((msg: any) => {
                if (!existingMessageIds.has(msg.id)) {
                    // Add new message
                    newTimeline.push({
                        id: `msg-${msg.id}`,
                        type: 'message',
                        timestamp: Date.now(), // Approximate for history
                        message: msg
                    });
                    added = true;
                } else {
                    // Update existing message (streaming content updates)
                    const idx = newTimeline.findIndex(item => item.type === 'message' && (item as MessageTimelineItem).message.id === msg.id);
                    if (idx !== -1) {
                        const currentItem = newTimeline[idx] as MessageTimelineItem;
                        if (currentItem.message.content !== msg.content || currentItem.message.toolInvocations !== msg.toolInvocations) {
                            newTimeline[idx] = { ...currentItem, message: msg };
                            added = true; // State changed
                        }
                    }
                }
            });

            return added ? newTimeline : prev;
        });
    }, [messages]);

    // 2. Handle Data Stream Events (Logs, Artifacts, etc.)
    useEffect(() => {
        if (!data) return;

        data.forEach((item: any) => {
            if (!item) return;

            // Process Logic Adaptation for Timeline
            if (['phase_change', 'agent_start', 'tool_call', 'tool_result', 'progress', 'artifact'].includes(item.type)) {
                handleProcessEventToTimeline(item, setTimeline, setArtifact, currentStepIdRef);
            }

            // Sources (handled in message usually, but if independent event...)
            // Legacy logic handled sources separately. Here we rely on message attachment if possible, 
            // or we could add a "Sources" timeline item if needed. For now sticking to message attachment logic in ChatList.
        });
    }, [data, setArtifact]);


    const handleFileSelect = useCallback((file: File) => {
        setPendingFile(file);
        const reader = new FileReader();
        reader.onloadend = () => {
            const base64 = reader.result as string;
            const base64Clean = base64.split(',')[1] || base64;
            setPendingFileBase64(base64Clean);
        };
        reader.readAsDataURL(file);
    }, []);

    const handleSend = useCallback((value: string) => {
        if (!value.trim()) return;

        const extraData: any = {};
        if (pendingFileBase64) {
            extraData.pptx_template_base64 = pendingFileBase64;
        }

        // Reset for new turn? 
        // We generally keep history. But maybe we want to guarantee the user message is added immediately by SDK.

        currentStepIdRef.current = null;

        const sendFunc = append || (chatHelpers as any).sendMessage;

        if (!sendFunc) {
            console.error("ChatHelpers.append AND sendMessage are undefined!", chatHelpers);
            return;
        }

        console.log("Sending message using:", append ? "append" : "sendMessage");
        sendFunc({
            role: 'user',
            content: value,
        }, {
            data: extraData
        });

        setPendingFile(null);
        setPendingFileBase64(null);
    }, [pendingFileBase64, append]);

    return (
        <div className="flex w-full h-full relative">
            <ChatSidebar />

            <div className="flex flex-col flex-1 h-full w-full min-w-0 relative">
                <div className="flex-1 overflow-hidden relative z-10">
                    <ChatList
                        timeline={timeline}
                        isLoading={isLoading}
                        className="h-full"
                    />
                </div>

                <div className="p-4 relative z-30 pointer-events-none flex justify-center">
                    <div className="w-full max-w-3xl pointer-events-auto">
                        <ChatInput
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onSend={handleSend}
                            isLoading={isLoading}
                            onFileSelect={handleFileSelect}
                            selectedFile={pendingFile}
                            onClearFile={() => { setPendingFile(null); setPendingFileBase64(null); }}
                        />
                    </div>
                </div>
            </div>
        </div>
    )
}

// --- Helper: Process Event to Timeline ---

function handleProcessEventToTimeline(
    data: any,
    setTimeline: React.Dispatch<React.SetStateAction<TimelineEvent[]>>,
    setArtifact: any,
    currentStepIdRef: React.MutableRefObject<string | null>
) {
    // 1. Plan Update (Legacy UI Type check, but coming via data stream?)
    // If plan update comes as a specific event type, add it.
    // Assuming 'artifact' event with type 'plan' handles this.

    // 2. Process Steps (Accordion)
    // We update the *last* ProcessStepItem in the timeline if it matches currentStepId,
    // OR we append a new ProcessStepItem.

    if (data.type === 'phase_change' || data.type === 'agent_start' || data.type === 'workflow_start' || (data.type === 'agent' && data.content?.status === 'started')) {
        const payload = data.content || {};
        const stepId = (data.type === 'phase_change' ? payload.id : data.metadata?.id) || `step-${Date.now()}`;
        const title = payload.title || data.metadata?.title || `Phase: ${payload.agent_name || data.metadata?.agent_name}`;
        const description = payload.description || "";
        const agentName = payload.agent_name || data.metadata?.agent_name;

        // Start new step
        const newStep: ProcessStep = {
            id: stepId,
            title: title,
            status: 'running',
            expanded: true,
            logs: [],
            agentName: agentName,
            description: description
        };

        setTimeline(prev => {
            // Close previous running steps?
            // Ideally yes, visualizer starts -> planner ends.
            const closedPrev = prev.map(item => {
                if (item.type === 'process_step' && item.step.status === 'running') {
                    return { ...item, step: { ...item.step, status: 'completed' as const, expanded: false } };
                }
                return item;
            });

            // Avoid duplicates if re-entrant
            if (closedPrev.some(item => item.type === 'process_step' && item.id === stepId)) return closedPrev;

            return [...closedPrev, {
                id: stepId,
                type: 'process_step',
                timestamp: Date.now(),
                step: newStep
            }];
        });
        currentStepIdRef.current = stepId;
    }
    else if (data.type === 'tool_call') {
        const stepId = currentStepIdRef.current;
        if (!stepId) return; // Should connect to active step

        const runId = data.metadata?.run_id;
        const logId = runId || `tool-${Date.now()}-${Math.random()}`;
        const toolName = data.content?.tool_name || "Tool";
        const inputSnippet = JSON.stringify(data.content?.input || {}).slice(0, 50);

        const newLog: ProcessLog = {
            id: logId, runId: runId, type: 'tool', title: `${toolName}: ${inputSnippet}...`,
            status: 'running', content: data.content, metadata: data.metadata
        };

        setTimeline(prev => prev.map(item => {
            if (item.type === 'process_step' && item.step.id === stepId) {
                // Avoid dupe logs
                if (item.step.logs.some(l => l.id === logId)) return item;
                return {
                    ...item,
                    step: { ...item.step, logs: [...item.step.logs, newLog] }
                };
            }
            return item;
        }));
    }
    else if (data.type === 'tool_result') {
        const stepId = currentStepIdRef.current;
        if (!stepId) return;
        const runId = data.metadata?.run_id;

        setTimeline(prev => prev.map(item => {
            if (item.type === 'process_step' && item.step.id === stepId) {
                const updatedLogs = item.step.logs.map(log => {
                    if (log.runId === runId && log.status === 'running') {
                        return { ...log, status: 'completed' as const };
                    }
                    return log;
                });
                return { ...item, step: { ...item.step, logs: updatedLogs } };
            }
            return item;
        }));
    }
    else if (data.type === 'agent_end' || (data.type === 'agent' && data.content?.status === 'completed')) {
        const stepId = currentStepIdRef.current;
        if (stepId) {
            setTimeline(prev => prev.map(item => {
                if (item.type === 'process_step' && item.step.id === stepId) {
                    return { ...item, step: { ...item.step, status: 'completed' as const } };
                }
                return item;
            }));
            // Optional: reset currentStepIdRef if you want to ensure no logs attach after completion
            // currentStepIdRef.current = null; 
        }
    }
    else if (data.type === 'progress') {
        const stepId = currentStepIdRef.current;
        if (!stepId) return;
        const runId = data.metadata?.run_id;

        setTimeline(prev => prev.map(item => {
            if (item.type === 'process_step' && item.step.id === stepId) {
                const updatedLogs = item.step.logs.map(log => {
                    if (log.runId === runId && log.status === 'running') {
                        return { ...log, progress: { message: data.content?.message || data.content?.status } };
                    }
                    return log;
                });
                return { ...item, step: { ...item.step, logs: updatedLogs } };
            }
            return item;
        }));
    }
    else if (data.type === 'artifact') {
        const art = data.content;
        setArtifact({
            id: art.id, type: art.type, title: art.title,
            content: art.content, status: 'streaming'
        });

        // Add artifact to the current step log AND potentially as a standalone timeline item?
        // Current design puts distinct UI artifacts (WorkerResult, Buttons) as separate items.

        // 1. Add Log to Accordion
        const stepId = currentStepIdRef.current;
        if (stepId) {
            setTimeline(prev => prev.map(item => {
                if (item.type === 'process_step' && item.step.id === stepId) {
                    if (item.step.logs.some(l => l.id === `art-${art.id}`)) return item;
                    return {
                        ...item,
                        step: {
                            ...item.step,
                            logs: [...item.step.logs, { id: `art-${art.id}`, type: 'artifact', title: `Artifact: ${art.title}`, status: 'completed', metadata: { id: art.id } }]
                        }
                    };
                }
                return item;
            }));
        }

        // 2. Add Standalone Timeline Item for specific visualizations
        // e.g. "Visualizer generated..." (WorkerResult) or Images
        // If it's a plan, we can add a 'plan_update' item.
        if (art.type === 'plan') {
            setTimeline(prev => {
                if (prev.some(item => item.id === `plan-${art.id}`)) return prev;
                return [...prev, {
                    id: `plan-${art.id}`,
                    type: 'plan_update',
                    timestamp: Date.now(),
                    plan: art.content,
                    title: art.title
                } as any];
            });
        }
        else if (art.type === 'image') {
            // Add artifact view item
            setTimeline(prev => {
                if (prev.some(item => item.id === `art-view-${art.id}`)) return prev;
                return [...prev, {
                    id: `art-view-${art.id}`,
                    type: 'artifact',
                    timestamp: Date.now(),
                    artifactId: art.id,
                    title: "Generated Images",
                    icon: "Image",
                    previewUrls: art.content?.image_url ? [art.content.image_url] : []
                } as any];
            })
        }
    }
}
