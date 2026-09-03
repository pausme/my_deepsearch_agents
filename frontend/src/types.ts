export type ConnectionState = "connecting" | "connected" | "reconnecting" | "closed";

export type MonitorEventName =
  | "session_created"
  | "tool_start"
  | "assistant_call"
  | "task_result"
  | "task_cancelled"
  | "error"
  | string;

export interface MonitorMessage {
  type: "monitor_event";
  event: MonitorEventName;
  message: string;
  data: Record<string, unknown>;
  timestamp: string;
}

export interface PongMessage {
  type: "pong";
  message: string;
}

export type SocketMessage = MonitorMessage | PongMessage;

export interface TaskResponse {
  status: "started" | string;
  thread_id: string;
}

export interface CancelTaskResponse {
  status: "cancelled" | "cancelling" | string;
  thread_id: string;
  message?: string;
}

export interface UploadResponse {
  status: "uploaded" | string;
  files: string[];
}

export interface OutputFile {
  name: string;
  type: "file" | string;
  path: string;
  size: number;
  mtime: number;
}

export interface FileListResponse {
  files?: OutputFile[];
  error?: string;
}

export interface UploadedItem {
  uid: string;
  name: string;
  size: number;
  raw: File;
}

/* ---------- 装修业务接口（FIX-005/009） ---------- */

export interface RenovationSession {
  session_id: string;
  thread_id: string;
  user_id: number;
  city: string;
  district?: string;
  house_area: number;
  room_type: string;
  renovation_stage: string;
  budget_min?: number | null;
  budget_max?: number | null;
  priority_tags: string[];
  delivery_date?: string;
  status: "ACTIVE" | "CLOSED" | string;
  create_time: string;
  report_count?: number;
}

export interface RenovationTask {
  task_id: string;
  session_id: string;
  thread_id: string;
  analysis_type: string;
  query: string;
  status: "PENDING" | "RUNNING" | "SUCCESS" | "FAILED" | "CANCELLED" | string;
  error_message?: string | null;
  start_time?: string | null;
  finish_time?: string | null;
  create_time: string;
}

export interface RiskItem {
  id: number;
  task_id: string;
  report_id?: string | null;
  title: string;
  risk_type: string;
  risk_level: "HIGH" | "MEDIUM" | "LOW" | string;
  evidence?: string;
  description?: string;
  suggestion?: string;
  create_time: string;
}

export interface RenovationReport {
  report_id: string;
  session_id: string;
  task_id: string;
  title: string;
  summary?: string;
  budget_score?: number | null;
  risk_level?: string | null;
  markdown_path?: string;
  pdf_path?: string;
  status: string;
  create_time: string;
}

export interface CreateSessionResponse {
  status: string;
  session_id: string;
  thread_id: string;
  session: RenovationSession;
}

export interface RenovationTaskResponse {
  status: string;
  task_id: string;
  session_id: string;
  thread_id: string;
}
