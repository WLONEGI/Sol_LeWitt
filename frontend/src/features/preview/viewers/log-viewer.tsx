"use client"

import { ScrollArea } from "@/components/ui/scroll-area"

interface LogViewerProps {
    content: string
    title?: string
}

export function LogViewer({ content, title }: LogViewerProps) {
    return (
        <div className="flex flex-col flex-1 min-h-0 bg-black/90 text-green-400 font-mono text-xs">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-white/10 bg-white/5 shrink-0">
                <span className="font-semibold">{title || "System Log"}</span>
            </div>

            {/* Log Content */}
            <ScrollArea className="flex-1 min-h-0 p-4">
                <pre className="whitespace-pre-wrap break-all">{content}</pre>
            </ScrollArea>
        </div>
    )
}
