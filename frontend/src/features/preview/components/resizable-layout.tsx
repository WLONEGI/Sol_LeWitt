"use client"

import { useId } from "react"
import {
    Panel,
    Group,
    Separator,
} from "react-resizable-panels"
import { useArtifactStore } from "@/features/preview/stores/artifact"
import { cn } from "@/lib/utils"

interface ResizableLayoutProps {
    children: [React.ReactNode, React.ReactNode] // [Left, Right]
    defaultLayout?: number[]
    navCollapsedSize?: number
}

export function ResizableLayout({
    children,
    defaultLayout = [50, 50],
    navCollapsedSize = 0,
}: ResizableLayoutProps) {
    const { isPreviewOpen } = useArtifactStore()
    const id = useId()

    return (
        <Group
            id={id}
            // @ts-ignore
            orientation="horizontal"
            className="h-full w-full bg-background overflow-hidden flex min-w-0 min-h-0"
        >
            <Panel
                id={`${id}-left`}
                defaultSize={isPreviewOpen ? defaultLayout[0] : 100}
                minSize={30}
                className={cn(
                    "transition-all duration-500 ease-in-out relative z-10 flex flex-col items-center min-w-0 min-h-0 bg-background",
                    !isPreviewOpen && "min-w-full",
                    isPreviewOpen ? "panel-mobile-hidden" : "panel-mobile-full"
                )}
            >
                <div className="w-full max-w-4xl h-full flex flex-col min-w-0 min-h-0">
                    {children[0]}
                </div>
            </Panel>

            {isPreviewOpen && (
                <Panel
                    id={`${id}-right`}
                    defaultSize={defaultLayout[1]}
                    minSize={30}
                    className="relative z-20 h-full transition-all duration-500 ease-in-out min-w-0 min-h-0 bg-background panel-mobile-full"
                >
                    <div className="h-full w-full min-w-0 min-h-0">
                        {children[1]}
                    </div>
                </Panel>
            )}
        </Group>
    )
}
