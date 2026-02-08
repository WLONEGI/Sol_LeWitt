"use client"

import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Check, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import TextareaAutosize from "react-textarea-autosize"

interface InpaintCanvasProps {
    imageUrl: string
    onSubmit: (prompt: string) => Promise<void>
    onCancel: () => void
    className?: string
}

export function InpaintCanvas({ imageUrl, onSubmit, onCancel, className }: InpaintCanvasProps) {
    const [prompt, setPrompt] = useState("")
    const [isSubmitting, setIsSubmitting] = useState(false)

    const containerRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        setPrompt("")
    }, [imageUrl])

    const handleCancel = () => {
        setPrompt("")
        onCancel()
    }

    const handleSubmit = async () => {
        if (!prompt.trim()) return
        setIsSubmitting(true)
        try {
            await onSubmit(prompt.trim())
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
            ref={containerRef}
            className={cn(
                "relative max-h-full max-w-full aspect-[16/9] shadow-2xl rounded-sm select-none",
                className
            )}
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
            {!isSubmitting && (
                <div className="absolute left-1/2 -translate-x-1/2 bottom-3 bg-black/70 backdrop-blur-md border border-white/10 rounded-xl shadow-2xl p-3 w-[360px] z-30">
                    <TextareaAutosize
                        minRows={2}
                        maxRows={3}
                        autoFocus
                        placeholder="例: 図の中央の円グラフを棒グラフに変更"
                        className="w-full resize-none bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder:text-white/40 focus:outline-none focus:ring-1 focus:ring-primary/60"
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
                        <span className="text-[10px] text-white/50">
                            {prompt.trim() ? "Ctrl/⌘ + Enterで送信" : "修正指示を入力してください"}
                        </span>
                        <div className="flex items-center gap-2">
                            <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2 text-[11px] text-white/70 hover:text-white hover:bg-white/10"
                                onClick={handleCancel}
                            >
                                キャンセル
                            </Button>
                            <Button
                                size="icon"
                                className="h-7 w-7 shrink-0"
                                onClick={handleSubmit}
                                disabled={!prompt.trim() || isSubmitting}
                            >
                                <Check className="h-4 w-4" />
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
