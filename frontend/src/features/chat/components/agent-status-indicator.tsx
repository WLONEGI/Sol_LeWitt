"use client"

import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"
import { Loader2, Bot, Brain, Sparkles, CheckCircle } from "lucide-react"

interface AgentStatus {
    stepId: string
    status: 'in_progress' | 'completed' | 'error'
    label: string
    details?: string
    agentName?: string
}

interface AgentStatusIndicatorProps {
    /** The latest status event from the stream */
    status: AgentStatus | null
    /** Whether any agent is currently active */
    isActive: boolean
    className?: string
}

const agentIcons: Record<string, React.ReactNode> = {
    coordinator: <Brain className="h-3.5 w-3.5" />,
    planner: <Sparkles className="h-3.5 w-3.5" />,
    supervisor: <Bot className="h-3.5 w-3.5" />,
    default: <Bot className="h-3.5 w-3.5" />,
}

/**
 * Displays the current agent activity status.
 * Shows a thinking/processing indicator with agent name and step description.
 */
export function AgentStatusIndicator({ status, isActive, className }: AgentStatusIndicatorProps) {
    const [visible, setVisible] = useState(false)

    useEffect(() => {
        if (status?.status === 'in_progress') {
            setVisible(true)
        } else if (status?.status === 'completed') {
            // Keep visible briefly then fade out
            const timer = setTimeout(() => setVisible(false), 1500)
            return () => clearTimeout(timer)
        }
    }, [status])

    if (!visible || !status) {
        return null
    }

    const agentKey = status.agentName?.toLowerCase() || 'default'
    const icon = agentIcons[agentKey] || agentIcons.default
    const isCompleted = status.status === 'completed'

    return (
        <div
            data-testid="agent-status-indicator"
            className={cn(
                "flex items-center gap-2.5 px-4 py-2.5 rounded-xl",
                "bg-gradient-to-r from-slate-50 to-slate-100/80",
                "border border-slate-200/60",
                "shadow-sm backdrop-blur-sm",
                "transition-all duration-500 ease-out",
                isCompleted && "opacity-60",
                className
            )}
        >
            {/* Status Icon */}
            <div className={cn(
                "flex items-center justify-center w-7 h-7 rounded-lg",
                isCompleted
                    ? "bg-green-100 text-green-600"
                    : "bg-indigo-100 text-indigo-600"
            )}>
                {isCompleted ? (
                    <CheckCircle className="h-4 w-4" />
                ) : (
                    <span className="animate-pulse">
                        {icon}
                    </span>
                )}
            </div>

            {/* Status Text */}
            <div className="flex flex-col min-w-0">
                <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-slate-700 truncate max-w-[200px]">
                        {status.label}
                    </span>
                    {!isCompleted && (
                        <Loader2 className="h-3 w-3 animate-spin text-slate-400 shrink-0" />
                    )}
                </div>
                {status.details && (
                    <span className="text-xs text-slate-500 truncate max-w-[280px]">
                        {status.details}
                    </span>
                )}
            </div>
        </div>
    )
}
