"use client"

import { useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { ChevronLeft, ChevronRight, Pencil } from "lucide-react"
import { useArtifactStore } from "@/features/preview/stores/artifact"
import { cn } from "@/lib/utils"
import { InpaintCanvas, type InpaintSubmitPayload } from "@/features/preview/components/inpaint-canvas"
import { useAuth } from "@/providers/auth-provider"
import { useChatStore } from "@/features/chat/stores/chat"
import { uploadInpaintReferenceImages } from "@/features/preview/lib/inpaint-reference-upload"

import { getAspectRatioClass } from "../utils/aspect-ratio"

interface SlideViewerProps {
    content: any // Expecting string (URL) or object with url
    imageId?: string
    aspectRatio?: string
}

function getVersionState(content: any) {
    const baseUrl = typeof content === "string" ? content : (content?.url || content?.image_url || null)
    const versions = Array.isArray(content?.image_versions)
        ? content.image_versions.filter(Boolean)
        : (baseUrl ? [baseUrl] : [])
    let currentIndex = Number.isInteger(content?.current_version)
        ? content.current_version
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

function buildVersionedContent(content: any, url: string, versions: string[], currentIndex: number) {
    if (!content || typeof content === "string") {
        return {
            url,
            image_url: url,
            image_versions: versions,
            current_version: currentIndex,
        }
    }
    return {
        ...content,
        url,
        image_url: url,
        image_versions: versions,
        current_version: currentIndex,
    }
}

export function SlideViewer({ content, imageId, aspectRatio }: SlideViewerProps) {
    const { updateArtifactContent } = useArtifactStore()
    const { token } = useAuth()
    const currentThreadId = useChatStore((state) => state.currentThreadId)

    const versionState = useMemo(() => getVersionState(content), [content])
    const imageUrl = versionState.url

    const [isEditing, setIsEditing] = useState(false)

    if (!imageUrl) {
        return (
            <div className="h-full w-full flex items-center justify-center text-muted-foreground bg-muted/10">
                <p>No slide image available</p>
            </div>
        )
    }

    const handleVersionChange = (nextIndex: number) => {
        if (!imageId) return
        const { versions } = getVersionState(content)
        if (!versions[nextIndex]) return
        const nextUrl = versions[nextIndex]
        updateArtifactContent(imageId, buildVersionedContent(content, nextUrl, versions, nextIndex))
    }

    const handleInpaintSubmit = async ({ prompt, maskImageUrl, referenceFiles }: InpaintSubmitPayload) => {
        if (!imageId) return
        if (!token) throw new Error("認証情報がありません。再ログインしてください。")
        const referenceImages = await uploadInpaintReferenceImages({
            token,
            files: referenceFiles,
            threadId: currentThreadId || imageId,
        })
        const response = await fetch(`/api/image/${imageId}/inpaint`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
                prompt,
                image_url: imageUrl,
                mask_image_url: maskImageUrl,
                reference_images: referenceImages,
            }),
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) {
            const detail =
                typeof data?.detail === "string"
                    ? data.detail
                    : (typeof data?.message === "string"
                        ? data.message
                        : (typeof data?.error === "string" ? data.error : "In-painting failed"))
            throw new Error(detail)
        }
        if (typeof data?.new_image_url !== "string" || data.new_image_url.length === 0) {
            throw new Error("In-painting failed: 生成画像URLが返却されませんでした。")
        }
        const current = getVersionState(content)
        const baseVersions = current.versions.length > 0 ? current.versions : (current.url ? [current.url] : [])
        const nextVersions = [...baseVersions, data.new_image_url]
        const nextIndex = nextVersions.length - 1
        updateArtifactContent(imageId, buildVersionedContent(content, data.new_image_url, nextVersions, nextIndex))
    }

    return (
        <div className="h-full w-full flex flex-col bg-transparent p-8 relative select-none">
            <div className="flex-1 flex items-center justify-center relative group perspective-1000">

                {/* Image Container with Cinematic Glow */}
                <div
                    className={cn(
                        "relative max-h-full max-w-full shadow-2xl rounded-md transition-transform duration-500 ease-out group-hover:scale-[1.01]",
                        getAspectRatioClass(aspectRatio)
                    )}
                    style={{
                        boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5), 0 0 40px rgba(124, 58, 237, 0.1)"
                    }}
                >
                    {isEditing ? (
                        <InpaintCanvas
                            imageUrl={imageUrl}
                            onSubmit={handleInpaintSubmit}
                            onCancel={() => setIsEditing(false)}
                        />
                    ) : (
                        <img
                            src={imageUrl}
                            alt="Slide Preview"
                            className={cn("h-full w-full object-contain pointer-events-none transition-opacity bg-muted/20 rounded-md")}
                        />
                    )}

                    <div className="absolute top-2 right-2 z-10 flex items-center gap-2 bg-background/90 border border-border rounded-full px-2 py-1">
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6"
                            onClick={() => handleVersionChange(versionState.currentIndex - 1)}
                            disabled={isEditing || versionState.currentIndex <= 0}
                        >
                            <ChevronLeft className="h-4 w-4" />
                        </Button>
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6"
                            onClick={() => handleVersionChange(versionState.currentIndex + 1)}
                            disabled={isEditing || versionState.currentIndex >= versionState.versions.length - 1}
                        >
                            <ChevronRight className="h-4 w-4" />
                        </Button>
                        <div className="w-px h-4 bg-border mx-1" />
                        <Button
                            size="sm"
                            className="h-6 px-2 text-xs"
                            onClick={() => setIsEditing(true)}
                            disabled={isEditing || !imageId}
                        >
                            <Pencil className="h-3 w-3 mr-1" />
                            部分修正
                        </Button>
                    </div>
                </div>
            </div>

        </div>
    )
}
