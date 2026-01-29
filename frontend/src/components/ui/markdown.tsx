"use client"

import React, { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { cn } from '@/lib/utils'; // Assumes utils.ts exists from shadcn

interface MarkdownProps {
    children: string;
    className?: string;
}

export const Markdown = memo(({ children, className }: MarkdownProps) => {
    return (
        <div className={cn("prose dark:prose-invert max-w-none break-words", className)}>
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                    code({ node, className, children, ...props }) {
                        const match = /language-(\w+)/.exec(className || '');
                        const isInline = !match;
                        if (isInline) {
                            return (
                                <code className={cn("bg-muted px-1 py-0.5 rounded text-sm font-mono", className)} {...props}>
                                    {children}
                                </code>
                            );
                        }
                        return (
                            <SyntaxHighlighter
                                style={vscDarkPlus}
                                language={match[1]}
                                PreTag="div"
                                className="rounded-md border my-2"
                                {...props as any}
                            >
                                {String(children).replace(/\n$/, '')}
                            </SyntaxHighlighter>
                        );
                    }
                }}
            >
                {String(children || "")}
            </ReactMarkdown>
        </div>
    );
});

Markdown.displayName = 'Markdown';
