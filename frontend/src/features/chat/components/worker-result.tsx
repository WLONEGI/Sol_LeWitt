"use client"

import { CheckCircle2, Bot } from "lucide-react"

interface WorkerResultProps {
    role: string;
    summary: string;
    status: string;
}

export function WorkerResult({ role, summary, status }: WorkerResultProps) {
    const formatRole = (r: string) => {
        const normalized = r.toLowerCase();
        if (normalized === "writer") return "Writer";
        if (normalized === "researcher") return "Researcher";
        if (normalized === "visualizer") return "Visualizer";
        if (normalized === "data_analyst") return "Data Analyst";
        return r.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
    }

    return (
        <div className="flex gap-3 pl-4 pr-4 py-2 my-1 opacity-80 hover:opacity-100 transition-opacity group">
            <div className="flex flex-col gap-0.5 max-w-[90%]">
                <div className="flex items-center gap-2">
                    <div className="h-5 w-5 rounded-md bg-blue-500/10 flex items-center justify-center shrink-0 border border-blue-500/20">
                        <Bot className="h-3 w-3 text-blue-400" />
                    </div>
                    <span className="text-xs font-medium text-blue-300/80">{formatRole(role)}</span>
                    <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                        <CheckCircle2 className="h-3 w-3 text-green-500/50" />
                        <span className="text-muted-foreground/60">{status === 'completed' ? 'Completed' : status}</span>
                    </span>
                </div>
                <div className="text-xs text-muted-foreground pl-7 border-l-2 border-white/5 ml-2.5">
                    {summary}
                </div>
            </div>
        </div>
    )
}
