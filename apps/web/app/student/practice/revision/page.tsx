"use client";

import { Suspense, useState, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  Loader2, RefreshCw, Target, Clock, TrendingDown, Sparkles,
  AlertCircle, CheckCircle2, XCircle, ChevronRight, RotateCcw,
  BookOpen, ArrowLeft, Brain, Trophy, Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  practiceApi,
  RevisionFocus,
  RevisionSummary,
  RevisionSessionResponse,
  AnswerResult,
  REVISION_SIGNAL_LABELS,
} from "@/lib/api/practice";
import { useRevisionSummary } from "@/lib/practice-hooks";
import { useOptionalStudentContext } from "@/contexts/StudentContext";
import { ApiError } from "@/lib/api/client";
import { practiceError } from "@/lib/practice-errors";

// ─── Types ────────────────────────────────────────────────────────────────────
interface AnsweredState {
  selected: string;
  is_correct: boolean;
  correct_option: string;
  explanation: string;
}

const SIGNAL_META: {
  key: keyof Omit<RevisionSummary, "total_available">;
  label: string;
  icon: typeof Clock;
  focus: RevisionFocus;
  color: string;
  bg: string;
  border: string;
}[] = [
  { key: "overdue",              label: "Due for Review",    icon: Clock,        focus: "overdue",              color: "text-blue-500",   bg: "bg-blue-500/10",   border: "border-blue-500/30" },
  { key: "repeatedly_incorrect", label: "Repeated Mistakes", icon: RefreshCw,    focus: "repeatedly_incorrect", color: "text-red-500",    bg: "bg-red-500/10",    border: "border-red-500/30" },
  { key: "recent_mistakes",      label: "Recent Mistakes",   icon: TrendingDown, focus: "recent_mistakes",      color: "text-orange-500", bg: "bg-orange-500/10", border: "border-orange-500/30" },
  { key: "weak_topics",          label: "Weak Topics",       icon: Target,       focus: "weak_topics",          color: "text-yellow-500", bg: "bg-yellow-500/10", border: "border-yellow-500/30" },
];

const SIGNAL_COLOR: Record<string, { badge: string; dot: string }> = {
  overdue:              { badge: "bg-blue-500/15 text-blue-600 dark:text-blue-400",       dot: "bg-blue-500" },
  repeatedly_incorrect: { badge: "bg-red-500/15 text-red-600 dark:text-red-400",         dot: "bg-red-500" },
  recent_mistakes:      { badge: "bg-orange-500/15 text-orange-600 dark:text-orange-400", dot: "bg-orange-500" },
  weak_topics:          { badge: "bg-yellow-500/15 text-yellow-600 dark:text-yellow-400", dot: "bg-yellow-500" },
};

const OPTIONS = ["a", "b", "c", "d"] as const;
const OPTION_LABELS: Record<string, string> = { a: "A", b: "B", c: "C", d: "D" };

// ─── Progress ring ─────────────────────────────────────────────────────────
function ProgressRing({ done, total, correct }: { done: number; total: number; correct: number }) {
  const r = 26;
  const circ = 2 * Math.PI * r;
  const pct = total > 0 ? done / total : 0;
  const accuracy = done > 0 ? Math.round((correct / done) * 100) : 0;
  const stroke = accuracy >= 70 ? "#22c55e" : accuracy >= 40 ? "#f59e0b" : "#ef4444";
  return (
    <div className="relative w-16 h-16 flex-shrink-0">
      <svg className="w-16 h-16 -rotate-90" viewBox="0 0 64 64">
        <circle cx="32" cy="32" r={r} fill="none" stroke="currentColor" strokeWidth="5" className="text-muted/30" />
        <circle cx="32" cy="32" r={r} fill="none" stroke={stroke} strokeWidth="5"
          strokeDasharray={`${pct * circ} ${circ}`} strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.4s ease" }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[11px] font-bold text-primary dark:text-foreground leading-none">{done}/{total}</span>
        <span className="text-[9px] text-muted-foreground leading-none mt-0.5">{accuracy}%</span>
      </div>
    </div>
  );
}

// ─── Question Card ────────────────────────────────────────────────────────────
function QuestionCard({
  question, questionNum, totalQuestions, signal, answered, onAnswer,
}: {
  question: { id: number; text: string; option_a: string; option_b: string; option_c: string; option_d: string };
  questionNum: number; totalQuestions: number; signal?: string;
  answered: AnsweredState | null; onAnswer: (opt: string) => Promise<void>;
}) {
  const [submitting, setSubmitting] = useState<string | null>(null);
  const signalStyle = signal ? SIGNAL_COLOR[signal] : null;

  const handleSelect = async (opt: string) => {
    if (answered || submitting) return;
    setSubmitting(opt);
    await onAnswer(opt);
    setSubmitting(null);
  };

  const optText = (opt: string) =>
    ({ a: question.option_a, b: question.option_b, c: question.option_c, d: question.option_d } as Record<string, string>)[opt] ?? "";

  return (
    <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden animate-in fade-in-50 slide-in-from-bottom-4 duration-400">
      <div className="px-5 pt-5 pb-4 border-b border-border/60 flex items-center gap-3">
        <span className="text-xs font-semibold text-muted-foreground">{questionNum} / {totalQuestions}</span>
        {signalStyle && (
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold ${signalStyle.badge}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${signalStyle.dot}`} />
            {REVISION_SIGNAL_LABELS[signal!] ?? signal}
          </span>
        )}
      </div>
      <div className="px-5 py-5">
        <p className="text-[15px] font-medium text-primary dark:text-foreground leading-relaxed">{question.text}</p>
      </div>
      <div className="px-5 pb-5 space-y-2.5">
        {OPTIONS.map((opt) => {
          const isSelected = answered?.selected === opt;
          const isCorrect = answered?.correct_option?.toLowerCase() === opt;
          const wasWrong = answered && isSelected && !isCorrect;
          const isCorrectNotSelected = answered && !isSelected && isCorrect;
          let cls = "w-full flex items-start gap-3 p-3.5 rounded-[12px] border text-left transition-all duration-200 ";
          if (!answered && !submitting) cls += "border-border bg-background hover:border-primary/60 hover:bg-primary/5 cursor-pointer";
          else if (!answered && submitting === opt) cls += "border-primary/60 bg-primary/5 cursor-wait";
          else if (isCorrect) cls += "border-green-500 bg-green-500/10 cursor-default";
          else if (wasWrong) cls += "border-red-500 bg-red-500/10 cursor-default";
          else if (isCorrectNotSelected) cls += "border-green-500/40 bg-green-500/5 cursor-default";
          else cls += "border-border/50 bg-muted/30 opacity-60 cursor-default";
          return (
            <button key={opt} className={cls} onClick={() => handleSelect(opt)} disabled={!!answered || !!submitting}>
              <span className={`flex-shrink-0 w-7 h-7 rounded-full border-2 flex items-center justify-center text-xs font-bold transition-colors ${
                isCorrect ? "border-green-500 bg-green-500 text-white"
                : wasWrong ? "border-red-500 bg-red-500 text-white"
                : "border-border text-muted-foreground"
              }`}>{OPTION_LABELS[opt]}</span>
              <span className="text-[14px] text-primary dark:text-foreground leading-relaxed pt-0.5 flex-1">{optText(opt)}</span>
              {isCorrect && <CheckCircle2 className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" />}
              {wasWrong && <XCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />}
            </button>
          );
        })}
      </div>
      {answered && answered.explanation && (
        <div className={`mx-5 mb-5 p-4 rounded-[10px] border ${answered.is_correct ? "bg-green-500/8 border-green-500/20" : "bg-orange-500/8 border-orange-500/20"}`}>
          <p className="text-[13px] text-primary dark:text-foreground leading-relaxed">
            <span className="font-semibold">{answered.is_correct ? "✓ Correct! " : "✗ Incorrect. "}</span>
            {answered.explanation}
          </p>
        </div>
      )}
    </div>
  );
}

// ─── Results Screen ───────────────────────────────────────────────────────────
function ResultsScreen({ total, correct, incorrect, skipped, onRestart }: {
  total: number; correct: number; incorrect: number; skipped: number; onRestart: () => void;
}) {
  const router = useRouter();
  const accuracy = total > 0 ? Math.round((correct / total) * 100) : 0;
  const grade =
    accuracy >= 80 ? { label: "Excellent!", color: "text-green-500", Icon: Trophy }
    : accuracy >= 60 ? { label: "Good work!", color: "text-blue-500", Icon: Zap }
    : { label: "Keep Going!", color: "text-orange-500", Icon: Brain };
  return (
    <div className="p-4 md:p-8 max-w-[640px] mx-auto animate-in fade-in-50 duration-500 space-y-6">
      <div className="bg-card rounded-2xl border border-border shadow-sm p-8 text-center space-y-4">
        <grade.Icon className={`w-12 h-12 mx-auto ${grade.color}`} />
        <div>
          <p className={`text-4xl font-black ${grade.color}`}>{accuracy}%</p>
          <p className="text-lg font-bold text-primary dark:text-foreground mt-1">{grade.label}</p>
          <p className="text-sm text-muted-foreground mt-1">Revision session complete</p>
        </div>
        <div className="grid grid-cols-3 gap-3 mt-4">
          {[
            { label: "Correct", value: correct, color: "text-green-500", bg: "bg-green-500/10" },
            { label: "Incorrect", value: incorrect, color: "text-red-500", bg: "bg-red-500/10" },
            { label: "Skipped", value: skipped, color: "text-muted-foreground", bg: "bg-muted/30" },
          ].map((s) => (
            <div key={s.label} className={`${s.bg} rounded-[10px] p-3`}>
              <p className={`text-2xl font-black ${s.color}`}>{s.value}</p>
              <p className="text-xs text-muted-foreground font-medium">{s.label}</p>
            </div>
          ))}
        </div>
        {accuracy < 70 && (
          <p className="text-sm text-muted-foreground bg-orange-500/8 border border-orange-500/20 rounded-[10px] p-3">
            💡 Keep practicing — your revision queue will update based on today&apos;s answers and show these topics again at the right time.
          </p>
        )}
      </div>
      <div className="flex flex-col sm:flex-row gap-3">
        <Button onClick={onRestart} className="flex-1 h-12 rounded-[12px] bg-primary text-white hover:bg-[#163E6B] font-bold gap-2">
          <RotateCcw className="w-4 h-4" /> Revise Again
        </Button>
        <Button variant="outline" onClick={() => router.push("/student/practice")} className="flex-1 h-12 rounded-[12px] gap-2">
          <BookOpen className="w-4 h-4" /> Back to Practice
        </Button>
      </div>
    </div>
  );
}

// ─── Main Revision Content ────────────────────────────────────────────────────
function RevisionContent() {
  const searchParams = useSearchParams();
  const requestedFocus = searchParams.get("focus") as RevisionFocus | null;
  const router = useRouter();
  const studentCtx = useOptionalStudentContext();
  const courseId = studentCtx?.activeCourse?.id ?? null;

  const summaryQuery = useRevisionSummary(courseId);
  const summary = summaryQuery.data ?? null;
  const loading = summaryQuery.isLoading;
  const summaryError = summaryQuery.isError ? practiceError(summaryQuery.error, "load").message : null;

  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [session, setSession] = useState<RevisionSessionResponse | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, AnsweredState>>({});
  const [done, setDone] = useState(false);

  const handleStart = async (focus?: RevisionFocus) => {
    setStarting(true);
    setStartError(null);
    try {
      const data = await practiceApi.startRevision(focus, courseId);
      setSession(data);
      setCurrentIndex(0);
      setAnswers({});
      setDone(false);
    } catch (e) {
      const pe = practiceError(e, "start");
      const detail = e instanceof ApiError && typeof (e as ApiError & { data?: { detail?: string } }).data?.detail === "string"
        ? (e as ApiError & { data?: { detail?: string } }).data!.detail as string : null;
      setStartError(pe.kind === "no-questions" && detail ? detail : pe.message);
    } finally {
      setStarting(false);
    }
  };

  const handleAnswer = useCallback(async (opt: string) => {
    if (!session) return;
    const q = session.questions[currentIndex];
    if (!q) return;
    const result: AnswerResult = await practiceApi.saveAnswer(session.session.id, {
      question_id: q.id, selected_option: opt, is_marked_for_review: false,
    });
    if (result.is_correct !== undefined) {
      setAnswers((prev) => ({
        ...prev,
        [q.id]: {
          selected: opt, is_correct: result.is_correct!,
          correct_option: result.correct_option ?? "", explanation: result.explanation ?? "",
        },
      }));
    }
  }, [session, currentIndex]);

  const handleNext = () => {
    if (!session) return;
    if (currentIndex + 1 >= session.questions.length) setDone(true);
    else setCurrentIndex((i) => i + 1);
  };

  const handleRestart = () => {
    setSession(null); setCurrentIndex(0); setAnswers({}); setDone(false); setStartError(null);
    summaryQuery.refetch();
  };

  // Loading
  if (loading) {
    return (
      <div className="p-4 md:p-8 max-w-[800px] mx-auto space-y-8" aria-busy="true">
        <div className="space-y-3 animate-pulse">
          <div className="h-8 w-56 rounded bg-muted" />
          <div className="h-4 w-full rounded bg-muted" />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 animate-pulse">
          {[0, 1, 2, 3].map((i) => <div key={i} className="h-28 rounded-[14px] bg-muted" />)}
        </div>
      </div>
    );
  }

  // Error
  if (summaryError && !session) {
    return (
      <div className="p-4 md:p-8 max-w-[800px] mx-auto">
        <div className="bg-card rounded-[16px] border border-border shadow-sm p-10 text-center space-y-4" role="alert">
          <AlertCircle className="w-8 h-8 text-red-500 mx-auto" />
          <p className="font-semibold text-primary dark:text-foreground">{summaryError}</p>
          <Button variant="outline" onClick={() => summaryQuery.refetch()}>Retry</Button>
        </div>
      </div>
    );
  }

  // Results
  if (done && session) {
    const correct = Object.values(answers).filter((a) => a.is_correct).length;
    const incorrect = Object.values(answers).filter((a) => !a.is_correct).length;
    const skipped = session.questions.length - Object.keys(answers).length;
    return <ResultsScreen total={session.questions.length} correct={correct} incorrect={incorrect} skipped={skipped} onRestart={handleRestart} />;
  }

  // Active quiz
  if (session) {
    const q = session.questions[currentIndex];
    if (!q) return null;
    const answeredState = answers[q.id] ?? null;
    const totalAnswered = Object.keys(answers).length;
    const totalCorrect = Object.values(answers).filter((a) => a.is_correct).length;
    const signal = session.question_signals?.[String(q.id)];
    return (
      <div className="p-4 md:p-8 max-w-[760px] mx-auto space-y-5 animate-in fade-in-50 duration-400">
        <div className="flex items-center gap-4">
          <button onClick={handleRestart} className="p-2 rounded-[10px] text-muted-foreground hover:text-primary hover:bg-muted/50 transition-colors" aria-label="Exit">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-[17px] font-bold text-primary dark:text-foreground truncate">Revision Mode</h1>
            <p className="text-xs text-muted-foreground">Adaptive — based on your performance history</p>
          </div>
          <ProgressRing done={totalAnswered} total={session.questions.length} correct={totalCorrect} />
        </div>
        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
          <div className="h-full bg-primary rounded-full transition-all duration-500"
            style={{ width: `${(currentIndex / session.questions.length) * 100}%` }} />
        </div>
        <QuestionCard
          question={q} questionNum={currentIndex + 1} totalQuestions={session.questions.length}
          signal={signal} answered={answeredState} onAnswer={handleAnswer}
        />
        <div className="flex gap-3">
          {!answeredState && (
            <Button variant="outline" onClick={handleNext} className="flex-1 h-11 rounded-[12px] text-muted-foreground">
              Skip
            </Button>
          )}
          {answeredState && (
            <Button onClick={handleNext} className="flex-1 h-11 rounded-[12px] bg-primary text-white hover:bg-[#163E6B] font-bold gap-2">
              {currentIndex + 1 >= session.questions.length ? "See Results" : "Next Question"}
              <ChevronRight className="w-4 h-4" />
            </Button>
          )}
        </div>
      </div>
    );
  }

  // Landing
  const hasAnything = !!summary && summary.total_available > 0;
  return (
    <div className="p-4 md:p-8 max-w-[800px] mx-auto space-y-8 animate-in fade-in-50 duration-500">
      <div className="flex items-start gap-3">
        <button onClick={() => router.push("/student/practice")} className="p-2 rounded-[10px] text-muted-foreground hover:text-primary hover:bg-muted/50 transition-colors mt-0.5">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-[26px] font-black tracking-tight text-primary dark:text-foreground flex items-center gap-2.5">
            <Sparkles className="w-7 h-7 text-[#D4A72C]" /> Revision Mode
          </h1>
          <p className="text-muted-foreground mt-1 text-[14px] max-w-prose">
            Your personal revision queue — built automatically from your mistakes, weak topics, repeated errors, and questions due for a spaced review.
          </p>
        </div>
      </div>

      {!hasAnything ? (
        <div className="bg-card rounded-2xl border border-border shadow-sm p-12 text-center space-y-3">
          <Brain className="w-10 h-10 mx-auto text-muted-foreground/50" />
          <p className="font-bold text-primary dark:text-foreground text-[17px]">Nothing to revise yet</p>
          <p className="text-muted-foreground text-[14px] max-w-md mx-auto">
            Answer some questions in Practice or Study mode — we&apos;ll build your revision queue automatically from what you get wrong and what&apos;s due for review.
          </p>
          <Button variant="outline" onClick={() => router.push("/student/practice")} className="mt-4 gap-2">
            <BookOpen className="w-4 h-4" /> Go to Practice
          </Button>
        </div>
      ) : (
        <>
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Quick-start by signal</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {SIGNAL_META.map((s) => {
                const count = summary![s.key];
                const active = count > 0;
                return (
                  <button key={s.key} onClick={() => active && !starting && handleStart(s.focus)}
                    disabled={!active || starting}
                    className={`flex flex-col items-center gap-2 p-5 rounded-[14px] border transition-all text-center ${
                      active ? `${s.bg} ${s.border} hover:scale-[1.03] cursor-pointer hover:shadow-md` : "border-border/50 bg-muted/30 opacity-40 cursor-not-allowed"
                    }`}>
                    <s.icon className={`w-5 h-5 ${active ? s.color : "text-muted-foreground"}`} />
                    <span className={`text-3xl font-black ${active ? "text-primary dark:text-foreground" : "text-muted-foreground"}`}>{count}</span>
                    <span className="text-[11px] font-semibold text-muted-foreground leading-tight">{s.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {startError && (
            <div className="flex items-center gap-2 p-3 rounded-[10px] bg-red-500/10 border border-red-500/20">
              <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
              <p className="text-sm text-red-600 dark:text-red-400 font-medium">{startError}</p>
            </div>
          )}

          <Button onClick={() => handleStart(requestedFocus || undefined)} disabled={starting}
            className="w-full h-14 rounded-[14px] bg-primary text-white hover:bg-[#163E6B] font-bold text-[16px] gap-3 shadow-lg shadow-primary/20">
            {starting ? <Loader2 className="w-5 h-5 animate-spin" /> : (
              <><Sparkles className="w-5 h-5" /> Start Revising ({summary!.total_available} question{summary!.total_available === 1 ? "" : "s"})</>
            )}
          </Button>

          <p className="text-center text-xs text-muted-foreground">
            Questions are mixed from all signals for the best experience. Choose a signal above to prioritise that area.
          </p>
        </>
      )}
    </div>
  );
}

export default function RevisionPage() {
  return (
    <Suspense fallback={<div className="flex justify-center p-8"><Loader2 className="w-8 h-8 animate-spin" /></div>}>
      <RevisionContent />
    </Suspense>
  );
}


