"use client"

import { useState } from "react";
import { Loader2, CheckCircle2, XCircle, Terminal, ChevronDown, ChevronRight, Play } from "lucide-react";
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { cn } from "@/lib/utils";

interface CodeExecutionBlockProps {
    code: string;
    language?: string;
    status: 'running' | 'completed' | 'failed';
    result?: string;
    toolCallId?: string;
}

export function CodeExecutionBlock({
    code,
    language = "python",
    status,
    result,
    toolCallId
}: CodeExecutionBlockProps) {
    const [isExpanded, setIsExpanded] = useState(true);

    const isRunning = status === 'running';
    const isFailed = status === 'failed';

    return (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden my-4 shadow-sm group hover:shadow-md transition-all duration-300">
            {/* Header */}
            <div
                className="flex items-center justify-between px-4 py-3 bg-gray-50/50 cursor-pointer hover:bg-gray-50 transition-colors border-b border-gray-100"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <div className="flex items-center gap-3">
                    <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gray-100 border border-gray-200 text-gray-600">
                        <Terminal className="h-4 w-4" />
                    </div>
                    <div className="flex flex-col">
                        <span className="text-sm font-semibold text-gray-900">Code Execution</span>
                        <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-xs text-gray-500 font-mono bg-white px-1.5 py-0.5 rounded border border-gray-100">
                                {language}
                            </span>
                            <div className={cn(
                                "flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider",
                                isRunning ? "text-blue-500" :
                                    isFailed ? "text-red-500" :
                                        "text-green-600"
                            )}>
                                {isRunning ? (
                                    <>Running...</>
                                ) : isFailed ? (
                                    <>Failed</>
                                ) : (
                                    <>Executed</>
                                )}
                            </div>
                        </div>
                    </div>
                </div>

                {isExpanded ? <ChevronDown className="h-4 w-4 text-gray-400" /> : <ChevronRight className="h-4 w-4 text-gray-400" />}
            </div>

            {/* Content */}
            {isExpanded && (
                <div>
                    {/* Code Section */}
                    <div className="bg-[#1e1e1e] p-0 overflow-x-auto relative group">
                        <SyntaxHighlighter
                            language={language}
                            style={vscDarkPlus}
                            customStyle={{ margin: 0, padding: '1.5rem', background: 'transparent' }}
                            codeTagProps={{ style: { fontSize: '0.85rem', fontFamily: 'var(--font-mono)', lineHeight: '1.5' } }}
                        >
                            {code}
                        </SyntaxHighlighter>
                    </div>

                    {/* Result Section */}
                    {result && (
                        <div className="bg-gray-50 border-t border-gray-100 p-4 text-xs font-mono whitespace-pre-wrap max-h-60 overflow-y-auto text-gray-700 leading-relaxed">
                            <div className="flex items-center gap-2 text-[10px] text-gray-400 mb-2 uppercase tracking-widest font-bold">
                                Output
                            </div>
                            <div className="pl-0 break-all">
                                {result}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
