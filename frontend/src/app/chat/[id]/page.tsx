"use client"

import { ChatInterface } from "@/features/chat/chat-interface";
import { ResizableLayout } from "@/components/layout/resizable-layout";
import { ArtifactView } from "@/features/preview/artifact-view";
import { useParams } from "next/navigation";

export default function ChatPage() {
    const params = useParams();
    const id = params.id as string;

    return (
        <main className="h-screen w-screen overflow-hidden bg-background relative selection:bg-primary/20">
            <div className="relative z-10 h-full w-full flex items-center justify-center">
                <div className="w-full h-full bg-transparent">
                    <ResizableLayout
                        defaultLayout={[40, 60]}
                    >
                        <ChatInterface key={id} threadId={id} />
                        <ArtifactView />
                    </ResizableLayout>
                </div>
            </div>
        </main>
    );
}
