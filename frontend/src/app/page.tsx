"use client"

import { ChatInterface } from "@/features/chat/chat-interface";
import { ResizableLayout } from "@/components/layout/resizable-layout";
import { ArtifactView } from "@/features/preview/artifact-view";

export default function Home() {
  return (
    <main className="h-screen w-screen overflow-hidden bg-background relative selection:bg-primary/20">
      <div className="relative z-10 h-full w-full flex items-center justify-center">
        <div className="w-full h-full bg-transparent">
          <ResizableLayout
            defaultLayout={[40, 60]}
          >
            <ChatInterface />
            <ArtifactView />
          </ResizableLayout>
        </div>
      </div>
    </main>
  );
}
