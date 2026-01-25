"use client"
import { ExternalLink } from "lucide-react"

interface Source {
    title: string;
    url: string;
}

interface SourceCitationProps {
    sources: Source[];
}

export function SourceCitation({ sources }: SourceCitationProps) {
    if (!sources || sources.length === 0) return null;

    return (
        <div className="mt-3 flex flex-col gap-2">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Confirmed Sources</div>
            <div className="grid grid-cols-1 gap-2">
                {sources.map((source, index) => (
                    <a
                        key={index}
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2 p-2 rounded-md bg-background/50 border hover:bg-background/80 transition-colors text-sm group"
                    >
                        <div className="bg-primary/10 p-1.5 rounded-full text-primary group-hover:bg-primary/20">
                            <ExternalLink className="h-3 w-3" />
                        </div>
                        <span className="truncate flex-1 font-medium text-foreground/80 group-hover:text-primary transition-colors">
                            {source.title}
                        </span>
                    </a>
                ))}
            </div>
        </div>
    )
}
