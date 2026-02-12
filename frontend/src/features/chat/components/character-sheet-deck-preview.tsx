"use client"

import { SlideDeckPreview, type SlideDeckItem } from "./slide-deck-preview"

interface CharacterSheetDeckPreviewProps {
    artifactId: string;
    slides: SlideDeckItem[];
    title?: string;
    isStreaming?: boolean;
    aspectRatio?: string;
}

export function CharacterSheetDeckPreview(props: CharacterSheetDeckPreviewProps) {
    return <SlideDeckPreview {...props} compact />
}
