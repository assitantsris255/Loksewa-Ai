"use client";

import React, { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, ChevronLeft, ChevronRight, Download, Eye, ExternalLink,
  Sparkles, Save, CheckCircle2, AlertCircle, Clock, ZoomIn, ZoomOut,
  Maximize2, Minimize2, FileText, Check, Loader2, Award, User, RefreshCw,
  BookOpen, Edit3, MessageSquare, Plus, Trash2, X, AlertTriangle, ShieldCheck
} from "lucide-react";
import { adminExamApi, AdminSubjectiveSubmissionDetail } from "@/lib/api/admin-exams";
import toast from "react-hot-toast";

interface QuestionScoreItem {
  question_number: number;
  max_marks: number | string;
  marks_obtained: number | string;
  feedback: string;
}

export default function SubmissionEvaluationPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const params = useParams<{ id: string; attemptId: string }>();
  const examId = Number(params?.id);
  const attemptId = Number(params?.attemptId);

  // Active view tab on mobile/small screens: 'viewer' | 'evaluation' | 'ocr'
  const [mobileTab, setMobileTab] = useState<"viewer" | "evaluation" | "ocr">("evaluation");
  // Active right column tab on desktop: 'evaluation' | 'ocr'
  const [activeTab, setActiveTab] = useState<"evaluation" | "ocr">("evaluation");

  // PDF Viewer state
  const [zoomLevel, setZoomLevel] = useState<number>(100);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [loadingPdf, setLoadingPdf] = useState(false);

  // Form State
  const [evaluatorFeedback, setEvaluatorFeedback] = useState<string>("");
  const [extractedText, setExtractedText] = useState<string>("");
  const [questionScores, setQuestionScores] = useState<QuestionScoreItem[]>([]);

  // Publish Modal State
  const [showPublishModal, setShowPublishModal] = useState<boolean>(false);
  const [editPublishedConfirmed, setEditPublishedConfirmed] = useState<boolean>(false);

  // Fetch submission details by attempt ID
  // Fetch submission details by attempt ID or submission ID
  const {
    data: submission,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["admin", "subjective-submission", attemptId],
    queryFn: async () => {
      try {
        return await adminExamApi.getSubjectiveSubmissionByAttempt(attemptId);
      } catch (err: any) {
        return await adminExamApi.getSubjectiveSubmission(attemptId);
      }
    },
    enabled: Number.isFinite(attemptId) && attemptId > 0,
  });

  // Populate local form state when submission loads
  useEffect(() => {
    if (!submission) return;
    setEvaluatorFeedback(submission.evaluator_feedback ?? "");
    setExtractedText(submission.extracted_text || submission.raw_ocr_text || "");

    if (submission.question_scores && submission.question_scores.length > 0) {
      setQuestionScores(
        submission.question_scores.map((qs, idx) => ({
          question_number: idx + 1,
          marks_obtained: qs.marks_obtained,
          max_marks: qs.max_marks > 0 ? qs.max_marks : 10,
          feedback: qs.feedback || "",
        }))
      );
    } else {
      // Default to 3 clean questions if none exist yet
      setQuestionScores([
        { question_number: 1, marks_obtained: 0, max_marks: 10, feedback: "" },
        { question_number: 2, marks_obtained: 0, max_marks: 10, feedback: "" },
        { question_number: 3, marks_obtained: 0, max_marks: 10, feedback: "" },
      ]);
    }
  }, [submission]);

  // Load Answer Sheet PDF Blob for streaming preview
  useEffect(() => {
    if (!submission?.id || !submission.has_answer_pdf) return;
    let active = true;
    setLoadingPdf(true);
    adminExamApi
      .getAnswerSheetBlob(submission.id)
      .then((blob) => {
        if (!active) return;
        const url = URL.createObjectURL(blob);
        setPdfUrl(url);
      })
      .catch(() => {
        if (active) toast.error("Could not load answer sheet PDF preview.");
      })
      .finally(() => {
        if (active) setLoadingPdf(false);
      });

    return () => {
      active = false;
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    };
  }, [submission?.id, submission?.has_answer_pdf]);

  // Real-time authoritative calculation helpers
  const totalMaxMarks = useMemo(() => {
    return questionScores.reduce((sum, q) => sum + (Number(q.max_marks) || 0), 0);
  }, [questionScores]);

  const totalObtainedMarks = useMemo(() => {
    return questionScores.reduce((sum, q) => sum + (Number(q.marks_obtained) || 0), 0);
  }, [questionScores]);

  const calculatedPercentage = useMemo(() => {
    if (totalMaxMarks <= 0) return "0.00";
    return ((totalObtainedMarks / totalMaxMarks) * 100).toFixed(2);
  }, [totalObtainedMarks, totalMaxMarks]);

  const passMarks = useMemo(() => {
    return totalMaxMarks * 0.4;
  }, [totalMaxMarks]);

  const isPassing = useMemo(() => {
    return totalMaxMarks > 0 && totalObtainedMarks >= passMarks;
  }, [totalObtainedMarks, passMarks, totalMaxMarks]);

  // Question validation check
  const getQuestionError = (q: QuestionScoreItem) => {
    if (q.max_marks === "" || Number(q.max_marks) <= 0) return "Maximum marks must be greater than 0";
    if (q.marks_obtained !== "" && Number(q.marks_obtained) < 0) return "Obtained marks cannot be negative";
    if (q.marks_obtained !== "" && q.max_marks !== "" && Number(q.marks_obtained) > Number(q.max_marks)) {
      return `Obtained marks (${q.marks_obtained}) cannot exceed maximum marks (${q.max_marks})`;
    }
    return null;
  };

  const validationErrors = useMemo(() => {
    const errors: { index: number; qNum: number; error: string }[] = [];
    if (questionScores.length === 0) {
      errors.push({ index: -1, qNum: 0, error: "Please add at least one question." });
    }
    questionScores.forEach((q, idx) => {
      const err = getQuestionError(q);
      if (err) {
        errors.push({ index: idx, qNum: q.question_number, error: err });
      }
    });
    return errors;
  }, [questionScores]);

  const hasErrors = validationErrors.length > 0;

  // Question List Management Handlers
  const handleAddQuestion = () => {
    const nextQNum = questionScores.length + 1;
    // Sensible default: 10 marks
    setQuestionScores((prev) => [
      ...prev,
      {
        question_number: nextQNum,
        max_marks: 10,
        marks_obtained: 0,
        feedback: "",
      },
    ]);
    toast.success(`Question #${nextQNum} added`);
  };

  const handleDeleteQuestion = (indexToDelete: number) => {
    if (questionScores.length <= 1) {
      toast.error("An exam must have at least one question.");
      return;
    }
    setQuestionScores((prev) => {
      const filtered = prev.filter((_, idx) => idx !== indexToDelete);
      // Renumber questions sequentially: 1, 2, 3...
      return filtered.map((item, idx) => ({
        ...item,
        question_number: idx + 1,
      }));
    });
    toast.success("Question removed and numbering updated.");
  };

  const handleUpdateQuestion = (
    index: number,
    field: keyof QuestionScoreItem,
    value: string | number
  ) => {
    setQuestionScores((prev) =>
      prev.map((item, idx) => {
        if (idx !== index) return item;
        return { ...item, [field]: value };
      })
    );
  };

  // OCR Mutation
  const ocrMutation = useMutation({
    mutationFn: () => adminExamApi.runOcr(submission!.id),
    onSuccess: (updated) => {
      queryClient.setQueryData(["admin", "subjective-submission", attemptId], updated);
      setExtractedText(updated.extracted_text || updated.raw_ocr_text || "");
      toast.success("AI handwriting transcription completed!");
    },
    onError: (err: any) => {
      toast.error(err?.data?.error || err?.data?.detail || "OCR transcription failed.");
    },
  });

  // Update Transcription text mutation
  const updateTranscriptionMutation = useMutation({
    mutationFn: () => adminExamApi.updateTranscription(submission!.id, extractedText),
    onSuccess: (updated) => {
      queryClient.setQueryData(["admin", "subjective-submission", attemptId], updated);
      toast.success("Transcription saved.");
    },
    onError: () => toast.error("Failed to save transcription."),
  });

  // Evaluate / Save Draft Mutation
  const evaluateMutation = useMutation({
    mutationFn: async (editPublished: boolean = false) => {
      const payload: any = {
        evaluator_feedback: evaluatorFeedback,
        question_scores: questionScores.map((q, idx) => ({
          question_number: idx + 1,
          max_marks: Number(q.max_marks),
          marks_obtained: Number(q.marks_obtained),
          feedback: q.feedback,
        })),
      };
      if (submission?.is_published || editPublished) {
        payload.edit_published = true;
      }
      return await adminExamApi.evaluateSubmission(submission!.id, payload);
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(["admin", "subjective-submission", attemptId], updated);
      queryClient.invalidateQueries({ queryKey: ["admin", "exam", examId, "submissions"] });
      toast.success("Evaluation draft saved successfully.");
    },
    onError: (err: any) => {
      toast.error(err?.data?.detail || err?.data?.error || "Failed to save evaluation draft.");
    },
  });

  // Publish Mutation
  const publishMutation = useMutation({
    mutationFn: async () => {
      // 1. Ensure latest evaluation draft is saved
      const payload: any = {
        evaluator_feedback: evaluatorFeedback,
        question_scores: questionScores.map((q, idx) => ({
          question_number: idx + 1,
          max_marks: Number(q.max_marks),
          marks_obtained: Number(q.marks_obtained),
          feedback: q.feedback,
        })),
        edit_published: true,
      };
      await adminExamApi.evaluateSubmission(submission!.id, payload);
      // 2. Publish to student
      return await adminExamApi.publishSubmission(submission!.id);
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(["admin", "subjective-submission", attemptId], updated);
      queryClient.invalidateQueries({ queryKey: ["admin", "exam", examId, "submissions"] });
      setShowPublishModal(false);
      toast.success("Result published to student! Candidate has been notified.");
    },
    onError: (err: any) => {
      toast.error(err?.data?.detail || err?.data?.error || "Failed to publish result.");
    },
  });

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3">
        <Loader2 className="w-8 h-8 animate-spin text-[#0B2545]" />
        <p className="text-sm text-slate-500 font-medium">Loading candidate submission &amp; answer sheets...</p>
      </div>
    );
  }

  if (error || !submission) {
    return (
      <div className="p-8 text-center max-w-md mx-auto space-y-4">
        <AlertCircle className="w-12 h-12 text-rose-500 mx-auto" />
        <h2 className="text-lg font-bold text-slate-900">Submission Not Found</h2>
        <p className="text-sm text-slate-500">
          The requested subjective examination attempt does not exist or has no uploaded answer sheet.
        </p>
        <Link
          href={`/admin-dashboard/exams/${examId}/submissions`}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-[#0B2545] text-white text-sm font-medium rounded-lg"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Submissions
        </Link>
      </div>
    );
  }

  const isPublished = submission.is_published;
  const isEvaluated = submission.status === "evaluated";

  return (
    <div className="space-y-4 pb-12">
      {/* Top Header & Breadcrumb */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            href={`/admin-dashboard/exams/${examId}/submissions`}
            className="p-2 rounded-lg text-slate-500 hover:text-[#0B2545] hover:bg-slate-100 transition-colors"
            title="Back to Exam Submissions"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-lg font-bold text-[#0B2545]">{submission.student_name}</h1>
              {isPublished ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Published
                </span>
              ) : isEvaluated ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                  <Award className="w-3.5 h-3.5" /> Evaluated (Draft)
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                  <Clock className="w-3.5 h-3.5" /> Awaiting Grading
                </span>
              )}
              {isPublished && submission.published_at && (
                <span className="text-xs text-slate-400">
                  · Published on {new Date(submission.published_at).toLocaleDateString()}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Candidate: <span className="font-medium text-slate-700">{submission.student_email || `@${submission.student_username}`}</span> · Exam: <span className="font-semibold text-slate-800">{submission.examination_title}</span> · Attempt #{submission.attempt_id} · Submitted {new Date(submission.submitted_at || submission.created_at).toLocaleString()}
            </p>
          </div>
        </div>

        {/* Global Action Buttons */}
        <div className="flex items-center gap-2 self-end md:self-auto flex-wrap">
          <button
            type="button"
            onClick={() => {
              if (hasErrors) {
                toast.error(validationErrors[0]?.error || "Please fix validation errors first.");
                return;
              }
              evaluateMutation.mutate(isPublished);
            }}
            disabled={evaluateMutation.isPending || publishMutation.isPending}
            className="px-4 py-2 border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg shadow-sm flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            {evaluateMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            Save Marks Draft
          </button>

          {!isPublished ? (
            <button
              type="button"
              onClick={() => {
                if (hasErrors) {
                  toast.error(validationErrors[0]?.error || "Cannot publish: complete question marks first.");
                  return;
                }
                setShowPublishModal(true);
              }}
              disabled={evaluateMutation.isPending || publishMutation.isPending}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg shadow-sm flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              <Check className="w-3.5 h-3.5" /> Publish to Student
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                if (hasErrors) {
                  toast.error(validationErrors[0]?.error || "Cannot update: complete question marks first.");
                  return;
                }
                setShowPublishModal(true);
              }}
              disabled={evaluateMutation.isPending || publishMutation.isPending}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg shadow-sm flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              <Edit3 className="w-3.5 h-3.5" /> Edit Published Result
            </button>
          )}
        </div>
      </div>

      {/* Mobile Tab Navigation */}
      <div className="lg:hidden flex rounded-lg bg-slate-200 p-1 text-xs font-semibold">
        <button
          type="button"
          onClick={() => setMobileTab("evaluation")}
          className={`flex-1 py-1.5 rounded-md transition-colors ${
            mobileTab === "evaluation" ? "bg-white text-[#0B2545] shadow-sm" : "text-slate-600"
          }`}
        >
          Marking &amp; Feedback
        </button>
        <button
          type="button"
          onClick={() => setMobileTab("viewer")}
          className={`flex-1 py-1.5 rounded-md transition-colors ${
            mobileTab === "viewer" ? "bg-white text-[#0B2545] shadow-sm" : "text-slate-600"
          }`}
        >
          Answer PDF ({submission.page_count})
        </button>
        <button
          type="button"
          onClick={() => setMobileTab("ocr")}
          className={`flex-1 py-1.5 rounded-md transition-colors ${
            mobileTab === "ocr" ? "bg-white text-indigo-700 shadow-sm" : "text-slate-600"
          }`}
        >
          AI OCR
        </button>
      </div>

      {/* Main Workspace (Split-screen) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Left Column: Answer Sheet PDF Viewer (7 cols) */}
        <div
          className={`lg:col-span-7 bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm flex flex-col h-[82vh] ${
            mobileTab !== "viewer" ? "hidden lg:flex" : "flex"
          }`}
        >
          {/* PDF Viewer Top Controls */}
          <div className="bg-slate-50 border-b border-slate-200 px-4 py-2.5 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
                <FileText className="w-4 h-4 text-indigo-600" />
                Answer Sheet ({submission.page_count} {submission.page_count === 1 ? "page" : "pages"})
              </span>
              {submission.file_size_bytes > 0 && (
                <span className="text-[11px] text-slate-400">
                  · {(submission.file_size_bytes / (1024 * 1024)).toFixed(1)} MB
                </span>
              )}
            </div>

            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setZoomLevel((z) => Math.max(50, z - 15))}
                className="p-1.5 hover:bg-slate-200 rounded text-slate-600 transition-colors"
                title="Zoom Out"
              >
                <ZoomOut className="w-3.5 h-3.5" />
              </button>
              <span className="text-xs font-medium text-slate-600 w-10 text-center">{zoomLevel}%</span>
              <button
                type="button"
                onClick={() => setZoomLevel((z) => Math.min(200, z + 15))}
                className="p-1.5 hover:bg-slate-200 rounded text-slate-600 transition-colors"
                title="Zoom In"
              >
                <ZoomIn className="w-3.5 h-3.5" />
              </button>
              {pdfUrl && (
                <>
                  <a
                    href={pdfUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-1.5 hover:bg-slate-200 rounded text-slate-600 transition-colors ml-1"
                    title="Open PDF in new window"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                  <a
                    href={pdfUrl}
                    download={`answer-sheet-${submission.student_name}.pdf`}
                    className="p-1.5 hover:bg-slate-200 rounded text-slate-600 transition-colors"
                    title="Download Answer Sheet PDF"
                  >
                    <Download className="w-3.5 h-3.5" />
                  </a>
                </>
              )}
            </div>
          </div>

          {/* PDF Frame */}
          <div className="flex-1 bg-slate-900/90 relative overflow-auto flex items-center justify-center p-2">
            {loadingPdf ? (
              <div className="flex flex-col items-center justify-center gap-2 text-white">
                <Loader2 className="w-7 h-7 animate-spin text-indigo-400" />
                <span className="text-xs text-slate-300 font-medium">Rendering answer sheet...</span>
              </div>
            ) : pdfUrl ? (
              <iframe
                src={`${pdfUrl}#zoom=${zoomLevel}`}
                className="w-full h-full rounded border-0 bg-white"
                style={{ transform: `scale(${zoomLevel / 100})`, transformOrigin: "top center" }}
                title="Candidate Answer Sheet"
              />
            ) : (
              <div className="text-center text-slate-400 p-8 space-y-2">
                <FileText className="w-10 h-10 mx-auto text-slate-500" />
                <p className="text-sm font-medium">Answer Sheet Not Available</p>
                <p className="text-xs text-slate-500">The student has not uploaded a valid answer sheet yet.</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Scoring & OCR Transcription (5 cols) */}
        <div
          className={`lg:col-span-5 bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm flex flex-col h-[82vh] ${
            mobileTab === "viewer" ? "hidden lg:flex" : "flex"
          }`}
        >
          {/* Tab Bar */}
          <div className="flex items-center border-b border-slate-200 bg-slate-50 px-2 pt-2">
            <button
              onClick={() => {
                setActiveTab("evaluation");
                setMobileTab("evaluation");
              }}
              className={`flex-1 py-2 text-xs font-semibold border-b-2 text-center flex items-center justify-center gap-1.5 transition-colors ${
                (activeTab === "evaluation" && mobileTab !== "ocr")
                  ? "border-[#0B2545] text-[#0B2545] bg-white rounded-t-lg"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              <Award className="w-4 h-4 text-[#D4A72C]" /> Marking &amp; Feedback
            </button>
            <button
              onClick={() => {
                setActiveTab("ocr");
                setMobileTab("ocr");
              }}
              className={`flex-1 py-2 text-xs font-semibold border-b-2 text-center flex items-center justify-center gap-1.5 transition-colors ${
                (activeTab === "ocr" || mobileTab === "ocr")
                  ? "border-indigo-600 text-indigo-700 bg-white rounded-t-lg"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              <Sparkles className="w-4 h-4 text-indigo-500" /> AI OCR Transcription
            </button>
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-5">
            {activeTab === "evaluation" && mobileTab !== "ocr" ? (
              <div className="space-y-5">
                {/* Overall Score Summary Card */}
                <div className="bg-gradient-to-br from-[#0B2545] to-[#163E6B] rounded-xl p-4 text-white shadow-sm border border-[#1a4a7e]">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-[11px] font-semibold text-[#D4A72C] uppercase tracking-wider">
                        Authoritative Marks
                      </span>
                      <p className="text-xs text-white/70 mt-0.5">
                        {questionScores.length} {questionScores.length === 1 ? "question" : "questions"} evaluated
                      </p>
                    </div>
                    <div className="text-right">
                      <div className="flex items-baseline justify-end gap-1.5">
                        <span className="text-3xl font-extrabold text-white">{totalObtainedMarks}</span>
                        <span className="text-sm font-semibold text-white/60">/ {totalMaxMarks}</span>
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 pt-2.5 border-t border-white/10 flex items-center justify-between text-xs font-medium">
                    <span className="text-white/80">
                      Percentage: <strong className="text-white text-sm">{calculatedPercentage}%</strong>
                    </span>
                    <span>
                      Status:{" "}
                      {isPassing ? (
                        <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-400/30">
                          Passed
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-rose-500/20 text-rose-300 border border-rose-400/30">
                          Failed (Need {passMarks} pts)
                        </span>
                      )}
                    </span>
                  </div>
                </div>

                {/* Validation Banner if errors exist */}
                {hasErrors && (
                  <div className="bg-rose-50 border border-rose-200 rounded-lg p-3 text-xs text-rose-800 space-y-1">
                    <div className="flex items-center gap-1.5 font-bold">
                      <AlertTriangle className="w-4 h-4 text-rose-600" />
                      Please resolve marking errors before publishing:
                    </div>
                    <ul className="list-disc list-inside space-y-0.5 pl-1 text-[11px] text-rose-700">
                      {validationErrors.map((err, i) => (
                        <li key={i}>{err.error}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Dynamic Question-Wise Marks Breakdown */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <label className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                        Question-Wise Evaluation ({questionScores.length})
                      </label>
                      <p className="text-[11px] text-slate-400">
                        Admin manages questions, maximum marks, and obtained marks dynamically.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={handleAddQuestion}
                      className="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 text-xs font-semibold rounded-lg flex items-center gap-1 transition-colors"
                    >
                      <Plus className="w-3.5 h-3.5" /> Add Question
                    </button>
                  </div>

                  <div className="space-y-3">
                    {questionScores.map((q, idx) => {
                      const qError = getQuestionError(q);
                      return (
                        <div
                          key={idx}
                          className={`p-3.5 rounded-xl border transition-all ${
                            qError
                              ? "bg-rose-50/60 border-rose-300 ring-1 ring-rose-300"
                              : "bg-slate-50/80 border-slate-200 hover:border-slate-300"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2 mb-2.5">
                            <div className="flex items-center gap-2">
                              <span className="w-6 h-6 rounded-full bg-[#0B2545] text-white text-xs font-bold flex items-center justify-center">
                                {q.question_number}
                              </span>
                              <span className="text-xs font-bold text-slate-800">
                                Question #{q.question_number}
                              </span>
                            </div>

                            <button
                              type="button"
                              onClick={() => handleDeleteQuestion(idx)}
                              className="p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded transition-colors"
                              title={`Delete Question #${q.question_number}`}
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>

                          <div className="grid grid-cols-2 gap-3 mb-2.5">
                            <div>
                              <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                                Maximum Marks
                              </label>
                              <input
                                type="number"
                                min={1}
                                step={1}
                                value={q.max_marks}
                                onFocus={(e) => e.target.select()}
                                onChange={(e) => {
                                  handleUpdateQuestion(idx, "max_marks", e.target.value);
                                }}
                                onBlur={() => {
                                  if (q.max_marks === "" || Number(q.max_marks) <= 0) {
                                    handleUpdateQuestion(idx, "max_marks", 10);
                                  }
                                }}
                                className={`w-full p-2 bg-white border rounded-lg text-xs font-bold text-slate-900 focus:outline-none focus:ring-2 ${
                                  q.max_marks === "" || Number(q.max_marks) <= 0
                                    ? "border-rose-400 focus:ring-rose-200 text-rose-700"
                                    : "border-slate-300 focus:ring-indigo-200"
                                }`}
                              />
                            </div>

                            <div>
                              <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                                Obtained Marks
                              </label>
                              <div className="flex items-center gap-1.5">
                                <input
                                  type="number"
                                  min={0}
                                  max={Number(q.max_marks) || 10}
                                  step={0.5}
                                  value={q.marks_obtained}
                                  onFocus={(e) => e.target.select()}
                                  onChange={(e) => {
                                    handleUpdateQuestion(idx, "marks_obtained", e.target.value);
                                  }}
                                  onBlur={() => {
                                    if (q.marks_obtained === "") {
                                      handleUpdateQuestion(idx, "marks_obtained", 0);
                                    }
                                  }}
                                  className={`w-full p-2 bg-white border rounded-lg text-xs font-bold text-slate-900 focus:outline-none focus:ring-2 ${
                                    (q.marks_obtained !== "" && q.max_marks !== "" && Number(q.marks_obtained) > Number(q.max_marks)) ||
                                    (q.marks_obtained !== "" && Number(q.marks_obtained) < 0)
                                      ? "border-rose-400 focus:ring-rose-200 text-rose-700 bg-rose-50"
                                      : "border-slate-300 focus:ring-indigo-200"
                                  }`}
                                />
                                <span className="text-xs font-semibold text-slate-400 whitespace-nowrap">
                                  / {q.max_marks || 0}
                                </span>
                              </div>
                            </div>
                          </div>

                          {qError && (
                            <p className="text-[11px] text-rose-600 font-semibold mb-2 flex items-center gap-1">
                              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                              {qError}
                            </p>
                          )}

                          <div>
                            <input
                              type="text"
                              placeholder={`Optional examiner remark for Question #${q.question_number}...`}
                              value={q.feedback}
                              onChange={(e) => handleUpdateQuestion(idx, "feedback", e.target.value)}
                              className="w-full text-xs p-2 bg-white border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-[#0B2545]/20"
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <button
                    type="button"
                    onClick={handleAddQuestion}
                    className="w-full py-2.5 border-2 border-dashed border-indigo-200 hover:border-indigo-400 bg-indigo-50/50 hover:bg-indigo-50 text-indigo-700 text-xs font-semibold rounded-xl flex items-center justify-center gap-1.5 transition-colors"
                  >
                    <Plus className="w-4 h-4" /> Add Another Question
                  </button>
                </div>

                {/* Overall Examiner Feedback */}
                <div className="pt-2 border-t border-slate-100">
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                    <MessageSquare className="w-3.5 h-3.5 text-indigo-600" />
                    Overall Examiner Qualitative Feedback
                  </label>
                  <textarea
                    rows={4}
                    value={evaluatorFeedback}
                    onChange={(e) => setEvaluatorFeedback(e.target.value)}
                    placeholder="Provide constructive feedback, presentation remarks, or corrections for the student..."
                    className="w-full text-xs p-3 border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-[#0B2545]/20 text-slate-900 placeholder:text-slate-400 resize-y leading-relaxed"
                  />
                  <p className="text-[11px] text-slate-400 mt-1">
                    This overall feedback is saved with the evaluation and shown on the student's result portal after publication.
                  </p>
                </div>
              </div>
            ) : (
              /* OCR Handwriting Transcription Tab */
              <div className="space-y-4">
                <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h4 className="text-xs font-bold text-indigo-900 uppercase tracking-wider flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                      Multimodal Handwriting OCR
                    </h4>
                    <p className="text-xs text-indigo-700 mt-0.5">
                      Extracts Nepali &amp; English handwritten script to assist evaluation. Final marks remain strictly admin-controlled.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => ocrMutation.mutate()}
                    disabled={ocrMutation.isPending || !submission.has_answer_pdf}
                    className="px-3.5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-sm flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50 shrink-0"
                  >
                    {ocrMutation.isPending ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Transcribing...
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-3.5 h-3.5" /> Run AI OCR
                      </>
                    )}
                  </button>
                </div>

                {submission.ocr_status === "completed" && (
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span className="flex items-center gap-1 text-emerald-700 font-medium">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Transcription Available
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(extractedText);
                        toast.success("Transcription copied to clipboard");
                      }}
                      className="text-indigo-600 hover:underline font-medium"
                    >
                      Copy All Text
                    </button>
                  </div>
                )}

                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5 flex items-center justify-between">
                    <span>Verified Transcription (Editable)</span>
                    <span className="text-[11px] text-slate-400 lowercase font-normal">
                      Correct any misrecognized words
                    </span>
                  </label>
                  <textarea
                    rows={15}
                    value={extractedText}
                    onChange={(e) => setExtractedText(e.target.value)}
                    placeholder="Click 'Run AI OCR' above to extract handwriting into text, or type notes here..."
                    className="w-full text-xs font-mono p-3 border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 text-slate-900 placeholder:text-slate-400 resize-y leading-relaxed"
                  />
                </div>

                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => updateTranscriptionMutation.mutate()}
                    disabled={updateTranscriptionMutation.isPending}
                    className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white text-xs font-semibold rounded-lg shadow-sm flex items-center gap-1.5 transition-colors disabled:opacity-50"
                  >
                    {updateTranscriptionMutation.isPending ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Save className="w-3.5 h-3.5" />
                    )}
                    Save Corrected Text
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Result Publishing Confirmation Modal */}
      {showPublishModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full shadow-2xl border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div className="w-10 h-10 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center justify-center">
                  <ShieldCheck className="w-6 h-6" />
                </div>
                <button
                  type="button"
                  onClick={() => setShowPublishModal(false)}
                  className="p-1 rounded-lg text-slate-400 hover:text-slate-600 transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div>
                <h3 className="text-lg font-bold text-slate-900">
                  {isPublished ? "Update Published Result?" : "Publish Result to Candidate?"}
                </h3>
                <p className="text-xs text-slate-500 mt-1">
                  Once published, the student will be immediately notified and able to view their final score, question-wise breakdown, and examiner feedback.
                </p>
              </div>

              {/* Summary details table */}
              <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 text-xs space-y-2.5">
                <div className="flex justify-between items-center text-slate-600">
                  <span>Candidate:</span>
                  <span className="font-bold text-slate-900">{submission.student_name}</span>
                </div>
                <div className="flex justify-between items-center text-slate-600">
                  <span>Examination:</span>
                  <span className="font-medium text-slate-800 text-right max-w-[200px] truncate">
                    {submission.examination_title}
                  </span>
                </div>
                <div className="flex justify-between items-center text-slate-600">
                  <span>Questions Evaluated:</span>
                  <span className="font-semibold text-slate-900">{questionScores.length}</span>
                </div>
                <div className="pt-2 border-t border-slate-200 flex justify-between items-center">
                  <span className="font-bold text-slate-700">Final Score:</span>
                  <span className="text-base font-extrabold text-[#0B2545]">
                    {totalObtainedMarks} / {totalMaxMarks} ({calculatedPercentage}%)
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="font-bold text-slate-700">Official Result:</span>
                  <span
                    className={`font-bold px-2 py-0.5 rounded-full text-[11px] ${
                      isPassing ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"
                    }`}
                  >
                    {isPassing ? "Passed" : "Failed"}
                  </span>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowPublishModal(false)}
                  disabled={publishMutation.isPending}
                  className="px-4 py-2 border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => publishMutation.mutate()}
                  disabled={publishMutation.isPending}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg shadow-sm flex items-center gap-1.5 transition-colors disabled:opacity-50"
                >
                  {publishMutation.isPending ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" /> Publishing...
                    </>
                  ) : (
                    <>
                      <Check className="w-3.5 h-3.5" /> Confirm &amp; Publish Result
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
