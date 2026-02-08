export interface ResolveDataEventMessageCountParams {
    messageCountOverride?: number
    streamMessageCount?: number | null
    currentMessageCount: number
}

export function resolveDataEventMessageCount({
    messageCountOverride,
    streamMessageCount,
    currentMessageCount,
}: ResolveDataEventMessageCountParams): number {
    if (typeof messageCountOverride === 'number' && Number.isFinite(messageCountOverride)) {
        return messageCountOverride
    }
    if (typeof streamMessageCount === 'number' && Number.isFinite(streamMessageCount)) {
        return streamMessageCount
    }
    return currentMessageCount
}
