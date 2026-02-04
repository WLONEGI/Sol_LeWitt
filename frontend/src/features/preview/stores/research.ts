
import { create } from 'zustand';

export interface ResearchTaskState {
    taskId: string;
    perspective: string;
    status: 'running' | 'completed';
    content: string;
    citations: Array<{ title: string; uri: string }>;
}

interface ResearchStore {
    tasks: Record<string, ResearchTaskState>;
    registerTask: (taskId: string, perspective: string) => void;
    appendContent: (taskId: string, token: string) => void;
    setCitations: (taskId: string, sources: Array<{ title: string; uri: string }>) => void;
    completeTask: (taskId: string) => void;
}

export const useResearchStore = create<ResearchStore>((set) => ({
    tasks: {},
    registerTask: (taskId, perspective) => set((state) => ({
        tasks: {
            ...state.tasks,
            [taskId]: {
                taskId,
                perspective,
                status: 'running',
                content: '',
                citations: []
            }
        }
    })),
    appendContent: (taskId, token) => set((state) => {
        const task = state.tasks[taskId];
        if (!task) return state;
        return {
            tasks: {
                ...state.tasks,
                [taskId]: { ...task, content: task.content + token }
            }
        };
    }),
    setCitations: (taskId, sources) => set((state) => {
        const task = state.tasks[taskId];
        if (!task) return state;
        return {
            tasks: {
                ...state.tasks,
                [taskId]: { ...task, citations: sources }
            }
        };
    }),
    completeTask: (taskId) => set((state) => {
        const task = state.tasks[taskId];
        if (!task) return state;
        return {
            tasks: {
                ...state.tasks,
                [taskId]: { ...task, status: 'completed' }
            }
        };
    })
}));
