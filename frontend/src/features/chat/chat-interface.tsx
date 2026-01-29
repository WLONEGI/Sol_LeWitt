"use client"

import { useChat } from '@ai-sdk/react'
import { DefaultChatTransport } from 'ai'
import { ChatList } from "./components/chat-list"
import { ChatInput } from "./components/chat-input"
import { useChatStore } from "./store/chat"
import { useArtifactStore } from "../preview/store/artifact"
import { useEffect, useState, useCallback } from 'react'
import { v4 as uuidv4 } from 'uuid';

import { ChatSidebar } from "./components/chat-sidebar";
import { useChatTimeline } from "./hooks/use-chat-timeline"
import { PanelLeftOpen } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ChatInterface() {
    const [input, setInput] = useState("");
    const [pendingFile, setPendingFile] = useState<File | null>(null);
    const [pendingFileBase64, setPendingFileBase64] = useState<string | null>(null);
    const { setArtifact } = useArtifactStore();
    const { currentThreadId, isSidebarOpen, setSidebarOpen } = useChatStore();


    // Use custom hook for timeline management
    const {
        timeline,
        setTimeline,
        currentStepIdRef,
        handleProcessEventToTimeline,
        syncMessagesToTimeline,
        completeRunningSteps
    } = useChatTimeline();

    const chatHelpers = useChat({
        // AI SDK v6: DefaultChatTransportでAPIエンドポイントを指定
        transport: new DefaultChatTransport({
            api: '/api/chat/stream', // Next.js Route Handler (Proxy Pattern)
            body: {
                thread_id: currentThreadId
            },
        }),
        onError: (error) => {
            console.error("Chat error:", error);
        },
        // Data Stream Protocol のカスタムデータハンドリング
        // d: prefix でパースされたデータは type フィールドを直接持つ
        onData: (dataPart: any) => {
            console.log("Received data part:", dataPart.type, dataPart);
            // Data Stream Protocol: type is now direct (e.g., "agent", "progress", "artifact")
            // No need to strip "data-" prefix anymore
            if (dataPart.type) {
                handleProcessEventToTimeline(
                    dataPart,
                    setArtifact
                );
            }
        },
        onFinish: (message) => {
            console.log("Chat finished:", message);
            // Ensure any running steps are marked completed on finish
            completeRunningSteps();
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
    }, [currentThreadId, setMessages, setTimeline]);


    useEffect(() => {
        console.log("ChatHelpers Keys:", Object.keys(chatHelpers));
        console.log("ChatHelpers available:", { status, messagesCount: messages.length, hasAppend: !!append });
    }, [status, messages.length, append, chatHelpers]);

    const isLoading = status === 'streaming' || status === 'submitted';

    // -- Timeline Construction Logic --

    // 1. Sync User Messages & History from SDK to Timeline
    useEffect(() => {
        syncMessagesToTimeline(messages);
    }, [messages, syncMessagesToTimeline]);

    // 2. Handle Data Stream Events (Logs, Artifacts, etc.)
    useEffect(() => {
        if (!data) return;

        data.forEach((item: any) => {
            if (!item) return;

            // Process Logic Adaptation for Timeline
            if ([
                'agent_start',
                'tool_call',
                'tool_result',
                'progress',
                'artifact',
                'reasoning-delta'
            ].includes(item.type)) {
                handleProcessEventToTimeline(item, setArtifact);
            }

            // Sources (handled in message usually, but if independent event...)
            // Legacy logic handled sources separately. Here we rely on message attachment if possible, 
            // or we could add a "Sources" timeline item if needed. For now sticking to message attachment logic in ChatList.
        });
    }, [data, setArtifact, handleProcessEventToTimeline]);


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
        setInput("");
    }, [pendingFileBase64, append, currentStepIdRef, chatHelpers]);

    return (
        <div className="flex w-full h-full relative">
            <ChatSidebar />

            <div className="flex flex-col flex-1 h-full w-full min-w-0 relative">
                {/* Header / Sidebar Toggle Area (Absolute or top bar) */}
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
