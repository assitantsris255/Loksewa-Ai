"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { BookOpen, Loader2, RotateCcw, Sparkles, AlertCircle, ChevronRight as ChevronRightIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { practiceApi, StudyPage } from "@/lib/api/practice";
import { TopicPracticeBrowser, QuestionSkeleton, readStoredPageSize } from "@/components/practice/TopicPracticeBrowser";
import { usePracticeExams, useSavedQuestions, practiceResultKey } from "@/lib/practice-hooks";
import { useOptionalStudentContext } from "@/contexts/StudentContext";
import { ExamListStatus } from "@/components/practice/ExamListStatus";
import { practiceError, PracticeError } from "@/lib/practice-errors";

export default function TopicStudyPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const studentCtx = useOptionalStudentContext();
  const courseId = studentCtx?.activeCourse?.id ?? null;
  // Syllabus + saved questions come from the shared query cache, so coming
  // back to Practice shows them instantly instead of refetching.
  const examsQuery = usePracticeExams();
  const exams = useMemo(() => examsQuery.data ?? [], [examsQuery.data]);
  const loadingExams = examsQuery.isPending;
  const { savedIds: savedQuestionIds, toggle: toggleSave } = useSavedQuestions();
  const [exam, setExam] = useState("");
  const [subject, setSubject] = useState("");
  const [topic, setTopic] = useState("");
  const [shuffleQuestions, setShuffleQuestions] = useState(false);

  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<PracticeError | null>(null);
  const [session, setSession] = useState<StudyPage | null>(null);

  useEffect(() => {
    if (!exam && exams.length > 0) {
      // Prioritize exams that have active subjects available for study
      const examWithSubjects = exams.find(e => (e.subjects?.length ?? 0) > 0) ?? exams[0];
      if (examWithSubjects?.id) {
        setExam(examWithSubjects.id.toString());
      }
    }
  }, [exams, exam]);

  const activeExam = useMemo(() => exams.find(e => e.id.toString() === exam), [exam, exams]);
  const activeSubject = useMemo(() => activeExam?.subjects?.find(s => s.id.toString() === subject), [activeExam, subject]);
  const allTopics = useMemo(
    () => (((activeSubject?.units ?? (activeSubject as any)?.chapters ?? []) as any[]).flatMap((u: any) => u.topics || [])) as any[],
    [activeSubject]
  );
  const activeUnit = useMemo(
    () => (((activeSubject?.units ?? (activeSubject as any)?.chapters ?? []) as any[])?.find((u: any) => (u.topics || []).some((t: any) => t.id.toString() === topic))) as any,
    [activeSubject, topic]
  );

  const handleStart = async (restart = false) => {
    if (!topic || starting) return;
    setStarting(true);
    setError(null);
    try {
      const data = await practiceApi.startStudy({
        topic, subject, exam, course: courseId, restart,
        shuffle_questions: shuffleQuestions,
        page_size: readStoredPageSize(),
      });
      // A restart replaces the question set: drop pages cached for the old one.
      queryClient.removeQueries({ queryKey: ["practice-study-page"] });
      setShuffleQuestions(Boolean(data.session.shuffle_questions));
      setSession(data);
    } catch (e) {
      console.error(e);
      setError(practiceError(e, "start"));
    } finally {
      setStarting(false);
    }
  };

  // First load: show the practice shell straight away with skeleton cards,
  // rather than leaving the student on a button spinner.
  if (starting && !session) {
    return (
      <div className="p-4 md:p-8 max-w-[1200px] mx-auto space-y-6" aria-busy="true">
        <div>
          <h1 className="text-[22px] font-bold tracking-tight text-primary dark:text-foreground">
            {allTopics.find((t: any) => t.id.toString() === topic)?.name || "Topic"}
          </h1>
          <p className="text-muted-foreground text-[14px]">Loading your questions…</p>
        </div>
        <div className="max-w-[860px] mx-auto"><QuestionSkeleton count={3} /></div>
      </div>
    );
  }

  if (session) {
    const topicName = allTopics.find((t: any) => t.id.toString() === topic)?.name;
    return (
      <div className="p-4 md:p-8 max-w-[1200px] mx-auto space-y-6 animate-in fade-in-50 duration-500">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <nav className="flex items-center flex-wrap gap-1 text-[12px] font-bold uppercase tracking-wider text-muted-foreground mb-1">
              {[activeExam?.title, activeSubject?.name, activeUnit?.title, "Topic-wise Practice"]
                .filter(Boolean)
                .map((crumb, i, arr) => (
                  <span key={i} className="flex items-center gap-1">
                    {crumb}
                    {i < arr.length - 1 && <ChevronRightIcon className="w-3 h-3" />}
                  </span>
                ))}
            </nav>
            <h1 className="text-[22px] font-bold tracking-tight text-primary dark:text-foreground">
              {topicName || "Topic"}
            </h1>
            <p className="text-muted-foreground text-[14px]">
              Browse freely — no timer, no fixed count. Answer if you&apos;re confident, or View Answer to just learn it.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-muted-foreground">
              Shuffle {session.session.shuffle_questions ? "On" : "Off"}
            </span>
            {session.resumed && (
              <span className="text-xs font-bold uppercase tracking-wider text-[#D4A72C] bg-[#D4A72C]/10 px-3 py-1.5 rounded-full">
                Resumed
              </span>
            )}
            <Button variant="outline" size="sm" onClick={() => handleStart(true)}>
              <RotateCcw className="w-4 h-4 mr-2" /> Start Over
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setSession(null)}>
              Change Topic
            </Button>
          </div>
        </div>

        {error && (
          <p className="text-sm text-red-500 font-medium" role="alert">{error.message}</p>
        )}

        {starting ? (
          <div className="max-w-[860px] mx-auto"><QuestionSkeleton count={3} /></div>
        ) : (
          <TopicPracticeBrowser
            key={session.session.id}
            initial={session}
            savedQuestionIds={savedQuestionIds}
            onToggleSave={toggleSave}
            onFinish={async () => {
              // The browser shows the (network / server) message next to the
              // Finish button; rethrow so it can.
              const finished = await practiceApi.submitSession(session.session.id, 0);
              // Hand the result page the payload we already have.
              queryClient.setQueryData(practiceResultKey(session.session.id), finished);
              router.push(`/student/practice/results/${session.session.id}`);
            }}
          />
        )}
      </div>
    );
  }

  return (
    <div className="p-4 md:p-8 max-w-[700px] mx-auto space-y-8 animate-in fade-in-50 duration-500">
      <div>
        <h1 className="text-[28px] font-bold tracking-tight text-primary dark:text-foreground flex items-center gap-3">
          <Sparkles className="w-7 h-7 text-[#D4A72C]" /> Study by Topic
        </h1>
        <p className="text-muted-foreground mt-1 text-[15px]">
          Pick a topic and go through its questions at your own pace. No timer, no required count, no exam pressure.
        </p>
      </div>

      <div className="bg-card rounded-[16px] border border-border shadow-sm p-6 md:p-8 space-y-5">
        <div className="space-y-2">
          <label className="text-[13px] font-bold text-muted-foreground uppercase tracking-wider block">Exam</label>
          <select
            value={exam}
            onChange={(e) => { setExam(e.target.value); setSubject(""); setTopic(""); }}
            className="w-full h-12 px-3 bg-muted border border-border rounded-[10px] text-[15px] font-medium text-foreground outline-none focus:border-primary focus:ring-1 focus:ring-primary dark:focus:border-[#D4A72C] dark:focus:ring-[#D4A72C]"
            disabled={loadingExams}
          >
            <option value="">Select an exam</option>
            {exams.map(e => <option key={e.id} value={e.id}>{e.display_name ?? e.title}</option>)}
          </select>
        </div>

        <div className="space-y-2">
          <label className="text-[13px] font-bold text-muted-foreground uppercase tracking-wider block">Subject</label>
          <select
            value={subject}
            onChange={(e) => { setSubject(e.target.value); setTopic(""); }}
            className="w-full h-12 px-3 bg-muted border border-border rounded-[10px] text-[15px] font-medium text-foreground outline-none focus:border-primary focus:ring-1 focus:ring-primary dark:focus:border-[#D4A72C] dark:focus:ring-[#D4A72C]"
            disabled={!activeExam || (activeExam?.subjects?.length ?? 0) === 0}
          >
            <option value="">
              {!activeExam
                ? "Select an exam first"
                : (activeExam?.subjects?.length ?? 0) === 0
                ? "No subjects available for this exam"
                : "Select a subject"}
            </option>
            {activeExam?.subjects?.map((s: any) => (
              <option key={s.id} value={s.id.toString()}>
                {s.name || s.title}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <label className="text-[13px] font-bold text-muted-foreground uppercase tracking-wider block">Topic</label>
          <select
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="w-full h-12 px-3 bg-muted border border-border rounded-[10px] text-[15px] font-medium text-foreground outline-none focus:border-primary focus:ring-1 focus:ring-primary dark:focus:border-[#D4A72C] dark:focus:ring-[#D4A72C]"
            disabled={!activeSubject || allTopics.length === 0}
          >
            <option value="">
              {!activeSubject
                ? "Select a subject first"
                : allTopics.length === 0
                ? "No topics available for this subject"
                : "Select a topic"}
            </option>
            {allTopics.map((t: any) => (
              <option key={t.id} value={t.id.toString()}>
                {t.name || t.title}
              </option>
            ))}
          </select>
        </div>

        <ExamListStatus
          isError={examsQuery.isError}
          isEmpty={!loadingExams && !examsQuery.isError && exams.length === 0}
          onRetry={() => examsQuery.refetch()}
        />

        <label className="flex items-center justify-between gap-4 border border-border rounded-[10px] px-4 py-3 text-sm font-medium text-primary dark:text-foreground">
          <span>Shuffle Questions</span>
          <span className="flex items-center gap-3 text-muted-foreground">
            {shuffleQuestions ? "On" : "Off"}
            <input
              type="checkbox"
              checked={shuffleQuestions}
              onChange={(event) => setShuffleQuestions(event.target.checked)}
              className="h-4 w-4 accent-primary"
              aria-label="Shuffle Questions"
            />
          </span>
        </label>

        {error && (
          <div className="flex items-center gap-2 text-sm text-red-600 font-medium" role="alert">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error.message}</span>
            {error.retryable && (
              <button type="button" className="underline font-bold" onClick={() => handleStart(false)}>Retry</button>
            )}
          </div>
        )}

        <Button
          onClick={() => handleStart(false)}
          disabled={!topic || starting}
          className="w-full h-14 rounded-[12px] bg-primary text-primary-foreground hover:bg-[#163E6B] text-white font-bold text-[16px]"
        >
          {starting ? <Loader2 className="w-5 h-5 animate-spin" /> : <><BookOpen className="w-5 h-5 mr-2" /> Start Studying</>}
        </Button>
      </div>
    </div>
  );
}
