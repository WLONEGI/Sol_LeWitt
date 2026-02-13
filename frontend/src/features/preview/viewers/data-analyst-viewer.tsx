"use client"

import { useMemo, useState } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Check, Copy, FileArchive, FileImage, FileSpreadsheet, FileText } from "lucide-react"


import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface DataAnalystViewerProps {
    content: any
    embedded?: boolean
}

type ViewerFileEntry = {
    url: string
    title: string
    mimeType: string
    isImage: boolean
}

const IMAGE_EXT_PATTERN = /\.(png|jpg|jpeg|webp|gif|svg)$/i
const FILE_NAME_FROM_URL = /\/([^/?#]+)(?:[?#].*)?$/

const inferMimeType = (url: string, rawMimeType?: string): string => {
    if (typeof rawMimeType === "string" && rawMimeType.trim().length > 0) {
        return rawMimeType.trim()
    }
    const lowered = url.toLowerCase()
    if (lowered.endsWith(".pptx")) return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if (lowered.endsWith(".pdf")) return "application/pdf"
    if (lowered.endsWith(".zip")) return "application/zip"
    if (lowered.endsWith(".csv")) return "text/csv"
    if (lowered.endsWith(".json")) return "application/json"
    if (lowered.endsWith(".xlsx") || lowered.endsWith(".xls")) return "application/vnd.ms-excel"
    if (IMAGE_EXT_PATTERN.test(lowered)) return "image/*"
    return "application/octet-stream"
}

const defaultTitleFromUrl = (url: string): string => {
    const match = FILE_NAME_FROM_URL.exec(url)
    if (match && match[1]) return decodeURIComponent(match[1])
    return "ファイル"
}

const normalizeFileEntry = (raw: any): ViewerFileEntry | null => {
    const url = typeof raw?.url === "string" ? raw.url.trim() : ""
    if (!url) return null
    const mimeType = inferMimeType(url, typeof raw?.mime_type === "string" ? raw.mime_type : undefined)
    const title =
        typeof raw?.title === "string" && raw.title.trim().length > 0
            ? raw.title.trim()
            : defaultTitleFromUrl(url)
    return {
        url,
        title,
        mimeType,
        isImage: mimeType.startsWith("image/") || IMAGE_EXT_PATTERN.test(url),
    }
}

export function DataAnalystViewer({ content, embedded = false }: DataAnalystViewerProps) {
    const [activeTab, setActiveTab] = useState<"code" | "log">("code")
    const [copied, setCopied] = useState<"code" | "log" | null>(null)

    const input = content?.input ?? null
    const output = content?.output ?? null
    const code = useMemo(() => {
        if (typeof content?.code === "string" && content.code.trim().length > 0) return content.code
        if (typeof output?.implementation_code === "string") return output.implementation_code
        return ""
    }, [content?.code, output?.implementation_code])
    const log = useMemo(() => {
        if (typeof content?.log === "string" && content.log.trim().length > 0) return content.log
        if (typeof output?.execution_log === "string") return output.execution_log
        return ""
    }, [content?.log, output?.execution_log])

    const failedChecks: string[] = Array.isArray(output?.failed_checks) ? output.failed_checks : []
    const inputFiles = useMemo(() => {
        const dedup = new Map<string, ViewerFileEntry>()

        const manifest = Array.isArray(input?.local_file_manifest) ? input.local_file_manifest : []
        manifest.forEach((row: any) => {
            const entry = normalizeFileEntry({
                url: row?.source_url,
                title: defaultTitleFromUrl(String(row?.source_url || "")),
                mime_type: undefined,
            })
            if (entry && !dedup.has(entry.url)) dedup.set(entry.url, entry)
        })

        const selectedImageInputs = Array.isArray(input?.selected_image_inputs) ? input.selected_image_inputs : []
        selectedImageInputs.forEach((row: any, index: number) => {
            const url = typeof row?.image_url === "string" ? row.image_url : ""
            const entry = normalizeFileEntry({
                url,
                title: typeof row?.caption === "string" && row.caption.trim().length > 0
                    ? row.caption
                    : `入力画像 ${index + 1}`,
                mime_type: "image/*",
            })
            if (entry && !dedup.has(entry.url)) dedup.set(entry.url, entry)
        })

        const attachments = Array.isArray(input?.attachments) ? input.attachments : []
        attachments.forEach((row: any) => {
            const entry = normalizeFileEntry({
                url: row?.url,
                title: row?.filename,
                mime_type: row?.mime_type,
            })
            if (entry && !dedup.has(entry.url)) dedup.set(entry.url, entry)
        })

        return Array.from(dedup.values())
    }, [input?.attachments, input?.local_file_manifest, input?.selected_image_inputs])

    const outputFiles = useMemo(() => {
        const rows = Array.isArray(output?.output_files) ? output.output_files : []
        const normalized = rows
            .map((row: any) => normalizeFileEntry(row))
            .filter((row: ViewerFileEntry | null): row is ViewerFileEntry => Boolean(row))
        return normalized.filter((row: ViewerFileEntry) => !row.isImage)
    }, [output?.output_files])

    const codeLines = useMemo(() => code.split("\n"), [code])
    const logLines = useMemo(() => log.split("\n"), [log])

    const handleCopy = async () => {
        const text = activeTab === "code" ? code : log
        if (!text) return
        try {
            await navigator.clipboard.writeText(text)
            setCopied(activeTab)
            window.setTimeout(() => setCopied(null), 1600)
        } catch {
            // noop
        }
    }

    const viewerContent = (
        <div className={cn("flex flex-col min-w-0", embedded ? "gap-2 pb-0" : "gap-4 pb-6")}>
                    <Card className={cn("min-w-0", embedded && "rounded-lg")}>
                        <CardHeader className={cn(embedded && "px-3 py-2")}>
                            <CardTitle className={cn("text-sm", embedded && "text-xs")}>インプット</CardTitle>
                        </CardHeader>
                        <CardContent className={cn(embedded ? "space-y-2 px-3 pb-3 pt-0" : "space-y-4")}>
                            {inputFiles.length === 0 ? (
                                <div className={cn("text-muted-foreground italic", embedded ? "text-[11px]" : "text-xs")}>インプットファイルがありません。</div>
                            ) : (
                                <div className={cn(embedded ? "space-y-1.5" : "space-y-2")}>
                                    {inputFiles.map((file, index) => {
                                        const isPdf = file.mimeType.includes("pdf")
                                        const isPptx =
                                            file.mimeType.includes("presentationml")
                                            || file.url.toLowerCase().endsWith(".pptx")
                                        const isZip = file.mimeType.includes("zip")
                                        const isSheet = file.mimeType.includes("csv") || file.mimeType.includes("excel")
                                        const Icon = file.isImage
                                            ? FileImage
                                            : isZip
                                                ? FileArchive
                                                : isSheet
                                                    ? FileSpreadsheet
                                                    : (isPptx || isPdf ? FileText : FileText)

                                        return (
                                            <a
                                                key={`input-${index}`}
                                                href={file.url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className={cn(
                                                    "flex items-center rounded-md border border-border hover:border-primary/50 hover:bg-muted/30 transition-colors group",
                                                    embedded ? "gap-2 p-2" : "gap-3 p-3"
                                                )}
                                            >
                                                <div className={cn(
                                                    "flex-shrink-0 rounded-md bg-primary/10 border border-primary/15 overflow-hidden flex items-center justify-center",
                                                    embedded ? "w-8 h-8" : "w-10 h-10"
                                                )}>
                                                    {file.isImage ? (
                                                        <img
                                                            src={file.url}
                                                            alt={file.title}
                                                            className="h-full w-full object-cover"
                                                        />
                                                    ) : (
                                                        <Icon className={cn("text-primary", embedded ? "h-4 w-4" : "h-5 w-5")} />
                                                    )}
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <div className={cn("font-medium truncate group-hover:text-primary transition-colors", embedded ? "text-xs" : "text-sm")}>
                                                        {file.title}
                                                    </div>
                                                    <div className={cn("text-muted-foreground truncate", embedded ? "text-[11px]" : "text-xs")}>
                                                        {file.mimeType}
                                                    </div>
                                                </div>
                                            </a>
                                        )
                                    })}
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    <Card className={cn("min-w-0", embedded && "rounded-lg")}>
                        <CardHeader className={cn("flex flex-wrap items-center justify-between", embedded ? "gap-2 px-3 py-2" : "gap-3")}>
                            <CardTitle className={cn("text-sm", embedded && "text-xs")}>実装コード</CardTitle>
                            <div className={cn("flex flex-wrap items-center min-w-0", embedded ? "gap-1.5" : "gap-2")}>
                                <div className="inline-flex rounded-md border border-border overflow-hidden">
                                    <button
                                        type="button"
                                        onClick={() => setActiveTab("code")}
                                        className={cn(
                                            embedded ? "px-2.5 py-0.5 text-[11px] font-medium border-r border-border" : "px-3 py-1 text-xs font-medium border-r border-border",
                                            activeTab === "code" ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground"
                                        )}
                                    >
                                        Code
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => setActiveTab("log")}
                                        className={cn(
                                            embedded ? "px-2.5 py-0.5 text-[11px] font-medium" : "px-3 py-1 text-xs font-medium",
                                            activeTab === "log" ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground"
                                        )}
                                    >
                                        Log
                                    </button>
                                </div>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className={cn(embedded ? "h-6 px-2 text-[11px]" : "h-7 px-2 text-xs")}
                                    onClick={handleCopy}
                                    disabled={activeTab === "code" ? !code : !log}
                                >
                                    {copied === activeTab ? <Check className="h-3 w-3 mr-1" /> : <Copy className="h-3 w-3 mr-1" />}
                                    Copy
                                </Button>
                            </div>
                        </CardHeader>
                        <CardContent className={cn("min-w-0", embedded && "px-3 pb-3 pt-0")}>
                            <div className="rounded-xl border border-border overflow-hidden min-w-0">
                                <div className={cn(
                                    "flex items-center justify-between bg-muted/40 text-[10px] uppercase tracking-widest text-muted-foreground border-b border-border",
                                    embedded ? "px-2.5 py-1.5" : "px-3 py-2"
                                )}>
                                    <span>{activeTab === "code" ? "Python" : "Runtime Log"}</span>
                                    <span>{activeTab === "code" ? `${codeLines.length} lines` : `${logLines.length} lines`}</span>
                                </div>
                                {activeTab === "code" ? (
                                    <div className="bg-[#1e1e1e] p-0 overflow-x-auto relative group max-w-full">
                                        <SyntaxHighlighter
                                            language="python"
                                            style={vscDarkPlus}
                                            showLineNumbers={true}
                                            wrapLongLines={true}
                                            customStyle={{ margin: 0, padding: embedded ? '0.75rem' : '1rem', background: 'transparent' }}
                                            codeTagProps={{
                                                style: {
                                                    fontSize: embedded ? '0.6875rem' : '0.75rem',
                                                    fontFamily: 'var(--font-mono)',
                                                    lineHeight: embedded ? '1.4' : '1.5',
                                                    wordBreak: 'break-word',
                                                }
                                            }}
                                            lineNumberStyle={{
                                                minWidth: embedded ? '2.1em' : '2.5em',
                                                paddingRight: embedded ? '0.75em' : '1em',
                                                color: 'rgba(255,255,255,0.3)',
                                                textAlign: 'right',
                                                fontSize: embedded ? '9px' : '10px'
                                            }}
                                        >
                                            {code || "コードがまだ出力されていません。"}
                                        </SyntaxHighlighter>
                                    </div>
                                ) : (
                                    <div className="grid w-full min-w-0 grid-cols-[auto_minmax(0,1fr)] font-mono text-xs bg-black/90 text-emerald-300">
                                        <div className={cn(
                                            "select-none text-[10px] text-white/30 border-r border-white/5 text-right",
                                            embedded ? "px-2 py-1.5" : "px-3 py-2"
                                        )}>
                                            {logLines.map((_: string, idx: number) => (
                                                <div key={`ln-${idx}`}>{idx + 1}</div>
                                            ))}
                                        </div>
                                        <div className={cn(
                                            "min-w-0 whitespace-pre-wrap break-all [overflow-wrap:anywhere]",
                                            embedded ? "px-2 py-1.5 text-[11px]" : "px-3 py-2"
                                        )}>
                                            {log || "ログがまだ出力されていません。"}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </CardContent>
                    </Card>

                    <Card className={cn("min-w-0", embedded && "rounded-lg")}>
                        <CardHeader className={cn(embedded && "px-3 py-2")}>
                            <CardTitle className={cn("text-sm", embedded && "text-xs")}>アウトプット</CardTitle>
                        </CardHeader>
                        <CardContent className={cn(embedded ? "space-y-2 px-3 pb-3 pt-0" : "space-y-4")}>
                            {outputFiles.length === 0 && failedChecks.length === 0 ? (
                                <div className={cn("text-muted-foreground italic", embedded ? "text-[11px]" : "text-xs")}>アウトプットはまだ生成されていません。</div>
                            ) : (
                                <>
                                    {failedChecks.length > 0 && (
                                        <div>
                                            <div className={cn("text-muted-foreground uppercase tracking-wider mb-2", embedded ? "text-[11px]" : "text-xs")}>Failed Checks</div>
                                            <div className="flex flex-wrap gap-1.5">
                                                {failedChecks.map((check) => (
                                                    <span
                                                        key={check}
                                                        className={cn(
                                                            "inline-flex items-center rounded-md bg-destructive/10 text-destructive border border-destructive/20 font-mono",
                                                            embedded ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs"
                                                        )}
                                                    >
                                                        {check}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {outputFiles.length > 0 && (
                                        <div>
                                            <div className={cn(embedded ? "space-y-1.5" : "space-y-2")}>
                                                {outputFiles.map((file: ViewerFileEntry, index: number) => {
                                                    const isZip = file.mimeType.includes("zip")
                                                    const isSheet = file.mimeType.includes("csv") || file.mimeType.includes("excel")
                                                    const Icon = isZip ? FileArchive : isSheet ? FileSpreadsheet : FileText
                                                    return (
                                                        <a
                                                            key={`output-${index}`}
                                                            href={file.url}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className={cn(
                                                                "flex items-center rounded-md border border-border hover:border-primary/50 hover:bg-muted/30 transition-colors group",
                                                                embedded ? "gap-2 p-2" : "gap-3 p-3"
                                                            )}
                                                        >
                                                            <div className={cn(
                                                                "flex-shrink-0 rounded-md bg-primary/10 flex items-center justify-center",
                                                                embedded ? "w-8 h-8" : "w-10 h-10"
                                                            )}>
                                                                <Icon className={cn("text-primary", embedded ? "h-4 w-4" : "h-5 w-5")} />
                                                            </div>
                                                            <div className="flex-1 min-w-0">
                                                                <div className={cn("font-medium truncate group-hover:text-primary transition-colors", embedded ? "text-xs" : "text-sm")}>
                                                                    {file.title}
                                                                </div>
                                                                {file.mimeType && (
                                                                    <div className={cn("text-muted-foreground", embedded ? "text-[11px]" : "text-xs")}>{file.mimeType}</div>
                                                                )}
                                                            </div>
                                                            <div className="flex-shrink-0">
                                                                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                                                </svg>
                                                            </div>
                                                        </a>
                                                    )
                                                })}
                                            </div>
                                        </div>
                                    )}
                                </>
                            )}
                        </CardContent>
                    </Card>
        </div>
    )

    if (embedded) {
        return <div className="min-w-0">{viewerContent}</div>
    }

    return (
        <div className="flex flex-col flex-1 min-h-0 min-w-0 bg-background overflow-hidden">
            <ScrollArea className="flex-1 min-h-0 min-w-0 p-3">
                {viewerContent}
            </ScrollArea>
        </div>
    )
}
