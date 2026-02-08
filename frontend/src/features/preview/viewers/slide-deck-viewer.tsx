"use client"

import { useEffect, useMemo, useState } from "react"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Download, ChevronLeft, ChevronRight, Pencil } from "lucide-react"
import { Button } from "@/components/ui/button"
import { InpaintCanvas } from "@/features/preview/components/inpaint-canvas"
import { useArtifactStore } from "@/features/preview/stores/artifact"

interface SlideDeckViewerProps {
    artifactId: string
    content: {
        slides?: Array<{
            slide_number: number
            title?: string
            image_url?: string
            image_versions?: string[]
            current_version?: number
            prompt_text?: string
            structured_prompt?: any
            rationale?: string
            layout_type?: string
            selected_inputs?: string[]
            compiled_prompt?: string
        }>
        pdf_url?: string
    }
}

function getSlideVersionState(slide: any) {
    const baseUrl = slide?.image_url || null
    const versions = Array.isArray(slide?.image_versions)
        ? slide.image_versions.filter(Boolean)
        : (baseUrl ? [baseUrl] : [])
    let currentIndex = Number.isInteger(slide?.current_version)
        ? slide.current_version
        : (versions.length > 0 ? versions.length - 1 : 0)
    if (versions.length === 0) {
        return { url: baseUrl, versions: [], currentIndex: 0 }
    }
    if (currentIndex < 0 || currentIndex >= versions.length) {
        currentIndex = versions.length - 1
    }
    const url = versions[currentIndex] ?? baseUrl
    return { url, versions, currentIndex }
}

export function SlideDeckViewer({ content, artifactId }: SlideDeckViewerProps) {
    const [tab, setTab] = useState<"image" | "prompt" | "pdf">("image")
    const [editingSlideNumber, setEditingSlideNumber] = useState<number | null>(null)
    const { updateArtifactContent } = useArtifactStore()

    const slides = useMemo(() => {
        const list = Array.isArray(content?.slides)
            ? content.slides
            : (Array.isArray((content as any)?.prompts) ? (content as any).prompts : [])
        return [...list].sort((a: any, b: any) => a.slide_number - b.slide_number)
    }, [content?.slides, (content as any)?.prompts])

    useEffect(() => {
        if (tab !== "image" && editingSlideNumber !== null) {
            setEditingSlideNumber(null)
        }
    }, [tab, editingSlideNumber])

    const editingSlide = editingSlideNumber == null
        ? null
        : slides.find((s) => s.slide_number === editingSlideNumber) || null

    const handleVersionChange = (slideNumber: number, nextIndex: number) => {
        const nextSlides = slides.map((slide) => {
            if (slide.slide_number !== slideNumber) return slide
            const versionState = getSlideVersionState(slide)
            if (!versionState.versions[nextIndex]) return slide
            return {
                ...slide,
                image_url: versionState.versions[nextIndex],
                image_versions: versionState.versions,
                current_version: nextIndex,
            }
        })
        updateArtifactContent(artifactId, { ...content, slides: nextSlides })
    }

    const handleInpaintSubmit = async (prompt: string) => {
        if (!editingSlide) return
        const response = await fetch(`/api/slide-deck/${artifactId}/slides/${editingSlide.slide_number}/inpaint`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                prompt,
                image_url: getSlideVersionState(editingSlide).url,
            }),
        })
        const data = await response.json()
        if (!data?.new_image_url) {
            alert(data?.message || "Request sent (Stub)")
            return
        }

        const nextSlides = slides.map((slide) => {
            if (slide.slide_number !== editingSlide.slide_number) return slide
            const versionState = getSlideVersionState(slide)
            const baseVersions = versionState.versions.length > 0
                ? versionState.versions
                : (versionState.url ? [versionState.url] : [])
            const nextVersions = [...baseVersions, data.new_image_url]
            const nextIndex = nextVersions.length - 1
            return {
                ...slide,
                image_url: data.new_image_url,
                image_versions: nextVersions,
                current_version: nextIndex,
            }
        })

        updateArtifactContent(artifactId, { ...content, slides: nextSlides })
    }

    return (
        <div className="flex flex-col flex-1 min-h-0 bg-background">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                <div className="flex items-center gap-2">
                    <button
                        className={cn(
                            "px-3 py-1.5 text-xs font-semibold rounded-md border transition-colors",
                            tab === "image"
                                ? "bg-foreground text-background border-foreground"
                                : "bg-transparent text-foreground border-border hover:bg-muted"
                        )}
                        onClick={() => setTab("image")}
                    >
                        Image
                    </button>
                    <button
                        className={cn(
                            "px-3 py-1.5 text-xs font-semibold rounded-md border transition-colors",
                            tab === "prompt"
                                ? "bg-foreground text-background border-foreground"
                                : "bg-transparent text-foreground border-border hover:bg-muted"
                        )}
                        onClick={() => setTab("prompt")}
                    >
                        Prompt
                    </button>
                    {content?.pdf_url && (
                        <button
                            className={cn(
                                "px-3 py-1.5 text-xs font-semibold rounded-md border transition-colors",
                                tab === "pdf"
                                    ? "bg-foreground text-background border-foreground"
                                    : "bg-transparent text-foreground border-border hover:bg-muted"
                            )}
                            onClick={() => setTab("pdf")}
                        >
                            PDF
                        </button>
                    )}
                </div>

                {content?.pdf_url && (
                    <a
                        href={content.pdf_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2 text-xs font-semibold px-3 py-1.5 rounded-md border border-border hover:bg-muted transition-colors"
                    >
                        <Download className="w-3 h-3" />
                        PDF
                    </a>
                )}
            </div>

            {tab === "pdf" && content?.pdf_url ? (
                <div className="flex-1 min-h-0 p-4">
                    <iframe
                        src={content.pdf_url}
                        className="w-full h-full rounded-md border border-border bg-muted/10"
                        title="Combined Slide PDF"
                    />
                </div>
            ) : (
                <div className="relative flex-1 min-h-0">
                    <ScrollArea className="h-full p-4">
                        <div className="flex flex-col gap-6">
                            {slides.map((slide) => {
                                const versionState = getSlideVersionState(slide)
                                const isEditing = editingSlideNumber === slide.slide_number
                                const disableOther = editingSlideNumber != null && !isEditing
                                return (
                                    <div
                                        key={slide.slide_number}
                                        className={cn(
                                            "flex flex-col gap-2",
                                            disableOther && "opacity-40 pointer-events-none"
                                        )}
                                    >
                                        <div className="flex items-center justify-between">
                                            <div className="text-sm font-semibold">
                                                {slide.title || `Slide ${slide.slide_number}`}
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-6 w-6"
                                                    onClick={() => handleVersionChange(slide.slide_number, versionState.currentIndex - 1)}
                                                    disabled={tab !== "image" || editingSlideNumber != null || versionState.currentIndex <= 0}
                                                >
                                                    <ChevronLeft className="h-4 w-4" />
                                                </Button>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-6 w-6"
                                                    onClick={() => handleVersionChange(slide.slide_number, versionState.currentIndex + 1)}
                                                    disabled={tab !== "image" || editingSlideNumber != null || versionState.currentIndex >= versionState.versions.length - 1}
                                                >
                                                    <ChevronRight className="h-4 w-4" />
                                                </Button>
                                                <Button
                                                    size="sm"
                                                    className="h-6 px-2 text-xs"
                                                    onClick={() => setEditingSlideNumber(slide.slide_number)}
                                                    disabled={tab !== "image" || editingSlideNumber != null || !versionState.url}
                                                >
                                                    <Pencil className="h-3 w-3 mr-1" />
                                                    部分修正
                                                </Button>
                                                <div className="text-[10px] font-mono text-muted-foreground bg-muted px-2 py-0.5 rounded">
                                                    {String(slide.slide_number).padStart(2, "0")}
                                                </div>
                                            </div>
                                        </div>

                                        {tab === "image" ? (
                                            <div className="aspect-video w-full rounded-md overflow-hidden border border-border bg-muted/30">
                                                {isEditing ? (
                                                    <InpaintCanvas
                                                        imageUrl={versionState.url || ""}
                                                        onSubmit={handleInpaintSubmit}
                                                        onCancel={() => setEditingSlideNumber(null)}
                                                    />
                                                ) : (
                                                    <>
                                                        {versionState.url ? (
                                                            <img
                                                                src={versionState.url}
                                                                alt={`Slide ${slide.slide_number}`}
                                                                className="h-full w-full object-contain"
                                                            />
                                                        ) : (
                                                            <div className="h-full w-full flex items-center justify-center text-xs text-muted-foreground">
                                                                Image not available yet
                                                            </div>
                                                        )}
                                                    </>
                                                )}
                                            </div>
                                        ) : (
                                            <div className="flex flex-col gap-3">
                                                {slide.compiled_prompt || slide.prompt_text ? (
                                                    <div className="rounded-md border border-border bg-muted/20 p-3">
                                                        <pre className="text-xs whitespace-pre-wrap break-words font-mono text-foreground/80">
                                                            {slide.compiled_prompt || slide.prompt_text}
                                                        </pre>
                                                    </div>
                                                ) : (
                                                    <div className="text-sm text-muted-foreground italic">
                                                        No compiled prompt information available.
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                )
                            })}
                        </div>
                    </ScrollArea>

                    {/*
                      オーバーレイは不要: 編集対象のスライド内で直接入力UIを表示
                    */}
                </div>
            )}
        </div>
    )
}
