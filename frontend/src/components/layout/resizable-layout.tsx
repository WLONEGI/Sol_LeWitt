"use client"

import {
    Panel,
    Group,
    Separator,
} from "react-resizable-panels"
import { useArtifactStore } from "@/store/artifact"
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
            className="h-full w-full bg-transparent"
        >
            <Panel
                defaultSize={isPreviewOpen ? defaultLayout[0] : 100}
                minSize={30}
                className={cn("transition-all duration-300 ease-in-out relative z-10", !isPreviewOpen && "min-w-full")}
            >
                {children[0]}
            </Panel>

            {isPreviewOpen && (
                <>
                    <Separator className="w-1 bg-transparent hover:bg-primary/20 transition-colors cursor-col-resize z-50 -ml-[2px] -mr-[2px]" />
                    <Panel defaultSize={defaultLayout[1]} minSize={30} className="relative z-10">
                        {children[1]}
                    </Panel>
                </>
            )}
        </Group>
    )
}
