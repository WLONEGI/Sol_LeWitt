import { UIMessage } from "ai";
import { ProcessStep } from "./process";

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

export type TimelineItemType = 'message' | 'process_step' | 'worker_result' | 'artifact' | 'plan_update';

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
}

export interface PlanUpdateTimelineItem extends TimelineItem {
    type: 'plan_update';
    plan: any; // Using any for now to match loose metadata typing locally, ideally strictly typed
    title?: string;
    description?: string;
}

export type TimelineEvent =
    | MessageTimelineItem
    | ProcessTimelineItem
    | WorkerResultTimelineItem
    | ArtifactTimelineItem
    | PlanUpdateTimelineItem;
