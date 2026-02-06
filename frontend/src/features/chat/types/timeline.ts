import { UIMessage } from "ai";
import { ProcessStep } from "../../preview/types/process";

/**
 * AI SDKのUIMessageを拡張し、カスタムプロパティをサポート
 * sources: 引用元情報
 * reasoning: LLMの思考プロセス
 * name: エージェント名
 * avatar: アバターURL
 */
export interface ExtendedMessage extends UIMessage {
    sources?: { title: string; url: string }[];
    reasoning?: string;
    name?: string;
    avatar?: string;
    content: string; // UIMessageのcontentはUIMessageContentだが、ここではstringを想定
    toolInvocations?: any[]; // AI SDK toolInvocations
}

export type TimelineItemType = 'message' | 'process_step' | 'worker_result' | 'artifact' | 'plan_update' | 'code_execution' | 'slide_outline' | 'research_report' | 'plan_step_marker' | 'plan_step_end_marker';

export interface TimelineItem {
    id: string;
    type: TimelineItemType;
    timestamp: number;
}

export interface MessageTimelineItem extends TimelineItem {
    type: 'message';
    message: ExtendedMessage;
}

export interface ProcessTimelineItem extends TimelineItem {
    type: 'process_step';
    step: ProcessStep;
}

export interface WorkerResultTimelineItem extends TimelineItem {
    type: 'worker_result';
    role: string;
    summary: string;
    status: string;
}

export interface ArtifactTimelineItem extends TimelineItem {
    type: 'artifact';
    artifactId: string;
    title: string;
    icon?: string;
    previewUrls?: string[];
    kind?: string;
    slides?: any[];
    status?: string;
    pdf_url?: string;
}

export interface PlanUpdateTimelineItem extends TimelineItem {
    type: 'plan_update';
    plan: any; // Using any for now to match loose metadata typing locally, ideally strictly typed
    title?: string;
    description?: string;
}

export interface CodeExecutionTimelineItem extends TimelineItem {
    type: 'code_execution';
    code: string;
    language: string;
    status: 'running' | 'completed' | 'failed';
    result?: string;
    toolCallId: string;
}

export interface SlideOutlineTimelineItem extends TimelineItem {
    type: 'slide_outline';
    title?: string;
    slides: {
        slide_number: number;
        title: string;
        description?: string;
        bullet_points: string[];
        key_message?: string;
    }[];
}

export interface ResearchReportTimelineItem extends TimelineItem {
    type: 'research_report';
    taskId: string;
    perspective: string;
    status: 'running' | 'completed';
}

export interface PlanStepMarkerTimelineItem extends TimelineItem {
    type: 'plan_step_marker';
    stepId: string;
    title: string;
}

export interface PlanStepEndMarkerTimelineItem extends TimelineItem {
    type: 'plan_step_end_marker';
    stepId: string;
}

export type TimelineEvent =
    | MessageTimelineItem
    | ProcessTimelineItem
    | WorkerResultTimelineItem
    | ArtifactTimelineItem
    | PlanUpdateTimelineItem
    | CodeExecutionTimelineItem
    | SlideOutlineTimelineItem
    | ResearchReportTimelineItem
    | PlanStepMarkerTimelineItem
    | PlanStepEndMarkerTimelineItem;
