import { useState } from "react";
import { Loader2, Wrench, ChevronDown, ChevronRight, CheckCircle2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Markdown } from "@/components/ui/markdown";

interface ToolInvocation {
    state: 'call' | 'result';
    toolCallId: string;
    toolName: string;
    args: any;
    result?: any;
}

interface ToolInvocationBlockProps {
    toolInvocations: ToolInvocation[];
}

export function ToolInvocationBlock({ toolInvocations }: ToolInvocationBlockProps) {
    if (!toolInvocations || toolInvocations.length === 0) return null;

    return (
        <div className="flex flex-col gap-2 my-2 w-full">
            {toolInvocations.map((invocation) => (
                <ToolInvocationItem key={invocation.toolCallId} invocation={invocation} />
            ))}
        </div>
    );
}

function ToolInvocationItem({ invocation }: { invocation: ToolInvocation }) {
    const [isExpanded, setIsExpanded] = useState(false);
    const isResult = invocation.state === 'result';

    // Format tool name for display
    const displayName = invocation.toolName.replace(/_/g, ' ');
    const capitalizedName = displayName.charAt(0).toUpperCase() + displayName.slice(1);

    if (!isResult) {
        return (
            <div className="flex items-center gap-3 px-4 py-2 bg-gray-50/50 rounded-xl border border-gray-100 animate-pulse">
                <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                <span className="text-sm font-medium text-gray-600">
                    {capitalizedName}...
                </span>
            </div>
        );
    }

    return (
        <div className="flex flex-col rounded-xl border border-gray-100 bg-white overflow-hidden shadow-sm hover:shadow-md transition-all duration-300">
            <div
                className="flex items-center justify-between px-4 py-2.5 bg-white cursor-pointer hover:bg-gray-50 transition-colors"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <div className="flex items-center gap-3">
                    <div className="flex items-center justify-center w-6 h-6 rounded-md bg-green-50 text-green-600">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                    </div>
                    <span className="text-sm font-semibold text-gray-800">
                        {capitalizedName}
                    </span>
                    <span className="text-[10px] text-gray-400 font-mono">
                        {invocation.toolCallId.slice(-6)}
                    </span>
                </div>
                {isExpanded ? <ChevronDown className="h-4 w-4 text-gray-400" /> : <ChevronRight className="h-4 w-4 text-gray-400" />}
            </div>

            {isExpanded && (
                <div className="px-4 pb-4 pt-1 border-t border-gray-50 bg-gray-50/20">
                    <div className="flex flex-col gap-3 mt-2">
                        {/* Args (Optional, but useful for context) */}
                        {invocation.args && Object.keys(invocation.args).length > 0 && (
                            <div className="flex flex-col gap-1">
                                <span className="text-[10px] uppercase tracking-wider text-gray-400 font-bold">Parameters</span>
                                <pre className="text-xs text-gray-600 bg-white p-2 rounded border border-gray-100 overflow-x-auto font-mono">
                                    {JSON.stringify(invocation.args, null, 2)}
                                </pre>
                            </div>
                        )}

                        {/* Result */}
                        <div className="flex flex-col gap-1">
                            <span className="text-[10px] uppercase tracking-wider text-gray-400 font-bold">Result</span>
                            <div className="bg-white p-3 rounded-lg border border-gray-100 shadow-inner">
                                {typeof invocation.result === 'string' ? (
                                    <Markdown className="prose prose-sm max-w-none text-gray-700">
                                        {invocation.result}
                                    </Markdown>
                                ) : (
                                    <pre className="text-xs text-gray-600 overflow-x-auto font-mono">
                                        {JSON.stringify(invocation.result, null, 2)}
                                    </pre>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
