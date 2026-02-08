"use client"

import { useMemo, useState } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Check, Copy } from "lucide-react"


import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface DataAnalystViewerProps {
    content: any
}

export function DataAnalystViewer({ content }: DataAnalystViewerProps) {
    const [activeTab, setActiveTab] = useState<"code" | "log">("code")
    const [copied, setCopied] = useState<"code" | "log" | null>(null)

    const input = content?.input ?? null
    const code = typeof content?.code === "string" ? content.code : ""
    const log = typeof content?.log === "string" ? content.log : ""
    const output = content?.output ?? null

    const artifactKeys: string[] = Array.isArray(input?.artifact_keys) ? input.artifact_keys : []
    const imageUrls: string[] = Array.isArray(input?.auto_task?.image_urls) ? input.auto_task.image_urls : []
    const outputFiles: any[] = Array.isArray(output?.output_files) ? output.output_files : []

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

    return (
        <div className="flex flex-col flex-1 min-h-0 bg-background">
            <ScrollArea className="flex-1 min-h-0 p-3">
                <div className="flex flex-col gap-4 pb-6">
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">インプット</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {!input?.instruction && imageUrls.length === 0 && artifactKeys.length === 0 ? (
                                <div className="text-muted-foreground text-xs italic">インプットデータがありません。</div>
                            ) : (
                                <>
                                    {input?.instruction && (
                                        <div>
                                            <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">実行指示</div>
                                            <div className="text-sm bg-muted/30 rounded-md p-3 border border-border">{input.instruction}</div>
                                        </div>
                                    )}

                                    {imageUrls.length > 0 && (
                                        <div>
                                            <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">画像インプット</div>
                                            <div className="grid grid-cols-2 gap-2">
                                                {imageUrls.map((url, idx) => (
                                                    <a
                                                        key={`img-${idx}`}
                                                        href={url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="relative group aspect-video rounded-md overflow-hidden border border-border hover:border-primary/50 transition-colors"
                                                    >
                                                        <img
                                                            src={url}
                                                            alt={`Input ${idx + 1}`}
                                                            className="h-full w-full object-cover transition-transform group-hover:scale-105"
                                                        />
                                                        <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                                                            <span className="text-white text-xs">クリックで拡大</span>
                                                        </div>
                                                    </a>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {artifactKeys.length > 0 && (
                                        <div>
                                            <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">使用アーティファクト</div>
                                            <div className="flex flex-wrap gap-1.5">
                                                {artifactKeys.map((key) => (
                                                    <span
                                                        key={key}
                                                        className="inline-flex items-center px-2 py-1 rounded-md bg-primary/10 text-primary border border-primary/20 text-xs font-mono"
                                                    >
                                                        {key}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </>
                            )}
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between gap-4">
                            <CardTitle className="text-sm">実装コード</CardTitle>
                            <div className="flex items-center gap-2">
                                <div className="inline-flex rounded-md border border-border overflow-hidden">
                                    <button
                                        type="button"
                                        onClick={() => setActiveTab("code")}
                                        className={cn(
                                            "px-3 py-1 text-xs font-medium border-r border-border",
                                            activeTab === "code" ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground"
                                        )}
                                    >
                                        Code
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => setActiveTab("log")}
                                        className={cn(
                                            "px-3 py-1 text-xs font-medium",
                                            activeTab === "log" ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground"
                                        )}
                                    >
                                        Log
                                    </button>
                                </div>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-7 px-2 text-xs"
                                    onClick={handleCopy}
                                    disabled={activeTab === "code" ? !code : !log}
                                >
                                    {copied === activeTab ? <Check className="h-3 w-3 mr-1" /> : <Copy className="h-3 w-3 mr-1" />}
                                    Copy
                                </Button>
                            </div>
                        </CardHeader>
                        <CardContent>
                            <div className="rounded-xl border border-border overflow-hidden">
                                <div className="flex items-center justify-between px-3 py-2 bg-muted/40 text-[10px] uppercase tracking-widest text-muted-foreground border-b border-border">
                                    <span>{activeTab === "code" ? "Python" : "Runtime Log"}</span>
                                    <span>{activeTab === "code" ? `${codeLines.length} lines` : `${logLines.length} lines`}</span>
                                </div>
                                {activeTab === "code" ? (
                                    <div className="bg-[#1e1e1e] p-0 overflow-x-auto relative group">
                                        <SyntaxHighlighter
                                            language="python"
                                            style={vscDarkPlus}
                                            showLineNumbers={true}
                                            customStyle={{ margin: 0, padding: '1rem', background: 'transparent' }}
                                            codeTagProps={{ style: { fontSize: '0.75rem', fontFamily: 'var(--font-mono)', lineHeight: '1.5' } }}
                                            lineNumberStyle={{ minWidth: '2.5em', paddingRight: '1em', color: 'rgba(255,255,255,0.3)', textAlign: 'right', fontSize: '10px' }}
                                        >
                                            {code || "コードがまだ出力されていません。"}
                                        </SyntaxHighlighter>
                                    </div>
                                ) : (
                                    <div className="grid grid-cols-[auto_1fr] font-mono text-xs bg-black/90 text-emerald-300">
                                        <div className="select-none text-[10px] text-white/30 px-3 py-2 border-r border-white/5 text-right">
                                            {logLines.map((_: string, idx: number) => (
                                                <div key={`ln-${idx}`}>{idx + 1}</div>
                                            ))}
                                        </div>
                                        <div className="px-3 py-2 whitespace-pre-wrap break-words">
                                            {log || "ログがまだ出力されていません。"}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">アウトプット</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {!output?.execution_summary && outputFiles.length === 0 ? (
                                <div className="text-muted-foreground text-xs italic">アウトプットはまだ生成されていません。</div>
                            ) : (
                                <>
                                    {output?.execution_summary && (
                                        <div>
                                            <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">実行結果</div>
                                            <div className="text-sm bg-muted/30 rounded-md p-3 border border-border">{output.execution_summary}</div>
                                        </div>
                                    )}

                                    {outputFiles.length > 0 && (
                                        <div>
                                            <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">生成ファイル</div>
                                            <div className="space-y-2">
                                                {outputFiles.map((file: any, index: number) => {
                                                    const url = file?.url || ""
                                                    const title = file?.title || `ファイル ${index + 1}`
                                                    const mimeType = file?.mime_type || ""
                                                    const isImage = mimeType.startsWith("image/") || /\.(png|jpg|jpeg|webp|gif)$/i.test(url)

                                                    if (isImage) {
                                                        return (
                                                            <a
                                                                key={`output-${index}`}
                                                                href={url}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                className="block group"
                                                            >
                                                                <div className="relative aspect-video rounded-md overflow-hidden border border-border hover:border-primary/50 transition-colors">
                                                                    <img
                                                                        src={url}
                                                                        alt={title}
                                                                        className="h-full w-full object-cover transition-transform group-hover:scale-105"
                                                                    />
                                                                    <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                                                                        <span className="text-white text-xs">クリックで拡大</span>
                                                                    </div>
                                                                </div>
                                                                {title && (
                                                                    <div className="text-xs text-muted-foreground mt-1 px-1">{title}</div>
                                                                )}
                                                            </a>
                                                        )
                                                    }

                                                    return (
                                                        <a
                                                            key={`output-${index}`}
                                                            href={url}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="flex items-center gap-3 p-3 rounded-md border border-border hover:border-primary/50 hover:bg-muted/30 transition-colors group"
                                                        >
                                                            <div className="flex-shrink-0 w-10 h-10 rounded-md bg-primary/10 flex items-center justify-center">
                                                                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                                                                </svg>
                                                            </div>
                                                            <div className="flex-1 min-w-0">
                                                                <div className="text-sm font-medium truncate group-hover:text-primary transition-colors">{title}</div>
                                                                {mimeType && (
                                                                    <div className="text-xs text-muted-foreground">{mimeType}</div>
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
            </ScrollArea>
        </div>
    )
}
