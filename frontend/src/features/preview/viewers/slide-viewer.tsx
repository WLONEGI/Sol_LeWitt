"use client"

import { useState, useRef, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Check, X, Loader2 } from "lucide-react"
import { useArtifactStore } from "../store/artifact"
import { cn } from "@/lib/utils"

interface SlideViewerProps {
    content: any // Expecting string (URL) or object with url
    imageId?: string
}

interface Rect {
    x: number
    y: number
    w: number
    h: number
}

export function SlideViewer({ content, imageId }: SlideViewerProps) {
    const imageUrl = typeof content === 'string' ? content : (content?.url || content?.image_url);
    const { updateArtifactContent } = useArtifactStore()

    // Interaction State
    const [selection, setSelection] = useState<Rect | null>(null)
    const [isDrawing, setIsDrawing] = useState(false)
    const [startPoint, setStartPoint] = useState<{ x: number, y: number } | null>(null)
    const [prompt, setPrompt] = useState("")
    const [isSubmitting, setIsSubmitting] = useState(false)

    const containerRef = useRef<HTMLDivElement>(null)

    // Reset selection when image changes
    useEffect(() => {
        setSelection(null)
        setPrompt("")
    }, [imageUrl])

    if (!imageUrl) {
        return (
            <div className="h-full w-full flex items-center justify-center text-muted-foreground bg-muted/10">
                <p>No slide image available</p>
                <div className="text-xs mt-2 opacity-50">Content: {JSON.stringify(content)}</div>
            </div>
        )
    }

    // Coordinates are in % (0-100) to be responsive
    const getCoords = (e: React.MouseEvent) => {
        if (!containerRef.current) return { x: 0, y: 0 }
        const rect = containerRef.current.getBoundingClientRect()
        const x = ((e.clientX - rect.left) / rect.width) * 100
        const y = ((e.clientY - rect.top) / rect.height) * 100
        return { x, y }
    }

    const handleMouseDown = (e: React.MouseEvent) => {
        if (selection || isSubmitting) return;
        const p = getCoords(e)
        setStartPoint(p)
        setIsDrawing(true)
        setSelection({ x: p.x, y: p.y, w: 0, h: 0 })
    }

    const handleMouseMove = (e: React.MouseEvent) => {
        if (!isDrawing || !startPoint) return
        const p = getCoords(e)

        // Calculate rect logic
        const x = Math.min(p.x, startPoint.x)
        const y = Math.min(p.y, startPoint.y)
        const w = Math.abs(p.x - startPoint.x)
        const h = Math.abs(p.y - startPoint.y)

        setSelection({ x, y, w, h })
    }

    const handleMouseUp = () => {
        if (isDrawing) {
            setIsDrawing(false)
            // If too small, cancel
            if (selection && (selection.w < 1 || selection.h < 1)) {
                setSelection(null)
            }
        }
    }

    const handleClear = () => {
        setSelection(null)
        setPrompt("")
    }

    const handleSubmit = async () => {
        if (!selection || !prompt || !imageId) return
        setIsSubmitting(true)

        try {
            const response = await fetch(`/api/image/${imageId}/inpaint`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    rect: selection, // {x, y, w, h} in %
                    prompt: prompt
                })
            })

            const data = await response.json()
            console.log("In-painting Response:", data)

            if (data.new_image_url) {
                // Update the artifact with the new image
                // Assuming content structure: { ..., url: new_url } or just new_url string
                const newContent = typeof content === 'string' ? data.new_image_url : { ...content, url: data.new_image_url }
                updateArtifactContent(imageId, newContent)
                handleClear()
            } else {
                // Stub behavior or error
                alert(data.message || "Request sent (Stub)")
                handleClear()
            }

        } catch (error) {
            console.error("In-painting failed:", error)
            alert("Failed to submit in-painting request")
        } finally {
            setIsSubmitting(false)
        }
    }

    return (
        <div className="h-full w-full flex flex-col bg-transparent p-8 relative select-none">
            <div className="flex-1 flex items-center justify-center relative group perspective-1000">

                {/* Image Container with Cinematic Glow */}
                <div
                    ref={containerRef}
                    className="relative max-h-full max-w-full aspect-[16/9] shadow-2xl rounded-sm cursor-crosshair transition-transform duration-500 ease-out group-hover:scale-[1.01]"
                    style={{
                        boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5), 0 0 40px rgba(124, 58, 237, 0.1)"
                    }}
                    onMouseDown={handleMouseDown}
                    onMouseMove={handleMouseMove}
                    onMouseUp={handleMouseUp}
                    onMouseLeave={handleMouseUp}
                >
                    <img
                        src={imageUrl}
                        alt="Slide Preview"
                        className={cn("h-full w-full object-contain pointer-events-none transition-opacity bg-black rounded-sm", isSubmitting && "opacity-50")}
                    />

                    {isSubmitting && (
                        <div className="absolute inset-0 flex items-center justify-center text-white z-40 bg-black/40 backdrop-blur-sm">
                            <Loader2 className="h-10 w-10 animate-spin text-primary" />
                        </div>
                    )}

                    {/* Selection Overlay */}
                    {selection && !isSubmitting && (
                        <div
                            className="absolute border-2 border-primary bg-primary/20 z-20 shadow-[0_0_15px_rgba(124,58,237,0.5)]"
                            style={{
                                left: `${selection.x}%`,
                                top: `${selection.y}%`,
                                width: `${selection.w}%`,
                                height: `${selection.h}%`,
                            }}
                        >
                            {/* Prompt Bubble */}
                            {!isDrawing && (
                                <div className="absolute top-full left-0 mt-3 bg-black/80 backdrop-blur-md border border-white/10 rounded-xl shadow-2xl p-2 w-[300px] flex gap-2 animate-in fade-in zoom-in-95 z-30 slide-in-from-top-2">
                                    <Input
                                        autoFocus
                                        placeholder="How to change this area?"
                                        className="h-9 text-xs bg-white/5 border-white/5 focus-visible:ring-primary/50 text-white"
                                        value={prompt}
                                        onChange={(e) => setPrompt(e.target.value)}
                                        onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
                                    />
                                    <Button size="icon" className="h-9 w-9 shrink-0 bg-primary hover:bg-primary/90" onClick={handleSubmit}>
                                        <Check className="h-4 w-4" />
                                    </Button>
                                    <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0 hover:bg-white/10 text-muted-foreground" onClick={handleClear}>
                                        <X className="h-4 w-4" />
                                    </Button>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* Toolbar / Status - Floating Glass */}
            <div className="absolute bottom-6 left-1/2 -translate-x-1/2 min-w-[300px] h-12 border border-white/10 rounded-full glass-panel flex items-center px-6 justify-between shrink-0 shadow-lg text-white/80 transition-all duration-300 hover:bg-black/40">
                <span className="text-xs font-medium tracking-wide">
                    {selection ? "AREA SELECTED" : "DRAG TO EDIT"}
                </span>
                {selection && (
                    <Button variant="ghost" size="sm" onClick={handleClear} className="text-xs h-7 ml-4 hover:bg-white/10 hover:text-white rounded-full px-3">
                        Cancel
                    </Button>
                )}
            </div>
        </div>
    )
}
