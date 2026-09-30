"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download, FileText, RotateCcw, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { adminExamApi, AdminCourseOption, SubjectivePaperGenerationResult } from "@/lib/api/admin-exams";
import { adminSyllabusApi } from "@/lib/api/admin-syllabus";
import { Button } from "@/components/ui/button";

const GENERATION_KEY_STORAGE = "admin.subjectiveLiveExamGenerationKey";

interface SyllabusTopic {
  id: number;
  name: string;
}

interface SyllabusChapter {
  topics?: SyllabusTopic[];
}

interface SyllabusSubject {
  id: number;
  name: string;
  chapters?: SyllabusChapter[];
}

interface SyllabusPaper {
  subjects?: SyllabusSubject[];
}

interface SyllabusPosition {
  id: number;
  name: string;
  children?: SyllabusPosition[];
  papers?: SyllabusPaper[];
}

interface SyllabusCategory {
  positions?: SyllabusPosition[];
}

function getErrorDetail(error: unknown, fallback: string) {
  if (typeof error !== "object" || error === null) return fallback;
  const data = "data" in error ? error.data : null;
  if (typeof data === "object" && data !== null && "detail" in data && typeof data.detail === "string") {
    return data.detail;
  }
  return fallback;
}

function flattenPositions(nodes: SyllabusPosition[], result: SyllabusPosition[] = []): SyllabusPosition[] {
  for (const node of nodes) {
    result.push(node);
    flattenPositions(node.children || [], result);
  }
  return result;
}

export default function SubjectiveExamGeneratorPage() {
  const searchParams = useSearchParams();
  const requestId = Number(searchParams.get("request")) || undefined;
  const generationKeyStorage = requestId ? `${GENERATION_KEY_STORAGE}:${requestId}` : GENERATION_KEY_STORAGE;
  const [generationKey, setGenerationKey] = useState("");
  const [examId, setExamId] = useState("");
  const [courseId, setCourseId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [topicId, setTopicId] = useState("");
  const [title, setTitle] = useState("");
  const [questionCount, setQuestionCount] = useState(10);
  const [timeLimit, setTimeLimit] = useState(90);
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [instructions, setInstructions] = useState("");
  const [questionType, setQuestionType] = useState<"subjective" | "objective" | "mixed">("subjective");
  const [result, setResult] = useState<SubjectivePaperGenerationResult | null>(null);
  const [generating, setGenerating] = useState(false);
  const requestKeyRef = useRef<string | null>(null);

  const { data: linkedRequest } = useQuery({
    queryKey: ["admin-exam-request", requestId],
    queryFn: () => adminExamApi.getExamRequest(requestId!),
    enabled: !!requestId,
  });

  const { data: tree = [], isLoading: treeLoading, isError: treeError, refetch: reloadTree } = useQuery({
    queryKey: ["admin-subjective-generator-syllabus"],
    queryFn: async () => await adminSyllabusApi.getTreeCached() as SyllabusCategory[],
  });
  const { data: courses = [], isLoading: coursesLoading } = useQuery({
    queryKey: ["admin-subjective-generator-courses"],
    queryFn: () => adminExamApi.getPublishedCourses(),
  });

  const positions = useMemo(() => flattenPositions(tree.flatMap((category) => category.positions || [])), [tree]);
  const position = positions.find((item) => String(item.id) === examId);
  const subjects = useMemo<SyllabusSubject[]>(() => {
    const byId = new Map<number, SyllabusSubject>();
    for (const paper of position?.papers || []) {
      for (const syllabusSubject of paper.subjects || []) byId.set(syllabusSubject.id, syllabusSubject);
    }
    return Array.from(byId.values());
  }, [position]);
  const subject = subjects.find((item) => String(item.id) === subjectId);
  const topics: SyllabusTopic[] = (subject?.chapters || []).flatMap((chapter) => chapter.topics || []);
  const matchingCourses = courses.filter((course: AdminCourseOption) => course.exam?.id === Number(examId));

  useEffect(() => {
    let key = sessionStorage.getItem(generationKeyStorage);
    if (!key) {
      key = crypto.randomUUID();
      sessionStorage.setItem(generationKeyStorage, key);
    }
    requestKeyRef.current = key;
    setGenerationKey(key);
  }, [generationKeyStorage]);

  useEffect(() => {
    if (!linkedRequest || linkedRequest.request_type !== "subjective_live") return;
    if (linkedRequest.academic_exam) setExamId(String(linkedRequest.academic_exam));
    if (linkedRequest.course) setCourseId(String(linkedRequest.course));
    if (linkedRequest.subject) setSubjectId(String(linkedRequest.subject));
    if (linkedRequest.topic) setTopicId(String(linkedRequest.topic));
  }, [linkedRequest]);

  const startNewDraft = () => {
    const key = crypto.randomUUID();
    sessionStorage.setItem(generationKeyStorage, key);
    requestKeyRef.current = key;
    setGenerationKey(key);
    setResult(null);
  };

  const generate = async (regenerate: boolean) => {
    if (!examId || !generationKey) return;
    setGenerating(true);
    try {
      const generated = await adminExamApi.generateSubjectiveLiveExam({
        generation_key: generationKey,
        ...(requestId ? { request_id: requestId } : {}),
        exam: Number(examId),
        ...(courseId ? { course: Number(courseId) } : {}),
        ...(subjectId ? { subject: Number(subjectId) } : {}),
        ...(topicId ? { topic: Number(topicId) } : {}),
        title: title.trim() || `${position?.name || "Subjective"} Subjective Live Exam`,
        question_count: questionCount,
        time_limit: timeLimit,
        start_time: startTime ? new Date(startTime).toISOString() : null,
        end_time: endTime ? new Date(endTime).toISOString() : null,
        instructions,
        question_type: questionType,
        regenerate,
      });
      setResult(generated);
      toast.success(generated.reused ? "Existing draft restored." : regenerate ? "Draft paper regenerated." : "Draft paper generated.");
    } catch (error: unknown) {
      toast.error(getErrorDetail(error, "Could not generate the subjective paper."));
    } finally {
      setGenerating(false);
    }
  };

  const openPaper = async () => {
    if (!result) return;
    try {
      const file = await adminExamApi.getQuestionPaperBlob(result.id);
      const fileUrl = URL.createObjectURL(file);
      window.open(fileUrl, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(fileUrl), 60_000);
    } catch {
      toast.error("Could not open the generated question paper.");
    }
  };

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-4 md:p-8">
      <Link href="/admin-dashboard/academic/questions" className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="mr-2 h-4 w-4" /> Subjective Question Bank
      </Link>
      <header className="border-b border-border pb-5">
        <div className="mb-2 flex items-center gap-2 text-sm font-medium text-indigo-700 dark:text-indigo-300"><Wand2 className="h-4 w-4" /> Admin exam preparation</div>
        <h1 className="text-2xl font-bold text-primary dark:text-foreground">Generate Subjective Live Exam</h1>
        {linkedRequest && <p className="mt-2 text-sm text-muted-foreground">Preparing for {linkedRequest.student_name}&apos;s request #{linkedRequest.id}</p>}
      </header>

      {treeError ? (
        <div className="flex items-center gap-3 border-y border-destructive/30 py-4 text-sm" role="alert">
          <span>Could not load the academic hierarchy.</span>
          <Button variant="outline" size="sm" onClick={() => void reloadTree()}>Retry</Button>
        </div>
      ) : (
        <section className="grid gap-5 sm:grid-cols-2">
          <label className="space-y-1.5 text-sm font-medium">
            Academic exam
            <select value={examId} onChange={(event) => { setExamId(event.target.value); setCourseId(""); setSubjectId(""); setTopicId(""); }} disabled={treeLoading} className="h-10 w-full rounded-md border border-input bg-background px-3">
              <option value="">Select exam</option>
              {positions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Published course
            <select value={courseId} onChange={(event) => setCourseId(event.target.value)} disabled={!examId || coursesLoading} className="h-10 w-full rounded-md border border-input bg-background px-3">
              <option value="">All authorized students for this exam</option>
              {matchingCourses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}
            </select>
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Subject (optional)
            <select value={subjectId} onChange={(event) => { setSubjectId(event.target.value); setTopicId(""); }} disabled={!examId} className="h-10 w-full rounded-md border border-input bg-background px-3">
              <option value="">All subjects</option>
              {subjects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Topic (optional)
            <select value={topicId} onChange={(event) => setTopicId(event.target.value)} disabled={!subjectId} className="h-10 w-full rounded-md border border-input bg-background px-3">
              <option value="">All topics in subject</option>
              {topics.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="space-y-1.5 text-sm font-medium sm:col-span-2">
            Paper title
            <input value={title} onChange={(event) => setTitle(event.target.value)} className="h-10 w-full rounded-md border border-input bg-background px-3" placeholder={`${position?.name || "Exam"} Subjective Live Exam`} />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Question style
            <select value={questionType} onChange={(event) => setQuestionType(event.target.value as typeof questionType)} className="h-10 w-full rounded-md border border-input bg-background px-3">
              <option value="subjective">Descriptive</option>
              <option value="objective">Objective-style questions</option>
              <option value="mixed">Mixed question bank</option>
            </select>
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Question count
            <input type="number" min={1} max={200} value={questionCount} onChange={(event) => setQuestionCount(Number(event.target.value))} className="h-10 w-full rounded-md border border-input bg-background px-3" />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Duration (minutes)
            <input type="number" min={1} max={1440} value={timeLimit} onChange={(event) => setTimeLimit(Number(event.target.value))} className="h-10 w-full rounded-md border border-input bg-background px-3" />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Available from
            <input type="datetime-local" value={startTime} onChange={(event) => setStartTime(event.target.value)} className="h-10 w-full rounded-md border border-input bg-background px-3" />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Available until
            <input type="datetime-local" value={endTime} onChange={(event) => setEndTime(event.target.value)} className="h-10 w-full rounded-md border border-input bg-background px-3" />
          </label>
          <label className="space-y-1.5 text-sm font-medium sm:col-span-2">
            Instructions
            <textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} rows={3} className="w-full rounded-md border border-input bg-background px-3 py-2" />
          </label>
        </section>
      )}

      <div className="flex flex-wrap gap-2 border-t border-border pt-5">
        <Button disabled={!examId || !generationKey || generating || treeLoading} onClick={() => void generate(false)}>
          <Wand2 className="mr-2 h-4 w-4" />{generating ? "Generating..." : "Generate Draft Paper"}
        </Button>
        {result && (
          <>
            <Button variant="outline" disabled={generating || result.status !== "draft"} onClick={() => void generate(true)}>
              <RotateCcw className="mr-2 h-4 w-4" />Regenerate Questions
            </Button>
            <Button variant="outline" onClick={() => void openPaper()}>
              <Download className="mr-2 h-4 w-4" />Open PDF
            </Button>
            <Link href={`/admin-dashboard/exams/new?draft=${result.id}`}>
              <Button variant="outline"><FileText className="mr-2 h-4 w-4" />Review Draft</Button>
            </Link>
            {!requestId && <Button variant="ghost" onClick={startNewDraft}>New paper</Button>}
          </>
        )}
      </div>

      {result && (
        <section className="space-y-2 border-y border-border py-4" aria-live="polite">
          <h2 className="font-semibold text-primary dark:text-foreground">{result.title}</h2>
          <p className="text-sm text-muted-foreground">
            {result.status.toUpperCase()} · {result.total_questions} questions · {result.total_marks} marks · {result.time_limit} minutes
            {result.has_question_paper ? ` · PDF stored (${result.question_paper_page_count} pages)` : " · PDF unavailable"}
          </p>
          <p className="text-sm text-muted-foreground">The paper is a draft. Review the PDF and exam details before publishing.</p>
        </section>
      )}
    </main>
  );
}