import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

interface ChatState {
    currentThreadId: string | null;
    threads: Array<{ id: string; title: string; updatedAt: string }>;
    isSidebarOpen: boolean;

    setCurrentThreadId: (id: string | null) => void;
    setSidebarOpen: (isOpen: boolean) => void;
    setThreads: (threads: Array<{ id: string; title: string; updatedAt: string }>) => void;
    fetchHistory: () => Promise<void>;
    createSession: () => void;
    updateThreadTitle: (id: string, title: string) => void;
}

export const useChatStore = create<ChatState>()(
    devtools(
        persist(
            (set) => ({
                currentThreadId: null,
                threads: [],
                isSidebarOpen: true,

                setCurrentThreadId: (id) => set({ currentThreadId: id }),
                setSidebarOpen: (isOpen) => set({ isSidebarOpen: isOpen }),
                setThreads: (threads) => set({ threads }),

                fetchHistory: async () => {
                    try {
                        const res = await fetch('/api/history');
                        if (!res.ok) {
                            console.warn('History fetch failed, but continuing with empty state');
                            return;
                        }
                        const data = await res.json();
                        if (Array.isArray(data)) {
                            set({ threads: data });
                        }
                    } catch (error) {
                        console.error('History fetch error:', error);
                    }
                },
                createSession: () => set({ currentThreadId: null }),

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
            }),
            {
                name: 'lobe-chat-storage',
            }
        )
    )
);
