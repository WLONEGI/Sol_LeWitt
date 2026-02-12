export const CHARACTER_SHEET_BUNDLE_ARTIFACT_ID = 'character_sheet_profile'

export type BundleStatus = 'pending' | 'streaming' | 'completed' | 'failed'

export interface CharacterSheetSlideImage {
    slide_number: number
    title?: string
    image_url?: string
    prompt_text?: string
    status: BundleStatus
}

export interface CharacterSheetVisualRun {
    run_id: string
    visual_artifact_id: string
    status: BundleStatus
    created_at: number
    updated_at: number
    slides: CharacterSheetSlideImage[]
}

export interface CharacterSheetVersion {
    version_id: string
    writer_artifact_id: string
    writer_status: BundleStatus
    created_at: number
    updated_at: number
    writer_output: Record<string, unknown>
    visual_runs: CharacterSheetVisualRun[]
}

export interface CharacterSheetBundleContent {
    ui_type: 'character_sheet_bundle'
    active_version_id: string | null
    versions: CharacterSheetVersion[]
}

interface MergeWriterPayload {
    artifact_id: string
    output?: unknown
    status?: unknown
}

interface MergeVisualPayload {
    artifact_id?: unknown
    slide_number?: unknown
    title?: unknown
    image_url?: unknown
    prompt_text?: unknown
    status?: unknown
    mode?: unknown
    asset_unit_kind?: unknown
}

const DEFAULT_BUNDLE: CharacterSheetBundleContent = {
    ui_type: 'character_sheet_bundle',
    active_version_id: null,
    versions: [],
}

function nowTs(): number {
    return Date.now()
}

function normalizeStatus(raw: unknown, fallback: BundleStatus = 'completed'): BundleStatus {
    if (raw === 'failed') return 'failed'
    if (raw === 'streaming') return 'streaming'
    if (raw === 'pending') return 'pending'
    if (raw === 'completed') return 'completed'
    return fallback
}

function toRecord(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
    return value as Record<string, unknown>
}

function cloneBundle(bundle: CharacterSheetBundleContent): CharacterSheetBundleContent {
    return {
        ui_type: 'character_sheet_bundle',
        active_version_id: bundle.active_version_id,
        versions: bundle.versions.map((version) => ({
            ...version,
            writer_output: { ...version.writer_output },
            visual_runs: version.visual_runs.map((run) => ({
                ...run,
                slides: run.slides.map((slide) => ({ ...slide })),
            })),
        })),
    }
}

function isCharacterHeader(promptText: unknown): boolean {
    if (typeof promptText !== 'string') return false
    return /^\s*#Character\d+/i.test(promptText)
}

export function inferVisualizerModeFromPayload(
    payload: unknown,
    existingMode?: string | null,
): string | null {
    const data = toRecord(payload)
    if (typeof data.mode === 'string' && data.mode.trim().length > 0) {
        return data.mode.trim()
    }
    if (
        typeof data.asset_unit_kind === 'string' &&
        /character/i.test(data.asset_unit_kind)
    ) {
        return 'character_sheet_render'
    }
    if (isCharacterHeader(data.prompt_text)) {
        return 'character_sheet_render'
    }
    if (existingMode && existingMode.trim().length > 0) {
        return existingMode
    }
    return null
}

export function isCharacterSheetVisualPayload(payload: unknown, existingMode?: string | null): boolean {
    const mode = inferVisualizerModeFromPayload(payload, existingMode)
    return mode === 'character_sheet_render'
}

export function normalizeCharacterSheetBundle(content: unknown): CharacterSheetBundleContent {
    const raw = toRecord(content)

    if (raw.ui_type !== 'character_sheet_bundle' || !Array.isArray(raw.versions)) {
        return cloneBundle(DEFAULT_BUNDLE)
    }

    const versions: CharacterSheetVersion[] = []
    for (const versionItem of raw.versions) {
        const version = toRecord(versionItem)
        const versionId = typeof version.version_id === 'string' ? version.version_id : ''
        const writerArtifactId =
            typeof version.writer_artifact_id === 'string' ? version.writer_artifact_id : versionId
        if (!versionId || !writerArtifactId) continue

        const visualRuns: CharacterSheetVisualRun[] = []
        const rawRuns = Array.isArray(version.visual_runs) ? version.visual_runs : []
        for (const runItem of rawRuns) {
            const run = toRecord(runItem)
            const runId = typeof run.run_id === 'string' ? run.run_id : ''
            const visualArtifactId =
                typeof run.visual_artifact_id === 'string' ? run.visual_artifact_id : runId
            if (!runId || !visualArtifactId) continue

            const slides: CharacterSheetSlideImage[] = []
            const rawSlides = Array.isArray(run.slides) ? run.slides : []
            for (const slideItem of rawSlides) {
                const slide = toRecord(slideItem)
                const slideNumber = Number(slide.slide_number)
                if (!Number.isInteger(slideNumber) || slideNumber <= 0) continue

                slides.push({
                    slide_number: slideNumber,
                    title: typeof slide.title === 'string' ? slide.title : undefined,
                    image_url: typeof slide.image_url === 'string' ? slide.image_url : undefined,
                    prompt_text: typeof slide.prompt_text === 'string' ? slide.prompt_text : undefined,
                    status: normalizeStatus(slide.status, 'streaming'),
                })
            }

            slides.sort((a, b) => a.slide_number - b.slide_number)

            visualRuns.push({
                run_id: runId,
                visual_artifact_id: visualArtifactId,
                status: normalizeStatus(run.status, 'streaming'),
                created_at: Number(run.created_at) || nowTs(),
                updated_at: Number(run.updated_at) || nowTs(),
                slides,
            })
        }

        versions.push({
            version_id: versionId,
            writer_artifact_id: writerArtifactId,
            writer_status: normalizeStatus(version.writer_status, 'completed'),
            created_at: Number(version.created_at) || nowTs(),
            updated_at: Number(version.updated_at) || nowTs(),
            writer_output: toRecord(version.writer_output),
            visual_runs: visualRuns,
        })
    }

    versions.sort((a, b) => a.created_at - b.created_at)

    const activeVersionIdRaw =
        typeof raw.active_version_id === 'string' && raw.active_version_id.trim().length > 0
            ? raw.active_version_id.trim()
            : null
    const activeVersionId =
        activeVersionIdRaw && versions.some((version) => version.version_id === activeVersionIdRaw)
            ? activeVersionIdRaw
            : (versions.length > 0 ? versions[versions.length - 1].version_id : null)

    return {
        ui_type: 'character_sheet_bundle',
        active_version_id: activeVersionId,
        versions,
    }
}

export function mergeCharacterSheetBundleWithWriter(
    existingContent: unknown,
    payload: MergeWriterPayload,
): CharacterSheetBundleContent {
    const bundle = normalizeCharacterSheetBundle(existingContent)
    const next = cloneBundle(bundle)
    const ts = nowTs()
    const versionId = payload.artifact_id
    if (!versionId || versionId.trim().length === 0) {
        return next
    }

    const writerOutput = toRecord(payload.output)
    const writerStatus = normalizeStatus(payload.status, 'completed')

    const existingIndex = next.versions.findIndex((version) => version.version_id === versionId)
    if (existingIndex >= 0) {
        const target = next.versions[existingIndex]
        next.versions[existingIndex] = {
            ...target,
            writer_artifact_id: versionId,
            writer_status: writerStatus,
            writer_output: writerOutput,
            updated_at: ts,
        }
    } else {
        next.versions.push({
            version_id: versionId,
            writer_artifact_id: versionId,
            writer_status: writerStatus,
            writer_output: writerOutput,
            created_at: ts,
            updated_at: ts,
            visual_runs: [],
        })
    }

    next.versions.sort((a, b) => a.created_at - b.created_at)
    next.active_version_id = versionId
    return next
}

export function mergeCharacterSheetBundleWithVisual(
    existingContent: unknown,
    payload: MergeVisualPayload,
): CharacterSheetBundleContent {
    const bundle = normalizeCharacterSheetBundle(existingContent)
    const next = cloneBundle(bundle)
    const ts = nowTs()

    const visualArtifactId = typeof payload.artifact_id === 'string' ? payload.artifact_id : ''
    if (!visualArtifactId) {
        return next
    }

    if (next.versions.length === 0) {
        const placeholderVersionId = `pending:${visualArtifactId}`
        next.versions.push({
            version_id: placeholderVersionId,
            writer_artifact_id: placeholderVersionId,
            writer_status: 'pending',
            writer_output: {},
            created_at: ts,
            updated_at: ts,
            visual_runs: [],
        })
        next.active_version_id = placeholderVersionId
    }

    const targetVersion =
        next.versions.find((version) => version.version_id === next.active_version_id) ||
        next.versions[next.versions.length - 1]

    targetVersion.updated_at = ts

    const normalizedStatus = normalizeStatus(payload.status, 'streaming')

    let targetRun = targetVersion.visual_runs.find((run) => run.visual_artifact_id === visualArtifactId)
    if (!targetRun) {
        targetRun = {
            run_id: visualArtifactId,
            visual_artifact_id: visualArtifactId,
            status: normalizedStatus,
            created_at: ts,
            updated_at: ts,
            slides: [],
        }
        targetVersion.visual_runs.push(targetRun)
    }

    targetRun.updated_at = ts
    targetRun.status = normalizedStatus

    const slideNumber = Number(payload.slide_number)
    if (Number.isInteger(slideNumber) && slideNumber > 0) {
        const slideIndex = targetRun.slides.findIndex((slide) => slide.slide_number === slideNumber)
        const current = slideIndex >= 0 ? targetRun.slides[slideIndex] : null

        const nextSlide: CharacterSheetSlideImage = {
            slide_number: slideNumber,
            title: typeof payload.title === 'string' && payload.title.trim().length > 0
                ? payload.title
                : current?.title,
            image_url: typeof payload.image_url === 'string' && payload.image_url.trim().length > 0
                ? payload.image_url
                : current?.image_url,
            prompt_text: typeof payload.prompt_text === 'string' && payload.prompt_text.trim().length > 0
                ? payload.prompt_text
                : current?.prompt_text,
            status: normalizeStatus(payload.status, current?.status || 'streaming'),
        }

        if (slideIndex >= 0) {
            targetRun.slides[slideIndex] = nextSlide
        } else {
            targetRun.slides.push(nextSlide)
        }
        targetRun.slides.sort((a, b) => a.slide_number - b.slide_number)

        if (!payload.status) {
            targetRun.status = targetRun.slides.every((slide) => Boolean(slide.image_url))
                ? 'completed'
                : 'streaming'
        }
    }

    return next
}

function parseStepNumber(artifactId: string): number {
    const match = artifactId.match(/^step_(\d+)_/)
    if (!match) return Number.MAX_SAFE_INTEGER
    return Number(match[1])
}

function isCharacterSheetDeckContent(content: unknown): boolean {
    const raw = toRecord(content)
    if (typeof raw.mode === 'string' && raw.mode === 'character_sheet_render') {
        return true
    }

    const slides = Array.isArray(raw.slides) ? raw.slides : []
    return slides.some((slide) => {
        const data = toRecord(slide)
        return isCharacterHeader(data.prompt_text)
    })
}

interface ArtifactLike {
    id: string
    type: string
    title: string
    content: unknown
    version: number
    status?: string
}

export function buildCharacterSheetBundleArtifact(
    artifacts: Record<string, ArtifactLike>,
): ArtifactLike | null {
    const entries = Object.values(artifacts)
        .filter((artifact) => artifact && typeof artifact.id === 'string')
        .sort((a, b) => {
            const stepA = parseStepNumber(a.id)
            const stepB = parseStepNumber(b.id)
            if (stepA !== stepB) return stepA - stepB
            return a.id.localeCompare(b.id)
        })

    let bundle = normalizeCharacterSheetBundle(artifacts[CHARACTER_SHEET_BUNDLE_ARTIFACT_ID]?.content)

    for (const artifact of entries) {
        if (artifact.type === 'writer_character_sheet') {
            bundle = mergeCharacterSheetBundleWithWriter(bundle, {
                artifact_id: artifact.id,
                output: artifact.content,
                status: artifact.status,
            })
            continue
        }

        if (artifact.type !== 'slide_deck') continue
        if (!isCharacterSheetDeckContent(artifact.content)) continue

        const content = toRecord(artifact.content)
        const slides = Array.isArray(content.slides) ? content.slides : []

        for (const slideItem of slides) {
            const slide = toRecord(slideItem)
            bundle = mergeCharacterSheetBundleWithVisual(bundle, {
                artifact_id: artifact.id,
                slide_number: slide.slide_number,
                title: slide.title,
                image_url: slide.image_url,
                prompt_text: slide.prompt_text,
                status: slide.status,
                mode: 'character_sheet_render',
            })
        }

        bundle = mergeCharacterSheetBundleWithVisual(bundle, {
            artifact_id: artifact.id,
            status: artifact.status || 'completed',
            mode: 'character_sheet_render',
        })
    }

    if (bundle.versions.length === 0) return null

    const lastVersion = bundle.versions[bundle.versions.length - 1]
    const latestRun = lastVersion.visual_runs[lastVersion.visual_runs.length - 1]
    const bundleStatus = latestRun?.status || lastVersion.writer_status || 'completed'

    return {
        id: CHARACTER_SHEET_BUNDLE_ARTIFACT_ID,
        type: 'writer_character_sheet',
        title: 'Character Sheet',
        content: bundle,
        version: Math.max(1, entries.length + 1),
        status: bundleStatus,
    }
}
