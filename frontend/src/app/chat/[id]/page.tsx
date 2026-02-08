import { ChatClient } from "@/app/chat/[id]/chat-client";

export default async function ChatPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = await params;

    return <ChatClient id={id} />;
}
