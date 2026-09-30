"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, AlertCircle, FileText } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useOptionalStudentContext } from "@/contexts/StudentContext";
import { AcademicHierarchyNode, ExaminationRequest, studentExamsApi } from "@/lib/api/student-exams";

export default function RequestSubjectiveExamPage() {
  const studentContext = useOptionalStudentContext();
  const courseId = studentContext?.activeCourse?.id;
  const [academicExamId, setAcademicExamId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [topicId, setTopicId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [submittedRequest, setSubmittedRequest] = useState<ExaminationRequest | null>(null);

  const {
    data: hierarchy = [],
    isLoading: isLoadingHierarchy,
    isError: hierarchyError,
    refetch: retryHierarchy,
  } = useQuery({
    queryKey: ["student-subjective-request-hierarchy", courseId ?? null],
    queryFn: () => studentExamsApi.getAcademicHierarchy(courseId),
    enabled: !studentContext?.isLoading,
  });
  const { data: requests = [], refetch: refetchRequests } = useQuery({
    queryKey: ["student-exam-requests"],
    queryFn: studentExamsApi.getExamRequests,
    enabled: !studentContext?.isLoading,
  });

  const academicExams = useMemo(
    () => hierarchy.flatMap((category: AcademicHierarchyNode) => category.exams || []),
    [hierarchy],
  );
  const academicExam = academicExams.find((item) => String(item.id) === academicExamId);
  const subjects = useMemo(
    () => (academicExam?.papers || []).flatMap((paper) => paper.subjects || []),
    [academicExam],
  );
  const subject = subjects.find((item) => String(item.id) === subjectId);
  const topics = (subject?.chapters || []).flatMap((chapter) => chapter.topics || []);
  const existingRequest = submittedRequest || requests.find(
    (item) => item.request_type === "subjective_live" && item.academic_exam === Number(academicExamId),
  );

  const submitRequest = async () => {
    if (!academicExamId) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      const result = await studentExamsApi.requestSubjectiveExam({
        academic_exam: Number(academicExamId),
        ...(courseId ? { course: courseId } : {}),
        ...(subjectId ? { subject: Number(subjectId) } : {}),
        ...(topicId ? { topic: Number(topicId) } : {}),
      });
      setSubmittedRequest(result);
      await refetchRequests();
      toast.success("Subjective exam request submitted.");
    } catch (error) {
      const detail = typeof error === "object" && error !== null && "data" in error
        && typeof error.data === "object" && error.data !== null && "detail" in error.data
        && typeof error.data.detail === "string" ? error.data.detail : "Could not submit this request.";
      setSubmitError(detail);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-4 md:p-8">
      <Link href="/student/exams" className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="mr-2 h-4 w-4" /> Mock Tests
      </Link>
      <header className="border-b border-border pb-5">
        <div className="mb-2 flex items-center gap-2 text-sm font-medium text-emerald-700 dark:text-emerald-300"><FileText className="h-4 w-4" /> Subjective examinations</div>
        <h1 className="text-2xl font-bold text-primary dark:text-foreground">Request a Subjective Live Exam</h1>
      </header>

      {hierarchyError ? (
        <div className="flex items-center gap-3 border-y border-destructive/30 py-4 text-sm" role="alert">
          <AlertCircle className="h-4 w-4" />Could not load your authorized exams.
          <Button variant="outline" size="sm" onClick={() => void retryHierarchy()}>Retry</Button>
        </div>
      ) : isLoadingHierarchy ? (
        <p className="py-8 text-sm text-muted-foreground" aria-live="polite">Loading authorized exams...</p>
      ) : academicExams.length === 0 ? (
        <p className="border-y border-border py-10 text-center text-sm text-muted-foreground">No authorized academic exams are available for this course.</p>
      ) : (
        <section className="grid gap-5 sm:grid-cols-2">
          <label className="space-y-1.5 text-sm font-medium">
            Academic exam
            <select value={academicExamId} onChange={(event) => { setAcademicExamId(event.target.value); setSubjectId(""); setTopicId(""); setSubmittedRequest(null); }} className="h-10 w-full rounded-md border border-input bg-background px-3">
              <option value="">Choose an exam</option>
              {academicExams.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Subject (optional)
            <select value={subjectId} onChange={(event) => { setSubjectId(event.target.value); setTopicId(""); }} disabled={!academicExamId} className="h-10 w-full rounded-md border border-input bg-background px-3">
              <option value="">Any subject</option>
              {subjects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="space-y-1.5 text-sm font-medium sm:col-span-2">
            Topic (optional)
            <select value={topicId} onChange={(event) => setTopicId(event.target.value)} disabled={!subjectId} className="h-10 w-full rounded-md border border-input bg-background px-3">
              <option value="">Any topic in subject</option>
              {topics.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
        </section>
      )}

      {submitError && <p className="text-sm text-destructive" role="alert">{submitError}</p>}
      {existingRequest && (
        <section className="border-y border-border py-4" aria-live="polite">
          <p className="font-semibold text-primary dark:text-foreground">Request {existingRequest.status}</p>
          <p className="mt-1 text-sm text-muted-foreground">{existingRequest.examination_title}</p>
          {existingRequest.rejection_reason && <p className="mt-1 text-sm text-muted-foreground">{existingRequest.rejection_reason}</p>}
          {existingRequest.status === "approved" && existingRequest.examination && (
            <Link href={`/student/exams/${existingRequest.examination}`} className="mt-3 inline-flex text-sm font-semibold text-primary underline-offset-4 hover:underline">
              Open Subjective Exam
            </Link>
          )}
        </section>
      )}
      <Button
        disabled={!academicExamId || submitting || isLoadingHierarchy || existingRequest?.status === "pending" || existingRequest?.status === "approved"}
        onClick={() => void submitRequest()}
      >
        {submitting ? "Submitting..." : existingRequest?.status === "pending" ? "Request Pending" : existingRequest?.status === "approved" ? "Request Approved" : existingRequest ? "Request Again" : "Request Admin for Exam"}
      </Button>
    </main>
  );
}