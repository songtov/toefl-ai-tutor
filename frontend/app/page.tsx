"use client";

import { type ReactNode, useEffect, useState } from "react";
import {
  type Answer,
  type AuthStatus,
  MANAGE_USAGE_URL,
  type SessionDetail,
  type Post,
  type SetSummary,
  type Task,
  type TaskDetail,
  USAGE_LIMIT_MESSAGE,
  describeError,
  getAuthStatus,
  getSession,
  listSets,
  login,
  logout,
  openSet,
  submitAnswer,
} from "@/lib/api";

const CRITERION_LABELS: Record<string, string> = {
  task_completion: "Task completion",
  organization: "Organization",
  language_use: "Language use",
  tone_and_register: "Tone & register",
  relevance_and_contribution: "Relevance & contribution",
  development: "Development",
};

const TYPE_LABELS: Record<Task["type"], string> = {
  build_a_sentence: "Build a Sentence",
  write_an_email: "Write an Email",
  academic_discussion: "Academic Discussion",
};

const BAR_BUTTON =
  "rounded border border-white/70 px-4 py-1.5 text-sm font-semibold text-white hover:bg-white/10 disabled:opacity-40 disabled:hover:bg-transparent";

const AUTHORIZE_ORIGIN = "https://auth.openai.com";

const countWords = (text: string) => (text.trim() ? text.trim().split(/\s+/).length : 0);

const BLANK = "_";

const blankCount = (template: string) => template.split(" ").filter((w) => w === BLANK).length;

export default function Home() {
  const [sets, setSets] = useState<SetSummary[]>([]);
  const [setId, setSetId] = useState<number | null>(null);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [index, setIndex] = useState(0);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [orders, setOrders] = useState<Record<number, string[]>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [auth, setAuth] = useState<AuthStatus | null>(null);

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    const result = new URLSearchParams(window.location.search).get("auth");
    if (result) window.history.replaceState(null, "", window.location.pathname);
    getAuthStatus().then(
      (status) => {
        setAuth(status);
        if (result && result !== "ok") setError(`Sign-in failed: ${describeError(result)}`);
        if (status.signed_in) listSets().then(setSets, (e) => setError(String(e)));
      },
      (e) => setError(String(e)),
    );
  }, []);

  const onLogin = () =>
    run("Opening ChatGPT sign-in…", async () => {
      const { authorize_url } = await login();
      if (new URL(authorize_url).origin !== AUTHORIZE_ORIGIN) throw new Error("Unexpected sign-in URL");
      window.location.assign(authorize_url);
    });

  const onLogout = () =>
    run("Signing out…", async () => {
      const { revoked } = await logout();
      setAuth(await getAuthStatus());
      setSets([]);
      setDetail(null);
      if (!revoked) {
        throw new Error(
          "Signed out locally, but OpenAI did not confirm revocation. You can disconnect this app in ChatGPT Settings.",
        );
      }
    });

  const ready = auth?.signed_in === true && auth.plan_enabled;
  const account = (
    <AccountMenu auth={auth} onLogin={onLogin} onLogout={onLogout} disabled={busy !== null} />
  );

  const onOpenSet = (id: number) =>
    run("Loading…", async () => {
      const session = await openSet(id);
      setDetail(await getSession(session.id));
      setSetId(id);
      setIndex(0);
    });

  const onExit = () =>
    run("Loading…", async () => {
      setDetail(null);
      setSets(await listSets());
    });

  const isDrafted = (t: TaskDetail) =>
    t.answer_text !== null ||
    (t.type === "build_a_sentence"
      ? (orders[t.id] ?? []).length === blankCount(t.content.template)
      : (drafts[t.id] ?? "").trim() !== "");

  const pending = detail?.tasks.filter((t) => t.answer_text === null) ?? [];
  const allDrafted = pending.every(isDrafted);

  const onSubmitSet = () =>
    run("Scoring your set…", async () => {
      if (!detail) return;
      const results = await Promise.allSettled(
        pending.map((t) =>
          submitAnswer(
            t.id,
            t.type === "build_a_sentence" ? { chunks: orders[t.id] } : { text: drafts[t.id] },
          ),
        ),
      );
      setDetail(await getSession(detail.id));
      const failed = results.filter((r) => r.status === "rejected");
      if (failed.length) throw new Error(`${failed.length} answer(s) failed to score. Submit again to retry.`);
    });

  if (auth && !auth.signed_in) {
    return <SignIn onLogin={onLogin} busy={busy} error={error} />;
  }

  if (!detail) {
    return (
      <Shell
        title="Writing Practice"
        actions={account}
        subLeft="Writing | Sets"
        subRight={`${sets.length} set(s)`}
        busy={busy}
        error={error}
      >
        {auth && <SetList sets={sets} onOpen={onOpenSet} disabled={busy !== null} />}
      </Shell>
    );
  }

  const task = detail.tasks[index];
  const last = index === detail.tasks.length - 1;
  const results = detail.tasks.flatMap((t) => (t.result ? [{ type: t.type, ...t.result }] : []));
  const done = results.length === detail.tasks.length;
  const summary = (Object.keys(TYPE_LABELS) as Task["type"][]).map((type) => {
    const ofType = results.filter((r) => r.type === type);
    const total = (key: "score" | "max_score") => ofType.reduce((sum, r) => sum + r[key], 0);
    return `${TYPE_LABELS[type]} ${total("score")}/${total("max_score")}`;
  });

  return (
    <Shell
      title={`Set ${setId}`}
      actions={
        <>
          {account}
          <button onClick={onExit} disabled={busy !== null} className={BAR_BUTTON}>
            Exit
          </button>
          <button onClick={() => setIndex(index - 1)} disabled={busy !== null || index === 0} className={BAR_BUTTON}>
            Back
          </button>
          {last && pending.length > 0 ? (
            <button
              onClick={onSubmitSet}
              disabled={busy !== null || !allDrafted || !ready}
              title={
                !ready
                  ? "Sign in with ChatGPT first"
                  : allDrafted
                    ? undefined
                    : "Answer every question before submitting"
              }
              className={`${BAR_BUTTON} border-transparent bg-exam-accent hover:bg-exam-accent/80`}
            >
              Submit Set
            </button>
          ) : (
            <button onClick={() => setIndex(index + 1)} disabled={busy !== null || last} className={BAR_BUTTON}>
              Next
            </button>
          )}
        </>
      }
      subLeft={`Writing | ${TYPE_LABELS[task.type]}`}
      subRight={
        <div className="flex items-center gap-3">
          {done && <span className="font-semibold">{summary.join(" · ")}</span>}
          <div className="flex flex-wrap gap-1">
            {detail.tasks.map((t, i) => (
              <button
                key={t.id}
                onClick={() => setIndex(i)}
                disabled={busy !== null}
                aria-current={i === index}
                className={`h-7 w-7 rounded border text-xs font-semibold ${
                  i === index
                    ? "border-exam-bar bg-exam-bar text-white"
                    : isDrafted(t)
                      ? "border-exam-line bg-white"
                      : "border-dashed border-exam-line bg-transparent"
                }`}
              >
                {i + 1}
              </button>
            ))}
          </div>
          <span>
            Question {index + 1} of {detail.tasks.length}
          </span>
        </div>
      }
      busy={busy}
      error={error}
    >
      {task.type === "build_a_sentence" ? (
        <SentenceView
          key={task.id}
          task={task}
          order={orders[task.id] ?? []}
          onOrder={(order) => setOrders({ ...orders, [task.id]: order })}
          disabled={busy !== null}
        />
      ) : (
        <WritingView
          task={task}
          draft={drafts[task.id] ?? ""}
          onDraft={(text) => setDrafts({ ...drafts, [task.id]: text })}
          disabled={busy !== null}
        />
      )}
    </Shell>
  );
}

function Shell({
  title,
  actions,
  subLeft,
  subRight,
  busy,
  error,
  children,
}: {
  title: string;
  actions: ReactNode;
  subLeft: ReactNode;
  subRight: ReactNode;
  busy: string | null;
  error: string | null;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex flex-wrap items-center justify-between gap-3 bg-exam-bar px-4 py-2.5 text-white sm:px-6">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-bold tracking-wide">English AI Tutor</span>
          <span className="text-sm text-white/70">{title}</span>
        </div>
        <div className="flex gap-2">{actions}</div>
      </header>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-exam-line bg-exam-subbar px-4 py-1.5 text-sm sm:px-6">
        <span className="font-semibold">{subLeft}</span>
        {subRight}
      </div>
      {busy && <p className="bg-exam-panel px-6 py-2 text-sm">{busy}</p>}
      {error && (
        <p role="alert" className="border-b border-red-300 bg-red-50 px-6 py-2 text-sm text-red-800">
          {error}
          {error === USAGE_LIMIT_MESSAGE && (
            <>
              {" "}
              <ManageUsageLink className="font-semibold underline" />
            </>
          )}
        </p>
      )}
      <main className="flex flex-1 flex-col">{children}</main>
    </div>
  );
}

function SignIn({
  onLogin,
  busy,
  error,
}: {
  onLogin: () => void;
  busy: string | null;
  error: string | null;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-exam-panel">
      <header className="bg-exam-bar px-4 py-2.5 text-white sm:px-6">
        <span className="text-sm font-bold tracking-wide">English AI Tutor</span>
      </header>
      <main className="flex flex-1 items-center justify-center p-4">
        <div className="w-full max-w-sm space-y-6 rounded border border-exam-line bg-white p-8 text-center shadow-sm">
          <p className="text-sm text-neutral-600">
            Practice the TOEFL Writing section with rubric scores and sentence-level corrections.
          </p>
          <button
            onClick={onLogin}
            disabled={busy !== null}
            className="w-full rounded bg-exam-bar px-4 py-3 font-semibold text-white hover:bg-exam-bar/90 disabled:opacity-40"
          >
            {busy ?? "Continue with ChatGPT"}
          </button>
          <p className="text-xs text-neutral-500">
            New here? Continuing creates your account. Practice runs on your ChatGPT plan.
          </p>
          {error && (
            <p role="alert" className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
              {error}
            </p>
          )}
        </div>
      </main>
    </div>
  );
}

function ManageUsageLink({ className }: { className: string }) {
  return (
    <a href={MANAGE_USAGE_URL} target="_blank" rel="noopener noreferrer" className={className}>
      Manage usage
    </a>
  );
}

function AccountMenu({
  auth,
  onLogin,
  onLogout,
  disabled,
}: {
  auth: AuthStatus | null;
  onLogin: () => void;
  onLogout: () => void;
  disabled: boolean;
}) {
  if (auth === null) return null;
  const continueButton = (
    <button onClick={onLogin} disabled={disabled} className={BAR_BUTTON}>
      Continue with ChatGPT
    </button>
  );
  return (
    <div className="flex items-center gap-3 text-xs text-white/80">
      {auth.plan_enabled ? (
        <span>
          Using ChatGPT plan · {auth.email} ·{" "}
          <ManageUsageLink className="underline hover:text-white" />
        </span>
      ) : (
        <>
          <span>{auth.email}</span>
          {continueButton}
        </>
      )}
      <button onClick={onLogout} disabled={disabled} className={BAR_BUTTON}>
        Sign out
      </button>
    </div>
  );
}

function SetList({
  sets,
  onOpen,
  disabled,
}: {
  sets: SetSummary[];
  onOpen: (id: number) => void;
  disabled: boolean;
}) {
  return (
    <div className="mx-auto w-full max-w-3xl p-4 sm:p-6">
      <table className="w-full border border-exam-line text-sm">
        <thead className="bg-exam-subbar text-left">
          <tr>
            <th className="px-3 py-2">Set</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {sets.map((s) => (
            <tr key={s.id} className="border-t border-exam-line">
              <td className="px-3 py-2 font-semibold">Set {s.id}</td>
              <td className="px-3 py-2">
                {s.answered_count === s.task_count
                  ? "Scored"
                  : s.answered_count === 0
                    ? `Not started · ${s.task_count} questions`
                    : `${s.answered_count}/${s.task_count} scored`}
              </td>
              <td className="px-3 py-2 text-right">
                <button
                  onClick={() => onOpen(s.id)}
                  disabled={disabled}
                  className="rounded border border-exam-bar px-3 py-1 font-semibold text-exam-bar hover:bg-exam-subbar disabled:opacity-40"
                >
                  {s.answered_count === s.task_count ? "Review" : "Enter"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SentenceView({
  task,
  order,
  onOrder,
  disabled,
}: {
  task: TaskDetail & { type: "build_a_sentence" };
  order: string[];
  onOrder: (order: string[]) => void;
  disabled: boolean;
}) {
  const { context, template, chunks } = task.content;
  const words = template.split(" ");
  const slotOf = words.map((w, i) => (w === BLANK ? words.slice(0, i).filter((x) => x === BLANK).length : -1));
  const unused = [...order];
  const available = chunks.filter((c) => {
    const i = unused.indexOf(c);
    if (i === -1) return true;
    unused.splice(i, 1);
    return false;
  });
  const answered = task.answer_text !== null;

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 p-4 text-[15px] leading-relaxed sm:p-6">
      <p className="text-sm italic">Directions: Move the words into the blanks to make an appropriate sentence.</p>
      <p className="font-semibold">{context}</p>
      {answered ? (
        <p className="border border-exam-line bg-exam-panel p-3">{task.answer_text}</p>
      ) : (
        <>
          <p className="flex flex-wrap items-center gap-x-2 gap-y-3">
            {words.map((w, i) =>
              slotOf[i] === -1 ? (
                <span key={i}>{w}</span>
              ) : (
                <button
                  key={i}
                  onClick={() => onOrder(order.filter((_, j) => j !== slotOf[i]))}
                  disabled={disabled || order[slotOf[i]] === undefined}
                  title="Remove"
                  className="min-w-16 border-b-2 border-exam-bar px-2 text-center font-semibold disabled:opacity-100"
                >
                  {order[slotOf[i]] ?? "\u00a0"}
                </button>
              ),
            )}
          </p>
          <div className="flex flex-wrap gap-2">
            {available.map((c, i) => (
              <button
                key={`${c}-${i}`}
                onClick={() => onOrder([...order, c])}
                disabled={disabled || order.length === blankCount(template)}
                className="rounded border border-exam-line bg-white px-3 py-1 hover:border-exam-bar disabled:opacity-40"
              >
                {c}
              </button>
            ))}
          </div>
        </>
      )}
      {task.result && (
        <div className="space-y-1 border-t border-exam-line pt-4 text-sm">
          <p className={`font-semibold ${task.result.score ? "text-green-700" : "text-red-700"}`}>
            {task.result.score ? "Correct" : "Incorrect"}
          </p>
          {!task.result.score && <p>Answer: {task.result.correct_answer}</p>}
        </div>
      )}
    </div>
  );
}

function WritingView({
  task,
  draft,
  onDraft,
  disabled,
}: {
  task: TaskDetail & { type: "write_an_email" | "academic_discussion" };
  draft: string;
  onDraft: (text: string) => void;
  disabled: boolean;
}) {
  const text = task.answer_text ?? draft;
  const words = countWords(text);
  const offTarget =
    task.type === "write_an_email" ? words < 80 || words > 120 : words < 100;

  return (
    <div className="grid flex-1 lg:grid-cols-2">
      <section className="space-y-4 border-exam-line bg-exam-panel p-4 text-[15px] leading-relaxed sm:p-6 lg:border-r">
        {task.type === "write_an_email" ? (
          <>
            <p className="text-sm italic">
              Directions: Read the situation and write an email. You should write 80–120 words in complete sentences.
            </p>
            <p>{task.content.situation}</p>
            <p>
              Write an email to <strong>{task.content.recipient}</strong>. In your email, do the following:
            </p>
            <ul className="list-disc space-y-1 pl-6">
              {task.content.requirements.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </>
        ) : (
          <>
            <p className="text-sm italic">
              Directions: Your professor is teaching a class on {task.content.course}. Write a post responding to the
              professor&apos;s question. Express and support your opinion, and make a contribution to the discussion in
              your own words. An effective response will contain at least 100 words.
            </p>
            {[task.content.professor, ...task.content.students].map((p: Post) => (
              <div key={p.name} className="space-y-1 border border-exam-line bg-white p-3">
                <p className="font-semibold">{p.name}</p>
                <p>{p.post}</p>
              </div>
            ))}
          </>
        )}
      </section>

      <section className="flex flex-col p-4 sm:p-6">
        <div className="flex items-center justify-between border border-b-0 border-exam-line bg-exam-subbar px-3 py-1 text-xs">
          <span className="font-semibold">{task.answer_text === null ? "Your Response" : "Submitted Response"}</span>
          <span className={task.answer_text === null && offTarget ? "text-amber-700" : ""}>Word Count: {words}</span>
        </div>
        <textarea
          value={text}
          onChange={(e) => onDraft(e.target.value)}
          readOnly={task.answer_text !== null}
          disabled={disabled}
          rows={14}
          spellCheck={false}
          className="w-full flex-1 resize-none border border-exam-line bg-white p-3 text-[15px] leading-relaxed outline-none focus:border-exam-accent read-only:bg-exam-panel"
        />
        {task.result && <ResultView result={task.result} />}
      </section>
    </div>
  );
}

function ResultView({ result }: { result: Answer }) {
  return (
    <div className="mt-6 space-y-5 text-sm">
      <div className="flex items-baseline gap-2 border-b border-exam-line pb-2">
        <span className="text-3xl font-bold">{result.score}</span>
        <span>/ {result.max_score}</span>
      </div>

      <dl className="space-y-3">
        {result.criteria.map((c) => (
          <div key={c.criterion}>
            <dt className="font-semibold">{CRITERION_LABELS[c.criterion] ?? c.criterion}</dt>
            <dd className="text-neutral-700">{c.rationale}</dd>
          </div>
        ))}
      </dl>

      <div className="space-y-3">
        <h3 className="font-semibold">Corrections</h3>
        {result.corrections.length === 0 && <p className="text-neutral-600">No errors found.</p>}
        {result.corrections.map((c, i) => (
          <div key={i} className="space-y-1 border border-exam-line p-3">
            <p className="text-red-700 line-through">{c.original}</p>
            <p className="text-green-700">{c.corrected}</p>
            <p className="text-neutral-700">{c.reason}</p>
            <div className="flex flex-wrap gap-1">
              {c.error_types.map((t) => (
                <span key={t} className="rounded bg-exam-subbar px-2 py-0.5 font-mono text-xs">
                  {t}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      <p className="font-mono text-xs text-neutral-500">
        {result.usage.input_tokens} in / {result.usage.output_tokens} out tokens · ${result.usage.cost_usd.toFixed(4)}
      </p>
    </div>
  );
}
