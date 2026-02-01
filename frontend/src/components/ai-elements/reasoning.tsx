"use client"

import * as React from "react"
import * as CollapsiblePrimitive from "@radix-ui/react-collapsible"
import { ChevronDown, Brain } from "lucide-react"

import { cn } from "@/lib/utils"

const Reasoning = React.forwardRef<
    React.ElementRef<typeof CollapsiblePrimitive.Root>,
    React.ComponentPropsWithoutRef<typeof CollapsiblePrimitive.Root>
>(({ className, ...props }, ref) => (
    <CollapsiblePrimitive.Root
        ref={ref}
        className={cn("w-full border rounded-lg bg-muted/50", className)}
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
            "flex w-full items-center justify-between p-3 font-medium text-sm transition-all hover:bg-muted/60 [&[data-state=open]>svg]:rotate-180",
            className
        )}
        {...props}
    >
        <div className="flex items-center gap-2 text-muted-foreground">
            <Brain className="h-4 w-4" />
            {children || "Thinking Process"}
        </div>
        <ChevronDown className="h-4 w-4 transition-transform duration-200 text-muted-foreground" />
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
            "overflow-hidden text-sm transition-all data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down",
            className
        )}
        {...props}
    >
        <div className="p-3 pt-0 text-muted-foreground border-t border-border/50 font-mono text-xs leading-relaxed whitespace-pre-wrap">
            {children}
        </div>
    </CollapsiblePrimitive.CollapsibleContent>
))
ReasoningContent.displayName = CollapsiblePrimitive.CollapsibleContent.displayName

export { Reasoning, ReasoningTrigger, ReasoningContent }
