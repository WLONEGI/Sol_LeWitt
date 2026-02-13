"use client"

export type InpaintReferenceImagePayload = {
    image_url: string
    caption?: string
    mime_type?: string
}

interface UploadAttachmentsResponseItem {
    filename?: unknown
    kind?: unknown
    url?: unknown
    mime_type?: unknown
}

export async function uploadInpaintReferenceImages(params: {
    token: string
    files: File[]
    threadId?: string | null
}): Promise<InpaintReferenceImagePayload[]> {
    const { token, files, threadId } = params
    if (!token) {
        throw new Error("認証情報がありません。再ログインしてください。")
    }
    if (!Array.isArray(files) || files.length === 0) {
        return []
    }

    const formData = new FormData()
    files.forEach((file) => formData.append("files", file))
    if (typeof threadId === "string" && threadId.trim().length > 0) {
        formData.append("thread_id", threadId.trim())
    }

    const response = await fetch("/api/uploads", {
        method: "POST",
        headers: {
            Authorization: `Bearer ${token}`,
        },
        body: formData,
    })

    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
        const detail =
            typeof payload?.detail === "string"
                ? payload.detail
                : (typeof payload?.error === "string" ? payload.error : `画像アップロードに失敗しました (${response.status})`)
        throw new Error(detail)
    }

    const attachments = Array.isArray(payload?.attachments) ? payload.attachments as UploadAttachmentsResponseItem[] : []
    const mapped = attachments
        .filter((item) => item && item.kind === "image" && typeof item.url === "string" && item.url.length > 0)
        .map((item) => ({
            image_url: item.url as string,
            caption: typeof item.filename === "string" && item.filename.trim().length > 0 ? item.filename.trim() : undefined,
            mime_type:
                typeof item.mime_type === "string" && item.mime_type.toLowerCase().startsWith("image/")
                    ? item.mime_type.toLowerCase()
                    : undefined,
        }))

    if (mapped.length !== files.length) {
        throw new Error("参照画像のアップロード結果が不正です。")
    }

    return mapped
}
