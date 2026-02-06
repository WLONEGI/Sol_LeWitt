import { ChatClient } from "@/app/chat/[id]/chat-client";

export default function ChatPage({ params }: { params: { id: string } }) {
    const id = params.id;

    return <ChatClient id={id} />;
}
