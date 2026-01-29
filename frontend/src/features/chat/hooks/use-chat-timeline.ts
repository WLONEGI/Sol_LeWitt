"use client"

import { useState, useRef, useCallback } from 'react'
import { v4 as uuidv4 } from 'uuid';
import { useChatStore } from '../store/chat';
import { TimelineEvent, MessageTimelineItem, ProcessTimelineItem } from "../types/timeline";
import { ProcessStep, ProcessLog } from "../../preview/types/process";
import { UIMessage } from '@ai-sdk/react';
import { parse } from 'best-effort-json-parser';

type SetArtifactFunc = (artifact: any) => void;

export function useChatTimeline() {
    const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
    const currentStepIdRef = useRef<string | null>(null);

    const handleProcessEventToTimeline = useCallback((
        data: any,
        setArtifact: SetArtifactFunc
    ) => {
        // 1. Plan Update (Legacy UI Type check, but coming via data stream?)
        // If plan update comes as a specific event type, add it.
        // Assuming 'artifact' event with type 'plan' handles this.

        // 2. Process Steps (Accordion)
        // We update the *last* ProcessStepItem in the timeline if it matches currentStepId,
        // OR we append a new ProcessStepItem.

        if (data.type === 'data-agent-start' || data.type === 'data-workflow-start') {
            const payload = data.data || data.content || {}; // Support both structure just in case

            const stepId = payload.id || `step-${Date.now()}`;
            const title = payload.title || `Agent: ${payload.agent_name || "Unknown"}`;
            const description = payload.description || "";
            const agentName = payload.agent_name || "System";

            // Start new step
            const newStep: ProcessStep = {
                id: stepId,
                title: title,
                status: 'running',
                expanded: true,
                logs: [],
                agentName: agentName,
                description: description
            };

            setTimeline(prev => {
                // Close previous running steps
                const closedPrev = prev.map(item => {
                    if (item.type === 'process_step' && item.step.status === 'running') {
                        return { ...item, step: { ...item.step, status: 'completed' as const, expanded: false } };
                    }
                    return item;
                });

                // Avoid duplicates if re-entrant
                if (closedPrev.some(item => item.type === 'process_step' && item.id === stepId)) return closedPrev;

                return [...closedPrev, {
                    id: stepId,
                    type: 'process_step',
                    timestamp: Date.now(),
                    step: newStep
                }];
            });
            currentStepIdRef.current = stepId;
        }
        else if (data.type === 'tool_call') {
            const stepId = currentStepIdRef.current;
            if (!stepId) return; // Should connect to active step

            const runId = data.metadata?.run_id;
            const logId = runId || `tool-${Date.now()}-${Math.random()}`;
            const toolName = data.content?.tool_name || "Tool";
            const inputSnippet = JSON.stringify(data.content?.input || {}).slice(0, 50);

            const newLog: ProcessLog = {
                id: logId, runId: runId, type: 'tool', title: `${toolName}: ${inputSnippet}...`,
                status: 'running', content: data.content, metadata: data.metadata
            };

            setTimeline(prev => prev.map(item => {
                if (item.type === 'process_step' && item.step.id === stepId) {
                    // Avoid dupe logs
                    if (item.step.logs.some((l: ProcessLog) => l.id === logId)) return item;
                    return {
                        ...item,
                        step: { ...item.step, logs: [...item.step.logs, newLog] }
                    };
                }
                return item;
            }));
        }
        else if (data.type === 'tool_result') {
            const stepId = currentStepIdRef.current;
            if (!stepId) return;
            const runId = data.metadata?.run_id;

            setTimeline(prev => prev.map(item => {
                if (item.type === 'process_step' && item.step.id === stepId) {
                    const updatedLogs = item.step.logs.map((log: ProcessLog) => {
                        if (log.runId === runId && log.status === 'running') {
                            return { ...log, status: 'completed' as const };
                        }
                        return log;
                    });
                    return { ...item, step: { ...item.step, logs: updatedLogs } };
                }
                return item;
            }));
        }
        else if (data.type === 'data-agent-end') {
            const stepId = currentStepIdRef.current;
            if (stepId) {
                setTimeline(prev => prev.map(item => {
                    if (item.type === 'process_step' && item.step.id === stepId) {
                        return { ...item, step: { ...item.step, status: 'completed' as const } };
                    }
                    return item;
                }));
            }
        }
        else if (data.type === 'data-progress') {
            const stepId = currentStepIdRef.current;
            if (!stepId) return;
            // payload is in data.data
            const payload = data.data || {};
            const runId = payload.run_id || data.metadata?.run_id;

            setTimeline(prev => prev.map(item => {
                if (item.type === 'process_step' && item.step.id === stepId) {
                    const updatedLogs = item.step.logs.map((log: ProcessLog) => {
                        if (log.runId === runId && log.status === 'running') {
                            return { ...log, progress: { message: payload.message || payload.status } };
                        }
                        return log;
                    });
                    return { ...item, step: { ...item.step, logs: updatedLogs } };
                }
                return item;
            }));
        }
        else if (data.type === 'data-artifact-ready') {
            const art = data.data || data.content;
            setArtifact({
                id: art.id, type: art.type, title: art.title,
                content: art.content, status: 'streaming'
            });

            const stepId = currentStepIdRef.current;
            if (stepId) {
                setTimeline(prev => prev.map(item => {
                    if (item.type === 'process_step' && item.step.id === stepId) {
                        if (item.step.logs.some((l: ProcessLog) => l.id === `art-${art.id}`)) return item;
                        return {
                            ...item,
                            step: {
                                ...item.step,
                                logs: [...item.step.logs, { id: `art-${art.id}`, type: 'artifact', title: `Artifact: ${art.title}`, status: 'completed', metadata: { id: art.id } }]
                            }
                        }
                    };
                    return item;
                }));
            }
        }
        else if (data.type === 'data-plan-update') {
            const planData = data.data || data.content;
            setTimeline(prev => {
                const planId = planData.id || `plan-${Date.now()}`;
                if (prev.some(item => item.id === planId)) return prev;
                return [...prev, {
                    id: planId,
                    type: 'plan_update',
                    timestamp: Date.now(),
                    plan: planData.steps || planData,
                    title: "Plan Updated"
                } as any];
            });
        }
        else if (data.type === 'data-slide_outline') {
            const outlineData = data.data || data.content;
            setTimeline(prev => {
                const outlineId = `outline-${Date.now()}`;
                return [...prev, {
                    id: outlineId,
                    type: 'slide_outline',
                    timestamp: Date.now(),
                    slides: outlineData.slides
                }];
            });
        }
        else if (data.type === 'data-visualizer-progress') {
            const slideData = data.data || data.content;
            // slideData: { slide_number, image_url, title }

            setTimeline(prev => {
                // Check if we already have a streaming artifact for this run/context
                // For simplicity, we look for the latest 'slide_deck' artifact or create one.
                // ideally use a unique ID provided by backend, but here we can assume one active generation stream?
                // Let's use a stable ID if possible, or find the last 'slide_deck' in the timeline.

                const existingIdx = prev.findLastIndex(item => item.type === 'artifact' && (item as any).kind === 'slide_deck' && (item as any).status === 'streaming');

                if (existingIdx !== -1) {
                    // Update existing
                    const existingItem = prev[existingIdx] as any;

                    // Avoid duplicates
                    if (existingItem.slides.some((s: any) => s.slide_number === slideData.slide_number)) return prev;

                    const activeSlides = [...existingItem.slides, slideData].sort((a, b) => a.slide_number - b.slide_number);

                    const newTimeline = [...prev];
                    newTimeline[existingIdx] = {
                        ...existingItem,
                        slides: activeSlides,
                        timestamp: Date.now()
                    };
                    return newTimeline;
                } else {
                    // Create new
                    return [...prev, {
                        id: `deck-${Date.now()}`,
                        type: 'artifact',
                        timestamp: Date.now(),
                        artifactId: "generated-slide-deck", // This ID matches what the slide viewer expects? 
                        title: "Generating Slides...",
                        kind: 'slide_deck',
                        status: 'streaming',
                        slides: [slideData]
                    } as any];
                }
            });
        }
        else if (data.type === 'data-title-generated') {
            const payload = data.data || data.content || {};
            const { title, thread_id } = payload;
            if (title && thread_id) {
                useChatStore.getState().updateThreadTitle(thread_id, title);
            }
        }
        else if (data.type === 'file' || (data.type === 'artifact' && data.content?.type === 'image')) {
            // Handle Image Preview
            // For Vercel SDK 'file' type, usually handled by implicit UI, but checking custom view
            const imageUrl = data.url || data.content?.image_url;
            if (imageUrl) {
                setTimeline(prev => {
                    if (prev.some(item => (item as any).previewUrls?.includes(imageUrl))) return prev;
                    return [...prev, {
                        id: `art-view-${Date.now()}`,
                        type: 'artifact',
                        timestamp: Date.now(),
                        artifactId: "generated-image",
                        title: "Generated Images",
                        icon: "Image",
                        previewUrls: [imageUrl]
                    } as any];
                })
            }
        }
        else if (data.type === 'data-code-execution') {
            const codePayload = data.data || data.content || {};
            const toolCallId = codePayload.toolCallId;

            if (toolCallId) {
                setTimeline(prev => {
                    if (prev.some(item => item.type === 'code_execution' && (item as any).toolCallId === toolCallId)) return prev;
                    return [...prev, {
                        id: `code-${toolCallId}`,
                        type: 'code_execution',
                        timestamp: Date.now(),
                        code: codePayload.code || "",
                        language: codePayload.language || "python",
                        status: 'running',
                        toolCallId: toolCallId
                    } as any];
                });
            }
        }
        // Reasoning Protocol (New hyphenated format from backend)
        else if (data.type === 'reasoning-delta') {
            const delta = data.delta || data.content?.delta || "";
            if (!delta) return;

            setTimeline(prev => {
                const lastProcessStepIndex = prev.findLastIndex(item => item.type === 'process_step');

                if (lastProcessStepIndex === -1) {
                    return prev;
                }

                const newPrev = [...prev];
                const lastProcessStepItem = newPrev[lastProcessStepIndex] as ProcessTimelineItem;
                const updatedStep = { ...lastProcessStepItem.step };

                updatedStep.thought = (updatedStep.thought || "") + delta;

                newPrev[lastProcessStepIndex] = {
                    ...lastProcessStepItem,
                    step: updatedStep
                };

                return newPrev;
            });
        }
        // Legacy/Misc Stream of Thought (thought event)
        else if (data.type === 'thought') {
            const thoughtToken = data.content?.token || "";
            if (!thoughtToken) return;

            setTimeline(prev => {
                const lastProcessStepIndex = prev.findLastIndex(item => item.type === 'process_step');
                if (lastProcessStepIndex === -1) return prev;

                const newPrev = [...prev];
                const lastProcessStepItem = newPrev[lastProcessStepIndex] as ProcessTimelineItem;
                const updatedStep = { ...lastProcessStepItem.step };
                updatedStep.thought = (updatedStep.thought || "") + thoughtToken;

                newPrev[lastProcessStepIndex] = {
                    ...lastProcessStepItem,
                    step: updatedStep
                };
                return newPrev;
            });
        }
        else if (data.type === 'data-code-output') {
            const outputPayload = data.data || data.content || {};
            const toolCallId = outputPayload.toolCallId;

            if (toolCallId) {
                setTimeline(prev => prev.map(item => {
                    if (item.type === 'code_execution' && (item as any).toolCallId === toolCallId) {
                        return {
                            ...item,
                            status: 'completed',
                            result: outputPayload.result
                        } as any;
                    }
                    return item;
                }));
            }
        }
        else if (data.type === 'data-storywriter-partial') {
            const payload = data.data || data.content || {}; // { args: "...", delta: "..." }
            const rawArgs = payload.args;

            if (rawArgs) {
                try {
                    // Best-effort parse the accumulated JSON string
                    const parsed = parse(rawArgs);

                    // Check if we have 'slides' array
                    if (parsed && Array.isArray(parsed.slides)) {
                        setTimeline(prev => {
                            const outlineId = `outline-streaming-${currentStepIdRef.current || 'global'}`;

                            // Check if exists
                            const existingIdx = prev.findIndex(item => item.id === outlineId);

                            if (existingIdx !== -1) {
                                // Update existing
                                const newTimeline = [...prev];
                                newTimeline[existingIdx] = {
                                    ...newTimeline[existingIdx],
                                    timestamp: Date.now(),
                                    slides: parsed.slides
                                } as any;
                                return newTimeline;
                            } else {
                                // Create new
                                return [...prev, {
                                    id: outlineId,
                                    type: 'slide_outline',
                                    timestamp: Date.now(),
                                    slides: parsed.slides,
                                    isStreaming: true // Optional flag for UI
                                } as any];
                            }
                        });
                    }
                } catch (e) {
                    // Ignore parse errors during streaming
                }
            }
        }
        else if (data.type === 'data-planner-partial') {
            const payload = data.data || data.content || {};
            const rawArgs = payload.args;
            if (rawArgs) {
                try {
                    const parsed = parse(rawArgs);
                    if (parsed && Array.isArray(parsed.steps)) {
                        setTimeline(prev => {
                            const planId = `plan-streaming-${data.metadata?.run_id || 'latest'}`;
                            const existingIdx = prev.findIndex(item => item.id === planId);

                            if (existingIdx !== -1) {
                                const newTimeline = [...prev];
                                newTimeline[existingIdx] = {
                                    ...newTimeline[existingIdx],
                                    plan: parsed.steps,
                                    timestamp: Date.now()
                                } as any;
                                return newTimeline;
                            } else {
                                return [...prev, {
                                    id: planId,
                                    type: 'plan_update',
                                    timestamp: Date.now(),
                                    plan: parsed.steps,
                                    title: "Generating Plan...",
                                    isStreaming: true
                                } as any];
                            }
                        });
                    }
                } catch (e) { }
            }
        }
        else if (data.type === 'data-research-worker-start') {
            const payload = data.data || data.content || {}; // { task_id, perspective, ... }
            const stepId = currentStepIdRef.current;

            // We attach to the current running step (Researcher Manager's step)
            // If no step is running, we mostly can't attach, but let's try to find the last researcher step or create one?
            // For now, assume a step is active (Manager started it).

            setTimeline(prev => {
                const targetStepIndex = stepId
                    ? prev.findIndex(item => item.type === 'process_step' && item.step.id === stepId)
                    : prev.findLastIndex(item => item.type === 'process_step' && (item.step.status === 'running' || item.step.agentName?.toLowerCase().includes('research')));

                if (targetStepIndex === -1) return prev; // Cannot find parent step

                const newPrev = [...prev];
                const item = newPrev[targetStepIndex] as ProcessTimelineItem;

                const existingSubTasks = item.step.subTasks || [];
                // Avoid dupes
                if (existingSubTasks.some(t => t.id === payload.task_id)) return prev;

                const newSubTask = {
                    id: payload.task_id || `task-${Date.now()}`,
                    title: payload.perspective || "Research Task",
                    status: 'running' as const,
                    content: ""
                };

                newPrev[targetStepIndex] = {
                    ...item,
                    step: {
                        ...item.step,
                        subTasks: [...existingSubTasks, newSubTask]
                    }
                };
                return newPrev;
            });
        }
        else if (data.type === 'data-research-worker-delta') {
            const payload = data.data || data.content || {};
            const taskId = payload.task_id;
            const delta = payload.delta;

            if (!taskId || !delta) return;

            setTimeline(prev => {
                // Find step containing this task
                const stepIndex = prev.findIndex(item =>
                    item.type === 'process_step' &&
                    item.step.subTasks?.some(t => t.id === taskId)
                );

                if (stepIndex === -1) return prev;

                const newPrev = [...prev];
                const item = newPrev[stepIndex] as ProcessTimelineItem;
                const subTasks = item.step.subTasks!;

                const taskIndex = subTasks.findIndex(t => t.id === taskId);
                if (taskIndex === -1) return prev;

                const updatedSubTasks = [...subTasks];
                updatedSubTasks[taskIndex] = {
                    ...updatedSubTasks[taskIndex],
                    content: updatedSubTasks[taskIndex].content + delta
                };

                newPrev[stepIndex] = {
                    ...item,
                    step: { ...item.step, subTasks: updatedSubTasks }
                };
                return newPrev;
            });
        }
        else if (data.type === 'data-research-worker-end') {
            const payload = data.data || data.content || {};
            const taskId = payload.task_id;

            if (!taskId) return;

            setTimeline(prev => {
                const stepIndex = prev.findIndex(item =>
                    item.type === 'process_step' &&
                    item.step.subTasks?.some(t => t.id === taskId)
                );

                if (stepIndex === -1) return prev;

                const newPrev = [...prev];
                const item = newPrev[stepIndex] as ProcessTimelineItem;
                const subTasks = item.step.subTasks!;

                const taskIndex = subTasks.findIndex(t => t.id === taskId);
                if (taskIndex === -1) return prev;

                const updatedSubTasks = [...subTasks];
                updatedSubTasks[taskIndex] = {
                    ...updatedSubTasks[taskIndex],
                    status: 'completed'
                };

                newPrev[stepIndex] = {
                    ...item,
                    step: { ...item.step, subTasks: updatedSubTasks }
                };
                return newPrev;
            });
        }
    }, []);

    const syncMessagesToTimeline = useCallback((messages: UIMessage[]) => {
        if (messages.length === 0) {
            return;
        }

        setTimeline(prev => {
            const newTimeline = [...prev];

            // Map existing timeline message IDs for quick lookup
            const existingMessageIds = new Set(
                newTimeline
                    .filter(item => item.type === 'message')
                    .map(item => (item as MessageTimelineItem).message.id)
            );

            let added = false;
            messages.forEach((msg: any) => {
                if (!existingMessageIds.has(msg.id)) {
                    // Add new message
                    newTimeline.push({
                        id: `msg-${msg.id}`,
                        type: 'message',
                        timestamp: Date.now(), // Approximate for history
                        message: msg
                    });
                    added = true;
                } else {
                    // Update existing message (streaming content updates)
                    const idx = newTimeline.findIndex(item => item.type === 'message' && (item as MessageTimelineItem).message.id === msg.id);
                    if (idx !== -1) {
                        const currentItem = newTimeline[idx] as MessageTimelineItem;
                        if (currentItem.message.content !== msg.content || currentItem.message.toolInvocations !== msg.toolInvocations) {
                            newTimeline[idx] = { ...currentItem, message: msg };
                            added = true; // State changed
                        }
                    }
                }
            });

            return added ? newTimeline : prev;
        });
    }, []);

    const completeRunningSteps = useCallback(() => {
        setTimeline(prev => prev.map(item => {
            if (item.type === 'process_step' && item.step.status === 'running') {
                return { ...item, step: { ...item.step, status: 'completed' } };
            }
            return item;
        }));
    }, []);

    return {
        timeline,
        setTimeline,
        currentStepIdRef,
        handleProcessEventToTimeline,
        syncMessagesToTimeline,
        completeRunningSteps
    };
}
