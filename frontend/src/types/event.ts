import type { FileInfo } from '../api/file';

export type AgentSSEEvent = {
  event: 'tool' | 'step' | 'message' | 'error' | 'done' | 'title' | 'wait' | 'plan' | 'attachments'
       | 'cloud_pipeline' | 'architecture_plan' | 'iac_generation' | 'deployment' | 'monitoring' | 'cost_estimate';
  data: ToolEventData | StepEventData | MessageEventData | ErrorEventData | DoneEventData | TitleEventData | WaitEventData | PlanEventData | any;
}

export interface BaseEventData {
  event_id: string;
  timestamp: number;
}

export interface ToolEventData extends BaseEventData {
  tool_call_id: string;
  name: string;
  status: "calling" | "called";
  function: string;
  args: {[key: string]: any};
  content?: any;
}

export interface StepEventData extends BaseEventData {
  status: "pending" | "running" | "completed" | "failed"
  id: string
  description: string
}

export interface MessageEventData extends BaseEventData {
  content: string;
  role: "user" | "assistant";
  attachments: FileInfo[];
}

export interface ErrorEventData extends BaseEventData {
  error: string;
}

export interface DoneEventData extends BaseEventData {
}

export interface WaitEventData extends BaseEventData {
}

export interface TitleEventData extends BaseEventData {
  title: string;
}

export interface PlanEventData extends BaseEventData {
  steps: StepEventData[];
  title?: string;
  goal?: string;
  mermaid?: string;
}