"use client"

import { ChatInterface } from "@/features/chat/chat-interface";
import { ResizableLayout } from "@/components/layout/resizable-layout";
import { ArtifactView } from "@/features/preview/artifact-view";

export default function Home() {
  return (
    <main className="h-screen w-screen overflow-hidden bg-background relative selection:bg-primary/20">
      {/* Animated Aurora Background */}
      <div className="absolute inset-0 bg-aurora animate-aurora opacity-50 z-0 pointer-events-none" />

      {/* Glass Overlay for depth */}
      <div className="absolute inset-0 bg-background/30 backdrop-blur-[1px] z-0 pointer-events-none" />

      {/* Content Layer */}
      <div className="relative z-10 h-full w-full flex items-center justify-center p-4">
        <div className="w-full h-full max-w-[1920px] shadow-2xl rounded-2xl overflow-hidden border border-white/5 bg-background/40 backdrop-blur-sm">
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
