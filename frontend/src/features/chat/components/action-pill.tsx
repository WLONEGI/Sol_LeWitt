import { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface ActionPillProps {
    icon: LucideIcon;
    label: string;
    value?: string; // The path or argument
    className?: string;
}

export function ActionPill({ icon: Icon, label, value, className }: ActionPillProps) {
    return (
        <div className={cn(
            "inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-100/80 border border-transparent hover:border-gray-200 transition-colors",
            className
        )}>
            <Icon className="h-3.5 w-3.5 text-gray-500" />
            <span className="text-xs font-medium text-gray-700 select-none">{label}</span>
            {value && (
                <span className="text-xs font-mono text-gray-500 max-w-[300px] truncate">
                    {value}
                </span>
            )}
        </div>
    );
}
