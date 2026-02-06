"use client"

import * as React from "react"
import TextareaAutosize from "react-textarea-autosize"
import { ArrowUp, Paperclip, Plus, X, type LucideIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
} from "@/components/ui/tooltip"

interface ChatInputProps {
    onSend: (value: string) => void;
    isLoading?: boolean;
    disabledReason?: string | null;
    className?: string;
    placeholder?: string;
    onFileSelect?: (file: File) => void;
    selectedFile?: File | null;
    onClearFile?: () => void;
    showAttachments?: boolean;
    actionPill?: {
        label: string;
        icon: LucideIcon;
    };
    onClearAction?: () => void;
}

export function ChatInput({
    onSend,
    isLoading,
    disabledReason,
    className,
    placeholder = "Send message to Spell",
    value,
    onChange,
    onFileSelect,
    selectedFile,
    onClearFile,
    showAttachments = true,
    actionPill,
    onClearAction,
}: ChatInputProps & {
    value?: string;
    onChange?: (e: React.ChangeEvent<HTMLTextAreaElement>) => void
}) {
    const [internalInput, setInternalInput] = React.useState("")
    const fileInputRef = React.useRef<HTMLInputElement>(null)
    const ActionIcon = actionPill?.icon

    const inputValue = value !== undefined ? value : internalInput;

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            if (inputValue.trim() && !isLoading) {
                onSend(inputValue)
                if (value === undefined) setInternalInput("")
            }
        }
    }

    const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        if (onChange) onChange(e);
        else setInternalInput(e.target.value);
    }

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (file && onFileSelect) {
            onFileSelect(file)
        }
    }

    return (
        <div className={cn("relative flex flex-col gap-2 transition-all duration-300", className)}>

            {/* Selected File Preview - Floats above input */}
            {showAttachments && selectedFile && (
                <div className="absolute -top-12 left-0 flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-200 rounded-full w-fit text-xs animate-in slide-in-from-bottom-2">
                    <Paperclip className="h-3 w-3 text-primary" />
                    <span className="max-w-[200px] truncate">{selectedFile.name}</span>
                    <button onClick={onClearFile} className="ml-1 hover:text-destructive transition-colors">
                        <X className="h-3 w-3" />
                    </button>
                </div>
            )}

            <div className="relative flex flex-col bg-white border border-gray-200 rounded-[28px] p-2 px-4 transition-all focus-within:border-gray-300 focus-within:ring-0 shadow-sm">
                {showAttachments && (
                    <input
                        type="file"
                        className="hidden"
                        ref={fileInputRef}
                        accept=".pptx,.pdf,.txt"
                        onChange={handleFileChange}
                    />
                )}

                {/* Row 1: Textarea */}
                <div className="relative w-full">
                    <TextareaAutosize
                        minRows={1}
                        maxRows={5}
                        value={inputValue}
                        onChange={handleChange}
                        onKeyDown={handleKeyDown}
                        placeholder={placeholder}
                        disabled={isLoading}
                        className="flex w-full resize-none bg-transparent px-2 py-3 text-base placeholder:text-muted-foreground focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 font-sans font-medium"
                    />
                </div>

                {/* Row 2: Toolbar */}
                <div className="flex items-center justify-between gap-3 pb-1">
                    <div className="flex items-center gap-2">
                        {/* Left: Attachment */}
                        {showAttachments ? (
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-9 w-9 shrink-0 text-gray-500 hover:text-primary rounded-full hover:bg-gray-100 transition-colors"
                                        onClick={() => fileInputRef.current?.click()}
                                        disabled={isLoading}
                                    >
                                        <Plus className="h-5 w-5" />
                                    </Button>
                                </TooltipTrigger>
                                <TooltipContent side="top">Attach template or data</TooltipContent>
                            </Tooltip>
                        ) : null}

                        {actionPill && ActionIcon ? (
                            <div className="group inline-flex items-center gap-2 rounded-full border border-blue-200/80 bg-blue-50/70 px-3 py-1 text-sm font-semibold text-blue-600 shadow-sm">
                                {onClearAction ? (
                                    <button
                                        type="button"
                                        onClick={onClearAction}
                                        className="relative h-4 w-4 text-blue-600 transition hover:text-blue-700"
                                        aria-label="Clear action"
                                    >
                                        <ActionIcon className="absolute inset-0 h-4 w-4 opacity-100 transition group-hover:opacity-0" />
                                        <X className="absolute inset-0 h-4 w-4 opacity-0 transition group-hover:opacity-100" />
                                    </button>
                                ) : (
                                    <ActionIcon className="h-4 w-4" />
                                )}
                                <span>{actionPill.label}</span>
                            </div>
                        ) : null}
                    </div>

                    {/* Right: Send Button */}
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Button
                                onClick={() => {
                                    if (inputValue.trim() && !isLoading) {
                                        onSend(inputValue)
                                        if (value === undefined) setInternalInput("")
                                    }
                                }}
                                disabled={!inputValue.trim() || isLoading}
                                size="icon"
                                className={cn(
                                    "h-9 w-9 shrink-0 rounded-full transition-all duration-300",
                                    inputValue.trim() && !isLoading
                                        ? "bg-primary text-primary-foreground hover:opacity-90 active:scale-95"
                                        : "bg-gray-100 text-gray-400"
                                )}
                            >
                                <ArrowUp className="h-5 w-5" />
                                <span className="sr-only">Send</span>
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent side="top">Send message</TooltipContent>
                    </Tooltip>
                </div>
            </div>
            {disabledReason ? (
                <p className="px-3 text-xs text-muted-foreground" aria-live="polite">
                    {disabledReason}
                </p>
            ) : null}

        </div>
    )
}
