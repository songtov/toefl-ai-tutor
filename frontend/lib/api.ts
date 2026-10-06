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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `${res.status} ${res.statusText}`);
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
