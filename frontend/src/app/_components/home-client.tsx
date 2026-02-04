"use client"

import { useEffect } from "react";
import { ChatInterface } from "@/features/chat/components/chat-interface";
import { ChatSidebar } from "@/features/chat/components/chat-sidebar";
import { ResizableLayout } from "@/features/preview/components/resizable-layout";
import { ArtifactView } from "@/features/preview/components/artifact-view";
import { SidebarProvider } from "@/components/ui/sidebar";
import { useChatStore } from "@/features/chat/stores/chat";

import { Header } from "@/features/chat/components/header";

export function HomeClient() {
  const { createSession } = useChatStore();

  // Reset session on mount to ensure "New Chat" logic works
  useEffect(() => {
    createSession();
  }, [createSession]);

  return (
    <main className="h-screen w-screen overflow-hidden bg-background relative selection:bg-primary/20 flex">
      <SidebarProvider defaultOpen={true}>
        <ChatSidebar />
        <div className="flex flex-col flex-1 min-w-0 h-full">
          <Header />
          <div className="relative z-10 flex-1 w-full min-h-0">
            <div className="w-full h-full bg-transparent">
              <ResizableLayout defaultLayout={[40, 60]}>
                <ChatInterface />
                <ArtifactView />
              </ResizableLayout>
            </div>
          </div>
        </div>
      </SidebarProvider>
    </main>
  );
}
