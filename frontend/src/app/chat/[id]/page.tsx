import { Header } from "@/features/chat/components/header";
import { ChatInterface } from "@/features/chat/components/chat-interface";
import { ResizableLayout } from "@/features/preview/components/resizable-layout";
import { ArtifactView } from "@/features/preview/components/artifact-view";
import { ChatSidebar } from "@/features/chat/components/chat-sidebar";

export default function ChatPage({ params }: { params: { id: string } }) {
    const id = params.id;

    return (
        <main className="h-screen w-screen overflow-hidden bg-background relative selection:bg-primary/20 flex">
            {/* Sidebar Scope: Full height, left side */}
            <ChatSidebar />

            {/* Content Scope: Header + Main Content */}
            <div className="flex flex-col flex-1 min-w-0 h-full">
                <Header />
                <div className="relative z-10 flex-1 w-full min-h-0">
                    <div className="w-full h-full bg-transparent">
                        <ResizableLayout
                            defaultLayout={[40, 60]}
                        >
                            <ChatInterface key={id} threadId={id} />
                            <ArtifactView />
                        </ResizableLayout>
                    </div>
                </div>
            </div>
        </main>
    );
}
