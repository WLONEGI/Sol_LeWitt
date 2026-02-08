import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ChatInput } from "@/features/chat/components/chat-input"

describe("ChatInput stop/send behavior", () => {
  it("uses stop action while processing", () => {
    const onSend = vi.fn()
    const onStop = vi.fn()

    render(
      <ChatInput
        value="queued interrupt"
        onChange={() => {}}
        onSend={onSend}
        onStop={onStop}
        isLoading={false}
        isProcessing={true}
        showAttachments={false}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: /stop/i }))

    expect(onStop).toHaveBeenCalledTimes(1)
    expect(onSend).not.toHaveBeenCalled()
  })

  it("uses send action when not processing", () => {
    const onSend = vi.fn()
    const onStop = vi.fn()

    render(
      <ChatInput
        value="new request"
        onChange={() => {}}
        onSend={onSend}
        onStop={onStop}
        isLoading={false}
        isProcessing={false}
        showAttachments={false}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: /send/i }))

    expect(onSend).toHaveBeenCalledTimes(1)
    expect(onSend).toHaveBeenCalledWith("new request")
    expect(onStop).not.toHaveBeenCalled()
  })
})
