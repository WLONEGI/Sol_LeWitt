"use client"

import * as React from "react"
import TextareaAutosize from "react-textarea-autosize"
import { ArrowUp, Paperclip, Square, X, type LucideIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
} from "@/components/ui/tooltip"
import { AspectRatioSelector, AspectRatio } from "./aspect-ratio-selector"

interface ChatInputProps {
    onSend: (value: string) => void;
    onStop?: () => void;
    isLoading?: boolean;
    isProcessing?: boolean;
    allowSendWhileLoading?: boolean;
    disabledReason?: string | null;
    className?: string;
    placeholder?: string;
    onFilesSelect?: (files: File[]) => void;
    selectedFiles?: File[];
    onRemoveFile?: (index: number) => void;
    showAttachments?: boolean;
    actionPill?: {
        label: string;
        icon: LucideIcon;
        className?: string;
    };
    onClearAction?: () => void;
    aspectRatio?: AspectRatio;
    onAspectRatioChange?: (value: AspectRatio) => void;
}

export function ChatInput({
    onSend,
    onStop,
    isLoading,
    isProcessing = false,
    allowSendWhileLoading = false,
    className,
    placeholder = "Send message to Sol LeWitt",
    value,
    onChange,
    onFilesSelect,
    selectedFiles = [],
    onRemoveFile,
    showAttachments = true,
    actionPill,
    onClearAction,
    aspectRatio,
    onAspectRatioChange,
}: ChatInputProps & {
    value?: string;
    onChange?: (e: React.ChangeEvent<HTMLTextAreaElement>) => void
}) {
    const [internalInput, setInternalInput] = React.useState("")
    const fileInputRef = React.useRef<HTMLInputElement>(null)
    const ActionIcon = actionPill?.icon
    const inputLocked = Boolean(isLoading && !allowSendWhileLoading)
    const showStopButton = Boolean(isProcessing)

    const inputValue = value !== undefined ? value : internalInput;

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            if (inputValue.trim() && !inputLocked) {
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
        const files = Array.from(e.target.files || [])
        if (files.length > 0 && onFilesSelect) {
            onFilesSelect(files)
        }
        e.currentTarget.value = ""
    }

    return (
        <div className={cn("relative flex flex-col gap-2 transition-all duration-300", className)}>

            {showAttachments && selectedFiles.length > 0 && (
                <div className="flex flex-wrap items-center gap-2 px-1">
                    {selectedFiles.map((file, index) => (
                        <div
                            key={`${file.name}-${file.size}-${file.lastModified}-${index}`}
                            className="flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-200 rounded-full text-xs animate-in slide-in-from-bottom-2"
                        >
                            <Paperclip className="h-3 w-3 text-primary" />
                            <span className="max-w-[180px] truncate">{file.name}</span>
                            <button
                                type="button"
                                onClick={() => onRemoveFile?.(index)}
                                className="ml-1 hover:text-destructive transition-colors"
                            >
                                <X className="h-3 w-3" />
                            </button>
                        </div>
                    ))}
                </div>
            )}

            <div className="relative flex flex-col bg-white border border-gray-200 rounded-[28px] p-2 px-4 transition-all focus-within:border-gray-300 focus-within:ring-0 shadow-sm">
                {showAttachments && (
                    <input
                        type="file"
                        className="hidden"
                        ref={fileInputRef}
                        multiple
                        accept=".pptx,.pdf,.csv,.txt,.md,.json,image/png,image/jpeg,image/webp"
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
                        disabled={inputLocked}
                        className="flex w-full resize-none bg-transparent px-2 py-3 text-base placeholder:text-muted-foreground focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 font-sans font-medium"
                    />
                </div>

                {/* Row 2: Toolbar */}
                <div className="flex items-center justify-between gap-3 pb-1">
                    <div className="flex items-center gap-2">
                        {/* Left: Attachment */}
                        <div className="flex items-center gap-1">
                            {showAttachments ? (
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-9 w-9 shrink-0 text-gray-500 hover:text-primary rounded-full hover:bg-gray-100 transition-colors"
                                            onClick={() => fileInputRef.current?.click()}
                                            disabled={inputLocked}
                                            aria-label="Attach file"
                                        >
                                            <Paperclip className="h-5 w-5" />
                                        </Button>
                                    </TooltipTrigger>
                                    <TooltipContent side="top">Attach template or data</TooltipContent>
                                </Tooltip>
                            ) : null}

                            {onAspectRatioChange && (
                                <AspectRatioSelector
                                    value={aspectRatio}
                                    onChange={onAspectRatioChange}
                                    disabled={inputLocked}
                                />
                            )}
                        </div>

                        {actionPill && ActionIcon ? (
                            <div className={cn(
                                "group inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm font-semibold shadow-sm",
                                actionPill.className || "border-blue-200/80 bg-blue-50/70 text-blue-600"
                            )}>
                                {onClearAction ? (
                                    <button
                                        type="button"
                                        onClick={onClearAction}
                                        className={cn(
                                            "relative h-4 w-4 transition hover:opacity-75",
                                            // Inherit text color from parent
                                            "text-current"
                                        )}
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
                                    if (showStopButton) {
                                        onStop?.()
                                        return
                                    }
                                    if (inputValue.trim() && !inputLocked) {
                                        onSend(inputValue)
                                        if (value === undefined) setInternalInput("")
                                    }
                                }}
                                disabled={showStopButton ? false : (!inputValue.trim() || inputLocked)}
                                size="icon"
                                className={cn(
                                    "h-9 w-9 shrink-0 rounded-full transition-all duration-300",
                                    showStopButton
                                        ? "bg-destructive text-destructive-foreground hover:opacity-90 active:scale-95"
                                        : inputValue.trim() && !inputLocked
                                            ? "bg-primary text-primary-foreground hover:opacity-90 active:scale-95"
                                            : "bg-gray-100 text-gray-400"
                                )}
                                aria-label={showStopButton ? "Stop generation" : "Send message"}
                            >
                                {showStopButton ? <Square className="h-4 w-4" /> : <ArrowUp className="h-5 w-5" />}
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent side="top">{showStopButton ? "Stop generation" : "Send message"}</TooltipContent>
                    </Tooltip>
                </div>
            </div>
        </div>
    )
}
