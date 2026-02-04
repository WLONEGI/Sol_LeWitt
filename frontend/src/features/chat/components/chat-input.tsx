"use client"

import * as React from "react"
import TextareaAutosize from "react-textarea-autosize"
import { SendHorizontal, Paperclip, X } from "lucide-react"

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
    className?: string;
    placeholder?: string;
    onFileSelect?: (file: File) => void;
    selectedFile?: File | null;
    onClearFile?: () => void;
}

export function ChatInput({
    onSend,
    isLoading,
    className,
    placeholder = "Type a message...",
    value,
    onChange,
    onFileSelect,
    selectedFile,
    onClearFile
}: ChatInputProps & {
    value?: string;
    onChange?: (e: React.ChangeEvent<HTMLTextAreaElement>) => void
}) {
    const [internalInput, setInternalInput] = React.useState("")
    const fileInputRef = React.useRef<HTMLInputElement>(null)

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
            {selectedFile && (
                <div className="absolute -top-12 left-0 flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-200 rounded-full w-fit text-xs animate-in slide-in-from-bottom-2">
                    <Paperclip className="h-3 w-3 text-primary" />
                    <span className="max-w-[200px] truncate">{selectedFile.name}</span>
                    <button onClick={onClearFile} className="ml-1 hover:text-destructive transition-colors">
                        <X className="h-3 w-3" />
                    </button>
                </div>
            )}

            <div className="relative flex items-end gap-2 bg-white border border-gray-200 rounded-2xl p-2 transition-all focus-within:border-gray-400 focus-within:ring-0">
                <input
                    type="file"
                    className="hidden"
                    ref={fileInputRef}
                    accept=".pptx,.pdf,.txt"
                    onChange={handleFileChange}
                />

                {/* Clip Button */}
                <Tooltip>
                    <TooltipTrigger asChild>
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-10 w-10 shrink-0 text-gray-400 hover:text-primary rounded-full hover:bg-gray-100 transition-colors"
                            onClick={() => fileInputRef.current?.click()}
                            disabled={isLoading}
                        >
                            <Paperclip className="h-5 w-5" />
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top">Attach template or data</TooltipContent>
                </Tooltip>

                <div className="relative flex-1">
                    <TextareaAutosize
                        minRows={1}
                        maxRows={5}
                        value={inputValue}
                        onChange={handleChange}
                        onKeyDown={handleKeyDown}
                        placeholder={placeholder}
                        className="flex w-full resize-none bg-transparent px-2 py-3 text-sm placeholder:text-muted-foreground focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                    />
                </div>

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
                                "h-10 w-10 shrink-0 rounded-full transition-all duration-300",
                                inputValue.trim() && !isLoading
                                    ? "bg-primary text-primary-foreground hover:opacity-90 active:scale-95"
                                    : "bg-gray-100 text-gray-400"
                            )}
                        >
                            <SendHorizontal className="h-5 w-5" />
                            <span className="sr-only">Send</span>
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top">Send message</TooltipContent>
                </Tooltip>
            </div>
        </div>
    )
}
