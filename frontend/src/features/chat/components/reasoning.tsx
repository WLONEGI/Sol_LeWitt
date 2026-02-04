"use client"

import * as React from "react"
import * as CollapsiblePrimitive from "@radix-ui/react-collapsible"
import { ChevronDown, Brain } from "lucide-react"

import { cn } from "@/lib/utils"
import { Markdown } from "@/components/ui/markdown"

const Reasoning = React.forwardRef<
    React.ElementRef<typeof CollapsiblePrimitive.Root>,
    React.ComponentPropsWithoutRef<typeof CollapsiblePrimitive.Root>
>(({ className, ...props }, ref) => (
    <CollapsiblePrimitive.Root
        ref={ref}
        className={cn("w-full bg-transparent", className)}
        {...props}
    />
))
Reasoning.displayName = CollapsiblePrimitive.Root.displayName

const ReasoningTrigger = React.forwardRef<
    React.ElementRef<typeof CollapsiblePrimitive.CollapsibleTrigger>,
    React.ComponentPropsWithoutRef<typeof CollapsiblePrimitive.CollapsibleTrigger>
>(({ className, children, ...props }, ref) => (
    <CollapsiblePrimitive.CollapsibleTrigger
        ref={ref}
        className={cn(
            "flex w-full items-center justify-start py-3 font-medium text-base transition-all hover:opacity-80 [&[data-state=open]>svg]:rotate-180 gap-2",
            className
        )}
        {...props}
    >
        <span className="text-gray-700 dark:text-gray-300">
            {children || "思考プロセスを表示"}
        </span>
        <ChevronDown className="h-5 w-5 transition-transform duration-200 text-gray-500" />
    </CollapsiblePrimitive.CollapsibleTrigger>
))
ReasoningTrigger.displayName = CollapsiblePrimitive.CollapsibleTrigger.displayName

const ReasoningContent = React.forwardRef<
    React.ElementRef<typeof CollapsiblePrimitive.CollapsibleContent>,
    React.ComponentPropsWithoutRef<typeof CollapsiblePrimitive.CollapsibleContent>
>(({ className, children, ...props }, ref) => (
    <CollapsiblePrimitive.CollapsibleContent
        ref={ref}
        className={cn(
            "overflow-hidden text-base transition-all data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down",
            className
        )}
        {...props}
    >
        <div className="pt-2 text-gray-800 dark:text-gray-200 border-l-2 border-gray-100 dark:border-gray-800 ml-1">
            <Markdown className="prose prose-base dark:prose-invert max-w-none leading-relaxed px-5">
                {typeof children === 'string' ? children : ""}
            </Markdown>
        </div>
    </CollapsiblePrimitive.CollapsibleContent>
))
ReasoningContent.displayName = CollapsiblePrimitive.CollapsibleContent.displayName

export { Reasoning, ReasoningTrigger, ReasoningContent }
