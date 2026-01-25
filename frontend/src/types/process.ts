export type ProcessStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface ProcessEvent {
    type: 'workflow_start' | 'agent_start' | 'agent_end' | 'tool_call' | 'tool_result' | 'progress' | 'artifact';
    content: any;
    metadata: {
        agent_name?: string;
        id?: string;
        [key: string]: any;
    };
    timestamp: number;
}

export interface ProcessStep {
    id: string;
    title: string;
    status: ProcessStatus;
    expanded: boolean;
    logs: ProcessLog[];
    agentName?: string;
    description?: string;
}

export interface ProcessLog {
    id: string; // Internal unique ID for the log item
    runId?: string; // Backend run_id for matching events
    type: 'tool' | 'artifact' | 'message';
    title: string;
    status: ProcessStatus;
    content?: any;
    metadata?: any;
    progress?: {
        message: string;
        percent?: number;
    };
}
