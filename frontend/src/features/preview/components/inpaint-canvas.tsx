"use client"

import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react"
import { Button } from "@/components/ui/button"
import { Check, Eraser, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import TextareaAutosize from "react-textarea-autosize"

export interface InpaintSubmitPayload {
    prompt: string
    maskImageUrl: string
}

interface InpaintCanvasProps {
    imageUrl: string
    onSubmit: (payload: InpaintSubmitPayload) => Promise<void>
    onCancel: () => void
    className?: string
}

type Point = {
    x: number
    y: number
}

type RenderArea = {
    offsetX: number
    offsetY: number
    width: number
    height: number
}

export function InpaintCanvas({ imageUrl, onSubmit, onCancel, className }: InpaintCanvasProps) {
    const [prompt, setPrompt] = useState("")
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [brushSize, setBrushSize] = useState(28)
    const [hasMask, setHasMask] = useState(false)
    const [isCanvasReady, setIsCanvasReady] = useState(false)

    const imageRef = useRef<HTMLImageElement>(null)
    const overlayCanvasRef = useRef<HTMLCanvasElement>(null)
    const maskCanvasRef = useRef<HTMLCanvasElement | null>(null)
    const isDrawingRef = useRef(false)
    const previousPointRef = useRef<Point | null>(null)

    const clearMask = () => {
        const overlayCanvas = overlayCanvasRef.current
        const maskCanvas = maskCanvasRef.current
        if (overlayCanvas) {
            const overlayCtx = overlayCanvas.getContext("2d")
            overlayCtx?.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height)
        }
        if (maskCanvas) {
            const maskCtx = maskCanvas.getContext("2d")
            maskCtx?.clearRect(0, 0, maskCanvas.width, maskCanvas.height)
        }
        setHasMask(false)
        isDrawingRef.current = false
        previousPointRef.current = null
    }

    const initializeCanvases = () => {
        const image = imageRef.current
        const overlayCanvas = overlayCanvasRef.current
        if (!image || !overlayCanvas) {
            return
        }

        const rect = image.getBoundingClientRect()
        const viewWidth = Math.max(1, Math.round(rect.width))
        const viewHeight = Math.max(1, Math.round(rect.height))
        if (viewWidth <= 1 || viewHeight <= 1) {
            return
        }

        overlayCanvas.width = viewWidth
        overlayCanvas.height = viewHeight

        const maskCanvas = document.createElement("canvas")
        maskCanvas.width = image.naturalWidth > 0 ? image.naturalWidth : viewWidth
        maskCanvas.height = image.naturalHeight > 0 ? image.naturalHeight : viewHeight
        maskCanvasRef.current = maskCanvas

        clearMask()
        setIsCanvasReady(true)
    }

    const getRenderArea = (): RenderArea | null => {
        const image = imageRef.current
        const overlayCanvas = overlayCanvasRef.current
        if (!image || !overlayCanvas || image.naturalWidth <= 0 || image.naturalHeight <= 0) {
            return null
        }

        const canvasWidth = overlayCanvas.width
        const canvasHeight = overlayCanvas.height
        if (canvasWidth <= 0 || canvasHeight <= 0) {
            return null
        }

        const imageAspect = image.naturalWidth / image.naturalHeight
        const canvasAspect = canvasWidth / canvasHeight

        if (imageAspect >= canvasAspect) {
            const width = canvasWidth
            const height = width / imageAspect
            return {
                offsetX: 0,
                offsetY: (canvasHeight - height) / 2,
                width,
                height,
            }
        }

        const height = canvasHeight
        const width = height * imageAspect
        return {
            offsetX: (canvasWidth - width) / 2,
            offsetY: 0,
            width,
            height,
        }
    }

    useEffect(() => {
        setPrompt("")
        setIsCanvasReady(false)
        maskCanvasRef.current = null
        clearMask()
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [imageUrl])

    const drawStroke = (from: Point, to: Point) => {
        const overlayCanvas = overlayCanvasRef.current
        const maskCanvas = maskCanvasRef.current
        const renderArea = getRenderArea()
        if (!overlayCanvas || !maskCanvas || !renderArea) {
            return
        }

        const overlayCtx = overlayCanvas.getContext("2d")
        const maskCtx = maskCanvas.getContext("2d")
        if (!overlayCtx || !maskCtx) {
            return
        }

        overlayCtx.save()
        overlayCtx.beginPath()
        overlayCtx.rect(renderArea.offsetX, renderArea.offsetY, renderArea.width, renderArea.height)
        overlayCtx.clip()
        overlayCtx.strokeStyle = "rgba(239, 68, 68, 0.6)"
        overlayCtx.lineCap = "round"
        overlayCtx.lineJoin = "round"
        overlayCtx.lineWidth = brushSize
        overlayCtx.beginPath()
        overlayCtx.moveTo(from.x, from.y)
        overlayCtx.lineTo(to.x, to.y)
        overlayCtx.stroke()
        overlayCtx.restore()

        const scaleX = maskCanvas.width / renderArea.width
        const scaleY = maskCanvas.height / renderArea.height
        const fromMaskX = (from.x - renderArea.offsetX) * scaleX
        const fromMaskY = (from.y - renderArea.offsetY) * scaleY
        const toMaskX = (to.x - renderArea.offsetX) * scaleX
        const toMaskY = (to.y - renderArea.offsetY) * scaleY

        maskCtx.strokeStyle = "#ffffff"
        maskCtx.lineCap = "round"
        maskCtx.lineJoin = "round"
        maskCtx.lineWidth = Math.max(1, ((scaleX + scaleY) / 2) * brushSize)
        maskCtx.beginPath()
        maskCtx.moveTo(fromMaskX, fromMaskY)
        maskCtx.lineTo(toMaskX, toMaskY)
        maskCtx.stroke()

        setHasMask(true)
    }

    const getPointFromEvent = (event: ReactPointerEvent<HTMLCanvasElement>): Point | null => {
        const canvas = overlayCanvasRef.current
        const renderArea = getRenderArea()
        if (!canvas || !renderArea) {
            return null
        }
        const rect = canvas.getBoundingClientRect()
        const x = Math.min(Math.max(0, event.clientX - rect.left), rect.width)
        const y = Math.min(Math.max(0, event.clientY - rect.top), rect.height)

        if (
            x < renderArea.offsetX
            || x > renderArea.offsetX + renderArea.width
            || y < renderArea.offsetY
            || y > renderArea.offsetY + renderArea.height
        ) {
            return null
        }
        return { x, y }
    }

    const handlePointerDown = (event: ReactPointerEvent<HTMLCanvasElement>) => {
        if (isSubmitting || !isCanvasReady) {
            return
        }
        event.preventDefault()
        const canvas = overlayCanvasRef.current
        if (!canvas) {
            return
        }
        canvas.setPointerCapture(event.pointerId)

        const point = getPointFromEvent(event)
        if (!point) {
            return
        }
        isDrawingRef.current = true
        previousPointRef.current = point
        drawStroke(point, point)
    }

    const handlePointerMove = (event: ReactPointerEvent<HTMLCanvasElement>) => {
        if (!isDrawingRef.current || isSubmitting || !isCanvasReady) {
            return
        }
        event.preventDefault()
        const nextPoint = getPointFromEvent(event)
        if (!nextPoint) {
            finishDrawing()
            return
        }
        const previous = previousPointRef.current
        if (!previous) {
            previousPointRef.current = nextPoint
            drawStroke(nextPoint, nextPoint)
            return
        }
        drawStroke(previous, nextPoint)
        previousPointRef.current = nextPoint
    }

    const finishDrawing = () => {
        isDrawingRef.current = false
        previousPointRef.current = null
    }

    const handleCancel = () => {
        setPrompt("")
        clearMask()
        onCancel()
    }

    const handleSubmit = async () => {
        if (!prompt.trim() || !hasMask || isSubmitting) {
            return
        }

        const maskCanvas = maskCanvasRef.current
        if (!maskCanvas) {
            return
        }

        setIsSubmitting(true)
        try {
            await onSubmit({
                prompt: prompt.trim(),
                maskImageUrl: maskCanvas.toDataURL("image/png"),
            })
            handleCancel()
        } catch (error) {
            console.error("In-painting failed:", error)
            alert("Failed to submit in-painting request")
        } finally {
            setIsSubmitting(false)
        }
    }

    return (
        <div
            className={cn(
                "relative max-h-full max-w-full aspect-[16/9] shadow-2xl rounded-md select-none overflow-hidden",
                className
            )}
        >
            <img
                ref={imageRef}
                src={imageUrl}
                alt="Slide Preview"
                className={cn("h-full w-full object-contain pointer-events-none transition-opacity bg-muted/20 rounded-md", isSubmitting && "opacity-50")}
                onLoad={initializeCanvases}
            />

            <canvas
                ref={overlayCanvasRef}
                className={cn("absolute inset-0 h-full w-full cursor-crosshair touch-none", !isCanvasReady && "pointer-events-none")}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={finishDrawing}
                onPointerLeave={finishDrawing}
                onPointerCancel={finishDrawing}
            />

            {isSubmitting && (
                <div className="absolute inset-0 flex items-center justify-center z-40 bg-background/50 backdrop-blur-sm">
                    <Loader2 className="h-10 w-10 animate-spin text-primary" />
                </div>
            )}

            {!isSubmitting && (
                <>
                    <div className="absolute top-3 left-3 bg-background/90 backdrop-blur-md border border-border rounded-lg shadow-lg p-2 z-30 text-foreground">
                        <div className="flex items-center gap-2">
                            <span className="text-[11px] font-medium">修正範囲</span>
                            <input
                                type="range"
                                min={8}
                                max={96}
                                step={2}
                                value={brushSize}
                                onChange={(event) => setBrushSize(Number(event.target.value))}
                                className="w-28 accent-primary"
                            />
                            <span className="text-[10px] text-muted-foreground w-8 text-right">{brushSize}</span>
                            <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2 text-[11px]"
                                onClick={clearMask}
                                disabled={!hasMask}
                            >
                                <Eraser className="h-3 w-3 mr-1" />
                                クリア
                            </Button>
                        </div>
                        <p className="mt-1 text-[10px] text-muted-foreground">赤い範囲だけを編集します</p>
                    </div>

                    <div className="absolute left-1/2 -translate-x-1/2 bottom-3 bg-background/92 backdrop-blur-md border border-border rounded-lg shadow-lg p-3 w-[min(92vw,420px)] z-30">
                        <TextareaAutosize
                            minRows={2}
                            maxRows={3}
                            autoFocus
                            placeholder="修正したい内容を入力"
                            className="w-full resize-none bg-background border border-border rounded-md px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/60"
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                                    e.preventDefault()
                                    handleSubmit()
                                }
                            }}
                        />
                        <div className="mt-2 flex items-center justify-between">
                            <span className="text-[10px] text-muted-foreground">
                                {!hasMask
                                    ? "先に修正範囲を赤く塗ってください"
                                    : prompt.trim()
                                        ? "Ctrl/⌘ + Enterで送信"
                                        : "修正指示を入力してください"}
                            </span>
                            <div className="flex items-center gap-2">
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 px-2 text-[11px]"
                                    onClick={handleCancel}
                                >
                                    キャンセル
                                </Button>
                                <Button
                                    size="icon"
                                    className="h-7 w-7 shrink-0"
                                    onClick={handleSubmit}
                                    disabled={!prompt.trim() || !hasMask || isSubmitting || !isCanvasReady}
                                >
                                    <Check className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>
                    </div>
                </>
            )}
        </div>
    )
}
