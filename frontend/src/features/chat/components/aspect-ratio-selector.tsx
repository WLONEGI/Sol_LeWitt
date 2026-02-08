"use client"

import * as React from "react"
import {
    Square,
    RectangleHorizontal,
    RectangleVertical,
    Smartphone,
    Monitor,
    LayoutTemplate,
    Check,
    Sparkles,
    ChevronUp
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

export type AspectRatio = "16:9" | "4:3" | "1:1" | "3:4" | "9:16" | "21:9" | undefined

interface AspectRatioOption {
    value: AspectRatio
    label: string
    description: string
    icon: React.ElementType
}

const OPTIONS: AspectRatioOption[] = [
    {
        value: undefined,
        label: "Auto",
        description: "AI chooses the best ratio for you",
        icon: Sparkles
    },
    {
        value: "16:9",
        label: "16:9",
        description: "Presentations & modern screens",
        icon: RectangleHorizontal
    },
    {
        value: "4:3",
        label: "4:3",
        description: "Knowledge cards & classic slides",
        icon: LayoutTemplate
    },
    {
        value: "1:1",
        label: "1:1",
        description: "Social posts & online ads",
        icon: Square
    },
    {
        value: "3:4",
        label: "3:4",
        description: "Posters & print-ready layouts",
        icon: RectangleVertical
    },
    {
        value: "9:16",
        label: "9:16",
        description: "Mobile stories & vertical videos",
        icon: Smartphone
    },
    {
        value: "21:9",
        label: "21:9",
        description: "Stage events & LED walls",
        icon: Monitor
    },
]

interface AspectRatioSelectorProps {
    value: AspectRatio
    onChange: (value: AspectRatio) => void
    disabled?: boolean
}

export function AspectRatioSelector({ value, onChange, disabled }: AspectRatioSelectorProps) {
    const [isOpen, setIsOpen] = React.useState(false)
    const containerRef = React.useRef<HTMLDivElement>(null)

    const selectedOption = OPTIONS.find(opt => opt.value === value) || OPTIONS[0]

    React.useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
                setIsOpen(false)
            }
        }
        if (isOpen) {
            document.addEventListener('mousedown', handleClickOutside)
        }
        return () => {
            document.removeEventListener('mousedown', handleClickOutside)
        }
    }, [isOpen])

    return (
        <div className="relative" ref={containerRef}>
            <Button
                variant="ghost"
                size={null}
                className={cn(
                    "flex items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold border transition-all shadow-sm",
                    // Default / Auto
                    value === undefined
                        ? "border-transparent text-gray-500 hover:bg-gray-100 hover:text-gray-900 hover:border-gray-200"
                        : "border-blue-200/80 bg-blue-50/70 text-blue-600 hover:bg-blue-100/80",
                    isOpen && value === undefined && "bg-gray-100 text-gray-900 border-gray-200",
                )}
                onClick={() => setIsOpen(!isOpen)}
                disabled={disabled}
                title="Aspect Ratio"
            >
                <selectedOption.icon className="h-4 w-4" />
                <span>{selectedOption.label}</span>
            </Button>

            {isOpen && (
                <div className="absolute top-full left-0 mt-2 w-64 rounded-xl border border-gray-200 bg-white p-1 shadow-lg animate-in fade-in zoom-in-95 duration-200 z-50">
                    <div className="flex flex-col gap-0.5">
                        {OPTIONS.map((option) => (
                            <button
                                key={option.label}
                                className={cn(
                                    "flex items-start gap-3 w-full rounded-lg px-3 py-2 text-left hover:bg-gray-50 transition-colors",
                                    option.value === value && "bg-primary/5 hover:bg-primary/10"
                                )}
                                onClick={() => {
                                    onChange(option.value)
                                    setIsOpen(false)
                                }}
                            >
                                <option.icon className={cn(
                                    "h-4 w-4 mt-0.5 shrink-0",
                                    option.value === value ? "text-primary" : "text-gray-500"
                                )} />
                                <div className="flex-1 min-w-0">
                                    <div className={cn(
                                        "text-sm font-medium",
                                        option.value === value ? "text-primary" : "text-gray-900"
                                    )}>
                                        {option.label}
                                    </div>
                                    <div className="text-xs text-gray-500 truncate">
                                        {option.description}
                                    </div>
                                </div>
                                {option.value === value && (
                                    <Check className="h-4 w-4 text-primary shrink-0" />
                                )}
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}
