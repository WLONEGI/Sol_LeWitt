"use client"

import { useMemo, useState } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Markdown } from "@/components/ui/markdown"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Check, Copy } from "lucide-react"

import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface DataAnalystViewerProps {
    content: any
    status?: string
}

export function DataAnalystViewer({ content, status }: DataAnalystViewerProps) {
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
            <ScrollArea className="flex-1 min-h-0 p-6">
                <div className="flex flex-col gap-6 pb-12">
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">インプット情報</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-3 text-sm">
                            {input?.instruction ? (
                                <div>
                                    <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Instruction</div>
                                    <div className="whitespace-pre-wrap">{input.instruction}</div>
                                </div>
                            ) : (
                                <div className="text-muted-foreground text-xs">インプット情報がまだありません。</div>
                            )}

                            {artifactKeys.length > 0 && (
                                <div>
                                    <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Artifacts</div>
                                    <ul className="list-disc pl-5 space-y-1">
                                        {artifactKeys.map((key) => (
                                            <li key={key} className="break-all">{key}</li>
                                        ))}
                                    </ul>
                                </div>
                            )}

                            {input?.output_prefix && (
                                <div>
                                    <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Output Prefix</div>
                                    <div className="font-mono text-xs break-all">{input.output_prefix}</div>
                                </div>
                            )}

                            {imageUrls.length > 0 && (
                                <div>
                                    <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Visualizer Inputs</div>
                                    <div className="text-xs">{imageUrls.length}件の画像URLを検出しました。</div>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between gap-4">
                            <CardTitle className="text-sm">実装コード</CardTitle>
                            <div className="flex items-center gap-2">
                                {status === "streaming" && (
                                    <span className="text-[10px] uppercase tracking-widest text-emerald-600 font-semibold">
                                        Streaming
                                    </span>
                                )}
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
                        <CardContent className="space-y-4 text-sm">
                            {output?.execution_summary ? (
                                <div>
                                    <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Summary</div>
                                    <div className="whitespace-pre-wrap">{output.execution_summary}</div>
                                </div>
                            ) : (
                                <div className="text-muted-foreground text-xs">アウトプットはまだ作成されていません。</div>
                            )}

                            {outputFiles.length > 0 && (
                                <div>
                                    <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Files</div>
                                    <ul className="list-disc pl-5 space-y-1">
                                        {outputFiles.map((file: any, index: number) => (
                                            <li key={`${file?.url || "file"}-${index}`} className="text-xs break-all">
                                                {file?.title || file?.url || "Untitled"}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}

                            {output?.analysis_report && (
                                <div>
                                    <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Report</div>
                                    <div className="prose dark:prose-invert max-w-none text-sm">
                                        <Markdown>{output.analysis_report}</Markdown>
                                    </div>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>
            </ScrollArea>
        </div>
    )
}
