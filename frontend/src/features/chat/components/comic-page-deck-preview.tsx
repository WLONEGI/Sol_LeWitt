"use client"

import { SlideDeckPreview, type SlideDeckItem } from "./slide-deck-preview"

interface ComicPageDeckPreviewProps {
    artifactId: string;
    slides: SlideDeckItem[];
    title?: string;
    isStreaming?: boolean;
    aspectRatio?: string;
}

export function ComicPageDeckPreview(props: ComicPageDeckPreviewProps) {
    return <SlideDeckPreview {...props} />
}

