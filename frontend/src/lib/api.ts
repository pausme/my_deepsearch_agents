import { API_BASE_URL } from "./config";
import type {
  CancelTaskResponse,
  CreateSessionResponse,
  FileListResponse,
  RenovationReport,
  RenovationSession,
  RenovationTaskResponse,
  RiskItem,
  TaskResponse,
  UploadResponse
} from "../types";

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    // 统一错误结构：detail 可能是 {code, message} 对象或纯字符串
    let message = `HTTP ${response.status}`;
    if (payload && typeof payload === "object" && "detail" in payload) {
      const detail = (payload as { detail: unknown }).detail;
      if (detail && typeof detail === "object" && "message" in detail) {
        message = String((detail as { message: unknown }).message);
      } else {
        message = String(detail);
      }
    }
    throw new Error(message);
  }

  return payload as T;
}

export async function startTask(query: string, threadId: string): Promise<TaskResponse> {
  return requestJson<TaskResponse>(apiUrl("/api/task"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      query,
      thread_id: threadId
    })
  });
}

export async function cancelTask(threadId: string): Promise<CancelTaskResponse> {
  return requestJson<CancelTaskResponse>(apiUrl(`/api/task/${encodeURIComponent(threadId)}/cancel`), {
    method: "POST"
  });
}

export async function uploadSessionFiles(
  files: File[],
  threadId: string
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("thread_id", threadId);
  files.forEach((file) => formData.append("files", file));

  return requestJson<UploadResponse>(apiUrl("/api/upload"), {
    method: "POST",
    body: formData
  });
}

export async function listSessionFiles(path: string): Promise<FileListResponse> {
  // 第二个参数兜底：API_BASE_URL 为空（同源部署）时 URL 需要显式 base 才能构造
  const url = new URL(apiUrl("/api/files"), window.location.origin);
  url.searchParams.set("path", path);
  return requestJson<FileListResponse>(url);
}

export function getDownloadUrl(path: string): string {
  const url = new URL(apiUrl("/api/download"), window.location.origin);
  url.searchParams.set("path", path);
  return url.toString();
}

/* ---------- 装修业务接口 ---------- */

export interface RenovationSessionInput {
  city: string;
  house_area: number;
  room_type: string;
  renovation_stage?: string;
  district?: string;
  budget_min?: number | null;
  budget_max?: number | null;
  priority_tags?: string[];
  delivery_date?: string;
}

export async function createRenovationSession(
  input: RenovationSessionInput
): Promise<CreateSessionResponse> {
  return requestJson<CreateSessionResponse>(apiUrl("/api/renovation/sessions"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input)
  });
}

export async function listRenovationSessions(): Promise<{ sessions: RenovationSession[] }> {
  return requestJson<{ sessions: RenovationSession[] }>(apiUrl("/api/renovation/sessions"));
}

export async function startRenovationTask(
  sessionId: string,
  query: string,
  analysisType: string
): Promise<RenovationTaskResponse> {
  return requestJson<RenovationTaskResponse>(apiUrl("/api/renovation/tasks"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      query,
      analysis_type: analysisType
    })
  });
}

export async function listSessionReports(
  sessionId: string
): Promise<{ reports: RenovationReport[] }> {
  const url = new URL(apiUrl("/api/renovation/reports"));
  url.searchParams.set("session_id", sessionId);
  return requestJson<{ reports: RenovationReport[] }>(url);
}

export async function getReportDetail(
  reportId: string
): Promise<{ report: RenovationReport; risk_items: RiskItem[] }> {
  return requestJson<{ report: RenovationReport; risk_items: RiskItem[] }>(
    apiUrl(`/api/renovation/reports/${encodeURIComponent(reportId)}`)
  );
}

export async function getReportContent(
  reportId: string
): Promise<{ report_id: string; title: string; markdown: string }> {
  return requestJson<{ report_id: string; title: string; markdown: string }>(
    apiUrl(`/api/renovation/reports/${encodeURIComponent(reportId)}/content`)
  );
}
