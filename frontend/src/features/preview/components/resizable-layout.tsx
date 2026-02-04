"use client"

import {
    Panel,
    Group,
    Separator,
} from "react-resizable-panels"
import { useArtifactStore } from "@/features/preview/stores/artifact"
import { cn } from "@/lib/utils"
import { useEffect, useState } from "react"

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
    const [isMobile, setIsMobile] = useState(false)

    // Basic mobile check
    useEffect(() => {
        const checkMobile = () => setIsMobile(window.innerWidth < 768)
        checkMobile()
        window.addEventListener("resize", checkMobile)
        return () => window.removeEventListener("resize", checkMobile)
    }, [])

    if (isMobile) {
        return (
            <div className="h-screen w-full flex flex-col">
                {isPreviewOpen ? children[1] : children[0]}
            </div>
        )
    }

    return (
        <Group
            // @ts-ignore
            orientation="horizontal"
            className="h-full w-full bg-transparent overflow-hidden"
        >
            <Panel
                defaultSize={isPreviewOpen ? defaultLayout[0] : 100}
                minSize={30}
                className={cn(
                    "transition-all duration-500 ease-in-out relative z-10 flex flex-col items-center",
                    !isPreviewOpen && "min-w-full"
                )}
            >
                <div className="w-full max-w-4xl h-full flex flex-col">
                    {children[0]}
                </div>
            </Panel>

            {isPreviewOpen && (
                <Panel
                    defaultSize={defaultLayout[1]}
                    minSize={30}
                    className="relative z-20 h-full transition-all duration-500 ease-in-out"
                >
                    <div className="h-full w-full">
                        {children[1]}
                    </div>
                </Panel>
            )}
        </Group>
    )
}
