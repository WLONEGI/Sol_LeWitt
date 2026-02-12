import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import type { QuickActionId } from "@/features/chat/constants/quick-actions";

interface ChatState {
    currentThreadId: string | null;
    threads: Array<{ id: string; title: string; updatedAt: string; product_type?: string }>;
    historyLoading: boolean;
    historyError: string | null;
    isSidebarOpen: boolean;
    pendingMessage: { threadId: string; text: string } | null;
    pendingThreadFiles: Record<string, File[]>;
    pendingHomeInput: string | null;
    pendingAspectRatio: string | undefined | null;
    pendingProductType: string | undefined | null;
    selectedActionId: QuickActionId | null;

    setCurrentThreadId: (id: string | null) => void;
    setSidebarOpen: (isOpen: boolean) => void;
    setThreads: (threads: Array<{ id: string; title: string; updatedAt: string; product_type?: string }>) => void;
    fetchHistory: (token: string | null) => Promise<void>;
    createSession: () => void;
    updateThreadTitle: (id: string, title: string) => void;
    setPendingMessage: (threadId: string, text: string) => void;
    consumePendingMessage: (threadId: string) => string | null;
    setPendingThreadFiles: (threadId: string, files: File[]) => void;
    consumePendingThreadFiles: (threadId: string) => File[];
    setPendingHomeInput: (text: string | null) => void;
    consumePendingHomeInput: () => string | null;
    setPendingAspectRatio: (ratio: string | undefined | null) => void;
    consumePendingAspectRatio: () => string | undefined | null;
    setPendingProductType: (type: string | undefined | null) => void;
    consumePendingProductType: () => string | undefined | null;
    setSelectedActionId: (id: QuickActionId | null) => void;
    resetForAuthBoundary: () => void;
}

export const useChatStore = create<ChatState>()(
    devtools(
        persist(
            (set, get) => ({
                currentThreadId: null,
                threads: [],
                historyLoading: false,
                historyError: null,
                isSidebarOpen: true,
                pendingMessage: null,
                pendingThreadFiles: {},
                pendingHomeInput: null,
                pendingAspectRatio: null,
                pendingProductType: null,
                selectedActionId: null,

                setCurrentThreadId: (id) => set({ currentThreadId: id }),
                setSidebarOpen: (isOpen) => set({ isSidebarOpen: isOpen }),
                setThreads: (threads) => set({ threads }),
                setSelectedActionId: (id) => set({ selectedActionId: id }),

                fetchHistory: async (token) => {
                    if (!token) {
                        set({ threads: [], historyLoading: false, historyError: null });
                        return;
                    }
                    set({ historyLoading: true, historyError: null });
                    try {
                        const res = await fetch('/api/history', {
                            headers: {
                                Authorization: `Bearer ${token}`,
                            },
                            cache: 'no-store',
                        });
                        if (!res.ok) {
                            console.warn('History fetch failed, but continuing with empty state');
                            set({ threads: [], historyError: '履歴の取得に失敗しました。' });
                            return;
                        }
                        const data = await res.json();
                        if (Array.isArray(data)) {
                            set({ threads: data, historyError: null });
                        } else {
                            set({ threads: [], historyError: '履歴データの形式が不正です。' });
                        }
                    } catch (error) {
                        console.error('History fetch error:', error);
                        set({ threads: [], historyError: '履歴の取得中にエラーが発生しました。' });
                    } finally {
                        set({ historyLoading: false });
                    }
                },
                createSession: () => set({ currentThreadId: null }),
                resetForAuthBoundary: () => set({
                    currentThreadId: null,
                    threads: [],
                    historyLoading: false,
                    historyError: null,
                    pendingMessage: null,
                    pendingThreadFiles: {},
                    pendingHomeInput: null,
                    pendingProductType: null,
                    selectedActionId: null,
                }),

                updateThreadTitle: (id: string, title: string) => set((state) => {
                    const exists = state.threads.some((t) => t.id === id);
                    if (exists) {
                        return {
                            threads: state.threads.map((t) => (t.id === id ? { ...t, title, updatedAt: new Date().toISOString() } : t)),
                        };
                    } else {
                        // If it doesn't exist (e.g. new chat), add it
                        return {
                            threads: [
                                { id, title, updatedAt: new Date().toISOString() },
                                ...state.threads,
                            ],
                        };
                    }
                }),
                setPendingMessage: (threadId, text) => set({ pendingMessage: { threadId, text } }),
                consumePendingMessage: (threadId) => {
                    const pending = get().pendingMessage;
                    if (!pending || pending.threadId !== threadId) return null;
                    set({ pendingMessage: null });
                    return pending.text;
                },
                setPendingThreadFiles: (threadId, files) => set((state) => ({
                    pendingThreadFiles: {
                        ...state.pendingThreadFiles,
                        [threadId]: files,
                    },
                })),
                consumePendingThreadFiles: (threadId) => {
                    const pendingFiles = get().pendingThreadFiles[threadId] ?? [];
                    set((state) => {
                        const nextFiles = { ...state.pendingThreadFiles };
                        delete nextFiles[threadId];
                        return { pendingThreadFiles: nextFiles };
                    });
                    return pendingFiles;
                },
                setPendingHomeInput: (text) => set({ pendingHomeInput: text }),
                consumePendingHomeInput: () => {
                    const pending = get().pendingHomeInput;
                    set({ pendingHomeInput: null });
                    return pending;
                },
                setPendingAspectRatio: (ratio) => set({ pendingAspectRatio: ratio }),
                consumePendingAspectRatio: () => {
                    const pending = get().pendingAspectRatio;
                    set({ pendingAspectRatio: null });
                    return pending;
                },
                setPendingProductType: (type) => set({ pendingProductType: type }),
                consumePendingProductType: () => {
                    const pending = get().pendingProductType;
                    set({ pendingProductType: null });
                    return pending;
                },
            }),
            {
                name: 'lobe-chat-storage',
                partialize: (state) => ({
                    currentThreadId: state.currentThreadId,
                    threads: state.threads,
                    historyLoading: state.historyLoading,
                    historyError: state.historyError,
                    isSidebarOpen: state.isSidebarOpen,
                    pendingMessage: state.pendingMessage,
                    pendingHomeInput: state.pendingHomeInput,
                    pendingAspectRatio: state.pendingAspectRatio,
                    pendingProductType: state.pendingProductType,
                    selectedActionId: state.selectedActionId,
                }),
            }
        )
    )
);
