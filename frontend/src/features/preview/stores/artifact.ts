import { create } from 'zustand';

export interface Artifact {
    id: string;
    type: string;
    title: string;
    content: any;
    version: number;
    status?: string;
}

interface ArtifactState {
    currentArtifact: Artifact | null;
    activeContextId: string | null;
    isPreviewOpen: boolean;
    artifacts: Record<string, Artifact>;
    setArtifact: (artifact: Artifact | null) => void;
    setActiveContextId: (id: string | null) => void;
    setPreviewOpen: (open: boolean) => void;
    setArtifacts: (artifacts: Record<string, Artifact>) => void;
    upsertArtifact: (artifact: Artifact) => void;
    updateArtifactContent: (id: string, content: any) => void;
}

export const useArtifactStore = create<ArtifactState>((set) => ({
    currentArtifact: null,
    activeContextId: null,
    isPreviewOpen: false,
    artifacts: {},
    setArtifact: (artifact) => set({ currentArtifact: artifact }),
    setActiveContextId: (id) => set({ activeContextId: id }),
    setPreviewOpen: (open) => set({ isPreviewOpen: open }),
    setArtifacts: (artifacts) => set({ artifacts }),
    upsertArtifact: (artifact) => set((state) => {
        const existing = state.artifacts[artifact.id];
        const mergedContent =
            existing && typeof existing.content === 'object' && typeof artifact.content === 'object'
                ? { ...existing.content, ...artifact.content }
                : (artifact.content ?? existing?.content);
        const merged = { ...existing, ...artifact, content: mergedContent };
        const artifacts = { ...state.artifacts, [artifact.id]: merged };
        const currentArtifact = state.currentArtifact?.id === artifact.id ? merged : state.currentArtifact;
        return { artifacts, currentArtifact };
    }),
    updateArtifactContent: (id, content) => set((state) => {
        const artifacts = { ...state.artifacts };
        if (artifacts[id]) {
            artifacts[id] = { ...artifacts[id], content };
        }
        const currentArtifact = state.currentArtifact?.id === id ? { ...state.currentArtifact, content } : state.currentArtifact;
        return { artifacts, currentArtifact };
    }),
}));
