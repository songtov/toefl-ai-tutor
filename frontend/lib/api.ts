export type Session = {
  id: number;
  plan_reason: string;
  task_ids: number[];
  cost_usd: number;
};

export type Post = { name: string; post: string };

type TaskBase = { id: number; difficulty: string; directions: string };

export type Task =
  | (TaskBase & { type: "build_a_sentence"; content: { context: string; template: string; chunks: string[] } })
  | (TaskBase & {
      type: "write_an_email";
      content: { situation: string; recipient: string; requirements: string[] };
    })
  | (TaskBase & { type: "academic_discussion"; content: { course: string; professor: Post; students: Post[] } });

export type Answer = {
  result_id: number;
  score: number;
  max_score: number;
  criteria: { criterion: string; rationale: string }[];
  corrections: {
    original: string;
    corrected: string;
    reason: string;
    error_types: string[];
  }[];
  correct_answer: string | null;
  usage: { input_tokens: number; output_tokens: number; cost_usd: number };
};

export type SetSummary = {
  id: number;
  task_count: number;
  session_id: number | null;
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

export const listSets = () => request<SetSummary[]>("/sets");

export const openSet = (setId: number) => request<Session>(`/sets/${setId}/session`, { method: "POST" });

export const getSession = (sessionId: number) => request<SessionDetail>(`/sessions/${sessionId}`);

export const submitAnswer = (taskId: number, answer: { text: string } | { chunks: string[] }) =>
  request<Answer>(`/tasks/${taskId}/answer`, {
    method: "POST",
    body: JSON.stringify(answer),
  });

export const getAuthStatus = () => request<AuthStatus>("/auth/status");

export const login = () => request<{ authorize_url: string }>("/auth/login", { method: "POST" });

export const logout = () => request<{ revoked: boolean }>("/auth/logout", { method: "POST" });
