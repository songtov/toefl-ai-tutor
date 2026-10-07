export type Session = {
  id: number;
  plan_reason: string;
  task_ids: number[];
  cost_usd: number;
};

export type Task = {
  id: number;
  type: string;
  difficulty: string;
  content: { situation: string; recipient: string; requirements: string[] };
  directions: string;
};

export type Answer = {
  result_id: number;
  score: number;
  criteria: { criterion: string; rationale: string }[];
  corrections: {
    original: string;
    corrected: string;
    reason: string;
    error_types: string[];
  }[];
  usage: { input_tokens: number; output_tokens: number; cost_usd: number };
};

export type SessionSummary = {
  id: number;
  started_at: string;
  task_count: number;
  answered_count: number;
};

export type TaskDetail = Task & { answer_text: string | null; result: Answer | null };

export type SessionDetail = {
  id: number;
  plan_reason: string;
  started_at: string;
  tasks: TaskDetail[];
};

export type AuthStatus = { signed_in: boolean; email: string | null; plan_enabled: boolean };

export const MANAGE_USAGE_URL = "https://chatgpt.com/settings/usage";

export const USAGE_LIMIT_MESSAGE =
  "Usage limit reached. Review your plan or this app's limit in ChatGPT settings.";

const ERROR_MESSAGES: Record<string, string> = {
  sign_in_required: "Sign in with ChatGPT to continue.",
  plan_not_enabled: "ChatGPT plan usage is not enabled for this sign-in. Sign in again and allow it.",
  subscription_sharing_usage_limit_exceeded: USAGE_LIMIT_MESSAGE,
  access_denied: "Sign-in was cancelled.",
};

export const describeError = (code: string) => ERROR_MESSAGES[code] ?? code;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(describeError(body?.detail ?? `${res.status} ${res.statusText}`));
  }
  return res.json();
}

export const startSession = () => request<Session>("/sessions", { method: "POST" });

export const listSessions = () => request<SessionSummary[]>("/sessions");

export const getSession = (sessionId: number) => request<SessionDetail>(`/sessions/${sessionId}`);

export const submitAnswer = (taskId: number, text: string) =>
  request<Answer>(`/tasks/${taskId}/answer`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });

export const getAuthStatus = () => request<AuthStatus>("/auth/status");

export const login = () => request<{ authorize_url: string }>("/auth/login", { method: "POST" });

export const logout = () => request<{ revoked: boolean }>("/auth/logout", { method: "POST" });
