"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Clock, Camera, UploadCloud, Trash2, ArrowLeft, ArrowRight,
  RotateCw, Eye, AlertTriangle, CheckCircle2, Loader2, Maximize2,
  Minimize2, ZoomIn, ZoomOut, FileText, Send,
  ExternalLink, RefreshCw
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { studentExamsApi, SubjectiveAttemptState } from "@/lib/api/student-exams";
import toast from "react-hot-toast";

interface PageImageItem {
  id: string;
  file: File;
  previewUrl: string;
  rotation: number; // 0, 90, 180, 270
}

interface SubjectiveExamAttemptViewProps {
  examId: number;
  attemptId: number;
  examTitle: string;
  initialState?: Partial<SubjectiveAttemptState>;
  onFinish?: () => void;
}

export function SubjectiveExamAttemptView({
  examId,
  attemptId,
  examTitle,
  initialState,
  onFinish,
}: SubjectiveExamAttemptViewProps) {
  const router = useRouter();

  // Mobile Tab: 'paper' | 'upload'
  const [mobileTab, setMobileTab] = useState<"paper" | "upload">("paper");

  // Timer State (Server Authoritative)
  const [writingSecondsRemaining, setWritingSecondsRemaining] = useState<number>(
    initialState?.time_remaining_seconds ?? 3600
  );
  const [uploadSecondsRemaining, setUploadSecondsRemaining] = useState<number>(
    initialState?.upload_time_remaining_seconds ?? 900
  );
  const [canUpload, setCanUpload] = useState<boolean>(initialState?.can_upload ?? true);
  const [isUploadPending, setIsUploadPending] = useState<boolean>(
    initialState?.status === "upload_pending"
  );
  const [isCompleted, setIsCompleted] = useState<boolean>(
    initialState?.status === "submitted" || initialState?.status === "completed"
  );

  // Question Paper PDF State
  const [paperPdfUrl, setPaperPdfUrl] = useState<string | null>(null);
  const [loadingPaper, setLoadingPaper] = useState(true);
  const [paperError, setPaperError] = useState<string | null>(null);
  const [paperZoom, setPaperZoom] = useState(100);
  const [isFullscreenPaper, setIsFullscreenPaper] = useState(false);

  // Upload Answer Sheet State
  const [capturedPages, setCapturedPages] = useState<PageImageItem[]>([]);
  const [uploadedPdfFile, setUploadedPdfFile] = useState<File | null>(null);
  const [submittingAnswer, setSubmittingAnswer] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState(Boolean(initialState?.has_answer_pdf));

  const cameraInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch initial & heartbeat timer state from backend
  const syncServerTime = async () => {
    try {
      const state = await studentExamsApi.getAttemptState(attemptId);
      setWritingSecondsRemaining(state.time_remaining_seconds);
      setUploadSecondsRemaining(state.upload_time_remaining_seconds);
      setCanUpload(state.can_upload);
      setIsUploadPending(state.status === "upload_pending");
      if (state.has_answer_pdf) {
        setUploadSuccess(true);
      }
      if (state.status === "submitted" || state.status === "completed" || state.status === "evaluated") {
        setIsCompleted(true);
      }
    } catch {
      // Keep running locally if heartbeat fails
    }
  };

  useEffect(() => {
    syncServerTime();
    // Heartbeat every 25 seconds to sync with server clock
    const heartbeat = setInterval(syncServerTime, 25000);
    return () => clearInterval(heartbeat);
  }, [attemptId]);

  // Local second-by-second countdown
  useEffect(() => {
    const timer = setInterval(() => {
      setWritingSecondsRemaining((prev) => {
        if (prev > 0) return prev - 1;
        setIsUploadPending(true);
        return 0;
      });

      setUploadSecondsRemaining((prev) => {
        if (prev > 0) return prev - 1;
        setCanUpload(false);
        return 0;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  // Fetch Question Paper PDF Blob
  const loadQuestionPaper = async () => {
    setLoadingPaper(true);
    setPaperError(null);
    try {
      const blob = await studentExamsApi.getQuestionPaperBlob(examId);
      if (!blob || blob.size < 100) {
        setPaperError("The question paper PDF uploaded for this examination is empty or corrupted. Please notify the exam administrator.");
        setPaperPdfUrl(null);
        return;
      }
      const url = URL.createObjectURL(blob);
      setPaperPdfUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
      setPaperError(null);
    } catch (err: any) {
      setPaperError("Could not retrieve the official question paper. Please check your network or try again.");
    } finally {
      setLoadingPaper(false);
    }
  };

  useEffect(() => {
    loadQuestionPaper();
    return () => {
      if (paperPdfUrl) URL.revokeObjectURL(paperPdfUrl);
    };
  }, [examId]);

  // Format seconds to HH:MM:SS
  const formatTime = (secs: number) => {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    const pad = (n: number) => n.toString().padStart(2, "0");
    if (h > 0) return `${pad(h)}:${pad(m)}:${pad(s)}`;
    return `${pad(m)}:${pad(s)}`;
  };

  // Image Selection Handler (Camera or Gallery)
  const handleFilesSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    // Check if user uploaded a direct PDF
    const pdfs = Array.from(files).filter(
      (f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf")
    );
    const selectedPdf = pdfs[0];
    if (selectedPdf) {
      setUploadedPdfFile(selectedPdf);
      setCapturedPages([]);
      toast.success(`Selected PDF answer sheet: ${selectedPdf.name}`);
      return;
    }

    // Process image pages
    const newItems: PageImageItem[] = Array.from(files).map((file, idx) => ({
      id: `${Date.now()}-${idx}-${Math.random().toString(36).substring(2, 6)}`,
      file,
      previewUrl: URL.createObjectURL(file),
      rotation: 0,
    }));

    setCapturedPages((prev) => [...prev, ...newItems]);
    setUploadedPdfFile(null);
    toast.success(`Added ${newItems.length} page(s). Total: ${capturedPages.length + newItems.length}`);

    // Reset input
    e.target.value = "";
  };

  // Reordering handlers
  const movePage = (index: number, direction: "left" | "right") => {
    const targetIndex = direction === "left" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= capturedPages.length) return;
    setCapturedPages((prev) => {
      const next = [...prev];
      const itemCurrent = next[index];
      const itemTarget = next[targetIndex];
      if (itemCurrent && itemTarget) {
        next[index] = itemTarget;
        next[targetIndex] = itemCurrent;
      }
      return next;
    });
  };

  const removePage = (index: number) => {
    setCapturedPages((prev) => {
      const target = prev[index];
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((_, i) => i !== index);
    });
  };

  const rotatePage = (index: number) => {
    setCapturedPages((prev) =>
      prev.map((item, i) => (i === index ? { ...item, rotation: (item.rotation + 90) % 360 } : item))
    );
  };

  // Submit Answer Sheet to Backend
  const handleSubmitAnswerSheet = async () => {
    if (!uploadedPdfFile && capturedPages.length === 0) {
      toast.error("Please take photos or upload your answer sheet first.");
      return;
    }
    if (!canUpload) {
      toast.error("The upload window has expired. Submissions are closed.");
      return;
    }

    setSubmittingAnswer(true);
    try {
      const formData = new FormData();
      if (uploadedPdfFile) {
        formData.append("pdf_file", uploadedPdfFile);
      } else {
        capturedPages.forEach((page) => {
          formData.append("images", page.file);
        });
      }

      const res = await studentExamsApi.uploadAnswerSheet(attemptId, formData);
      setUploadSuccess(true);
      toast.success((res as any)?.detail || res?.message || "Answer sheet submitted successfully!");
      if (onFinish) onFinish();
    } catch (err: any) {
      const msg = err?.data?.detail || err?.data?.error || err?.message || "Failed to submit answer sheet. Please retry.";
      toast.error(msg);
    } finally {
      setSubmittingAnswer(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col">
      {/* Top Authoritative Header */}
      <header className="sticky top-0 z-50 bg-slate-950/90 backdrop-blur-md border-b border-slate-800 px-4 py-3 flex flex-wrap items-center justify-between gap-3 shadow-md">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center shrink-0">
            <FileText className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-sm sm:text-base font-bold text-white line-clamp-1">{examTitle}</h1>
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <span className="capitalize text-indigo-400 font-semibold">Subjective Examination</span>
              <span>•</span>
              <span>Attempt #{attemptId}</span>
            </div>
          </div>
        </div>

        {/* Dual Timers */}
        <div className="flex items-center gap-2 sm:gap-4">
          {/* Writing Timer */}
          <div
            className={`px-3 py-1.5 rounded-lg border text-xs sm:text-sm font-mono font-bold flex items-center gap-2 shadow-sm ${
              writingSecondsRemaining > 0
                ? "bg-slate-900 border-slate-700 text-emerald-400"
                : "bg-rose-950/40 border-rose-900 text-rose-400"
            }`}
          >
            <Clock className="w-4 h-4 shrink-0" />
            <div>
              <span className="text-[10px] uppercase tracking-wider block text-slate-400 font-sans font-medium">
                {writingSecondsRemaining > 0 ? "Writing Time" : "Writing Ended"}
              </span>
              <span>{formatTime(writingSecondsRemaining)}</span>
            </div>
          </div>

          {/* Upload Window Timer */}
          <div
            className={`px-3 py-1.5 rounded-lg border text-xs sm:text-sm font-mono font-bold flex items-center gap-2 shadow-sm ${
              uploadSecondsRemaining > 300
                ? "bg-slate-900 border-slate-700 text-amber-300"
                : uploadSecondsRemaining > 0
                ? "bg-amber-950/60 border-amber-600 text-amber-300 animate-pulse"
                : "bg-rose-950 border-rose-700 text-rose-400"
            }`}
          >
            <Camera className="w-4 h-4 shrink-0" />
            <div>
              <span className="text-[10px] uppercase tracking-wider block text-slate-400 font-sans font-medium">
                Upload Window
              </span>
              <span>{uploadSecondsRemaining > 0 ? formatTime(uploadSecondsRemaining) : "Closed"}</span>
            </div>
          </div>
        </div>
      </header>

      {/* Upload Deadline Alert Banner if writing time is finished */}
      {isUploadPending && canUpload && !uploadSuccess && (
        <div className="bg-amber-500/10 border-b border-amber-500/30 px-4 py-2 text-xs text-amber-300 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>
              <strong>Writing time has ended!</strong> You have{" "}
              <strong>{formatTime(uploadSecondsRemaining)}</strong> remaining to photograph and submit your
              handwritten answer sheets.
            </span>
          </div>
          <button
            onClick={() => setMobileTab("upload")}
            className="hidden sm:inline-block px-2.5 py-1 bg-amber-500 text-slate-950 rounded font-bold hover:bg-amber-400 transition-colors"
          >
            Go to Upload
          </button>
        </div>
      )}

      {/* Mobile Tab Switcher */}
      <div className="lg:hidden flex border-b border-slate-800 bg-slate-950">
        <button
          onClick={() => setMobileTab("paper")}
          className={`flex-1 py-2.5 text-xs font-bold text-center border-b-2 flex items-center justify-center gap-2 ${
            mobileTab === "paper"
              ? "border-indigo-500 text-indigo-400 bg-slate-900/60"
              : "border-transparent text-slate-400"
          }`}
        >
          <FileText className="w-4 h-4" /> Question Paper
        </button>
        <button
          onClick={() => setMobileTab("upload")}
          className={`flex-1 py-2.5 text-xs font-bold text-center border-b-2 flex items-center justify-center gap-2 ${
            mobileTab === "upload"
              ? "border-indigo-500 text-indigo-400 bg-slate-900/60"
              : "border-transparent text-slate-400"
          }`}
        >
          <Camera className="w-4 h-4" /> Upload Answers{" "}
          {capturedPages.length > 0 && `(${capturedPages.length})`}
        </button>
      </div>

      {/* Main Workspace: Split View on Desktop */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Column: Question Paper PDF Viewer */}
        <div
          className={`flex-1 flex-col border-r border-slate-800 bg-slate-950 ${
            mobileTab === "paper" ? "flex" : "hidden lg:flex"
          }`}
        >
          {/* Question Paper Controls */}
          <div className="bg-slate-900/90 border-b border-slate-800 px-4 py-2 flex items-center justify-between gap-3 text-xs">
            <span className="font-semibold text-slate-300 flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-indigo-400" /> Question Paper
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setPaperZoom((z) => Math.max(50, z - 15))}
                className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white"
                title="Zoom Out"
              >
                <ZoomOut className="w-3.5 h-3.5" />
              </button>
              <span className="w-8 text-center text-slate-400">{paperZoom}%</span>
              <button
                type="button"
                onClick={() => setPaperZoom((z) => Math.min(200, z + 15))}
                className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white"
                title="Zoom In"
              >
                <ZoomIn className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={loadQuestionPaper}
                disabled={loadingPaper}
                className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white ml-1 disabled:opacity-40"
                title="Reload Question Paper"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingPaper ? "animate-spin" : ""}`} />
              </button>
              {paperPdfUrl && (
                <a
                  href={paperPdfUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white"
                  title="Open in New Tab"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
              <button
                type="button"
                onClick={() => setIsFullscreenPaper(!isFullscreenPaper)}
                className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white ml-1"
                title="Toggle Fullscreen"
              >
                {isFullscreenPaper ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
              </button>
            </div>
          </div>

          {/* PDF Embed */}
          <div
            className={`flex-1 bg-slate-900 relative overflow-auto flex items-center justify-center p-2 ${
              isFullscreenPaper ? "fixed inset-0 z-50 bg-black p-4" : ""
            }`}
          >
            {isFullscreenPaper && (
              <button
                onClick={() => setIsFullscreenPaper(false)}
                className="absolute top-4 right-4 z-50 p-2 bg-slate-800 text-white rounded-lg shadow-lg hover:bg-slate-700"
              >
                <Minimize2 className="w-5 h-5" />
              </button>
            )}

            {loadingPaper ? (
              <div className="flex flex-col items-center justify-center gap-2 text-slate-400">
                <Loader2 className="w-7 h-7 animate-spin text-indigo-400" />
                <span className="text-xs">Loading question paper PDF...</span>
              </div>
            ) : paperError ? (
              <div className="text-center text-slate-400 p-8 space-y-3 max-w-sm">
                <div className="w-12 h-12 rounded-full bg-rose-950/60 border border-rose-500/40 text-rose-400 flex items-center justify-center mx-auto">
                  <AlertTriangle className="w-6 h-6" />
                </div>
                <p className="text-sm font-semibold text-slate-200">Question Paper Issue</p>
                <p className="text-xs text-slate-400 leading-relaxed">{paperError}</p>
                <button
                  type="button"
                  onClick={loadQuestionPaper}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg shadow transition-colors"
                >
                  <RefreshCw className="w-3.5 h-3.5" /> Retry Loading
                </button>
              </div>
            ) : paperPdfUrl ? (
              <iframe
                src={`${paperPdfUrl}#zoom=${paperZoom}`}
                className="w-full h-full rounded border-0 bg-white"
                style={{ transform: `scale(${paperZoom / 100})`, transformOrigin: "top center" }}
                title="Question Paper"
              />
            ) : (
              <div className="text-center text-slate-500 p-8 space-y-2">
                <FileText className="w-10 h-10 mx-auto text-slate-600" />
                <p className="text-sm font-semibold">Question Paper Unavailable</p>
                <p className="text-xs text-slate-400">Could not retrieve the official question paper.</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Handwritten Answer Sheet Upload (Mobile camera + Reordering) */}
        <div
          className={`flex-1 flex flex-col bg-slate-900 overflow-y-auto ${
            mobileTab === "upload" ? "flex" : "hidden lg:flex"
          }`}
        >
          <div className="p-4 sm:p-6 space-y-5 max-w-2xl mx-auto w-full">
            {/* Answer Upload Header */}
            <div className="border-b border-slate-800 pb-4">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Camera className="w-5 h-5 text-indigo-400" />
                Handwritten Answer Sheet Submission
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Take clear photos of each page of your handwritten answer sheet in numerical order. You can reorder or
                rotate pages before submitting.
              </p>
            </div>

            {/* Success state */}
            {uploadSuccess ? (
              <div className="bg-emerald-950/40 border border-emerald-500/40 rounded-xl p-5 space-y-3 text-center">
                <div className="w-12 h-12 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto">
                  <CheckCircle2 className="w-6 h-6" />
                </div>
                <h3 className="font-bold text-emerald-300 text-base">Answer Sheet Uploaded!</h3>
                <p className="text-xs text-slate-300 max-w-md mx-auto">
                  Your handwritten answer sheet has been compiled and safely recorded. Our evaluators will review and
                  grade your submission.
                </p>
                <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
                  {uploadedPdfFile && (
                    <button
                      type="button"
                      onClick={() => {
                        const url = URL.createObjectURL(uploadedPdfFile);
                        window.open(url, "_blank");
                      }}
                      className="px-3.5 py-1.5 bg-indigo-950 border border-indigo-700 hover:bg-indigo-900 text-xs font-semibold text-indigo-200 rounded-lg transition-colors inline-flex items-center gap-1.5"
                    >
                      <Eye className="w-3.5 h-3.5 text-indigo-400" /> Preview Submitted PDF
                    </button>
                  )}
                  {canUpload && (
                    <button
                      onClick={() => {
                        if (confirm("Replace existing submitted answer sheet with a new PDF or photos?")) {
                          setUploadSuccess(false);
                          setUploadedPdfFile(null);
                          setCapturedPages([]);
                        }
                      }}
                      className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 rounded-lg transition-colors inline-block"
                    >
                      Replace / Re-upload
                    </button>
                  )}
                  {isCompleted && (
                    <Button
                      onClick={() => router.replace(`/student/exams/${examId}/result/${attemptId}`)}
                      className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs"
                    >
                      View Result Portal
                    </Button>
                  )}
                </div>
              </div>
            ) : (
              <>
                {/* Upload action buttons */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {/* Camera capture */}
                  <input
                    ref={cameraInputRef}
                    type="file"
                    accept="image/*"
                    capture="environment"
                    multiple
                    className="hidden"
                    onChange={handleFilesSelected}
                  />
                  <button
                    type="button"
                    onClick={() => cameraInputRef.current?.click()}
                    disabled={!canUpload || submittingAnswer}
                    className="p-4 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/40 text-indigo-300 flex flex-col items-center justify-center gap-2 transition-all group disabled:opacity-40"
                  >
                    <div className="w-10 h-10 rounded-full bg-indigo-600 text-white flex items-center justify-center group-hover:scale-105 transition-transform shadow-md">
                      <Camera className="w-5 h-5" />
                    </div>
                    <span className="font-bold text-sm text-white">Take Photos with Camera</span>
                    <span className="text-[11px] text-slate-400">Capture answer pages sequentially</span>
                  </button>

                  {/* Device file / PDF upload */}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="application/pdf,image/*"
                    multiple
                    className="hidden"
                    onChange={handleFilesSelected}
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={!canUpload || submittingAnswer}
                    className="p-4 rounded-xl bg-slate-800/80 hover:bg-slate-800 border border-slate-700 text-slate-300 flex flex-col items-center justify-center gap-2 transition-all group disabled:opacity-40"
                  >
                    <div className="w-10 h-10 rounded-full bg-slate-700 text-slate-200 flex items-center justify-center group-hover:scale-105 transition-transform shadow-md">
                      <UploadCloud className="w-5 h-5 text-indigo-400" />
                    </div>
                    <span className="font-bold text-sm text-white">Upload PDF or Images</span>
                    <span className="text-[11px] text-slate-400">Directly submit scanned PDF or image sheets</span>
                  </button>
                </div>

                {/* Direct PDF Upload Selected */}
                {uploadedPdfFile && (
                  <div className="bg-slate-800/90 border border-indigo-500/40 rounded-xl p-4 space-y-3 shadow-md">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-red-500/20 text-red-400 border border-red-500/30 flex items-center justify-center shrink-0">
                          <FileText className="w-5 h-5" />
                        </div>
                        <div>
                          <div className="font-bold text-sm text-white flex items-center gap-2">
                            <span>{uploadedPdfFile.name}</span>
                            <Badge variant="outline" className="bg-red-500/10 text-red-400 border-red-500/30 text-[10px] font-bold">
                              PDF
                            </Badge>
                          </div>
                          <div className="text-xs text-slate-400">
                            {(uploadedPdfFile.size / (1024 * 1024)).toFixed(2)} MB · Document Ready to Submit
                          </div>
                        </div>
                      </div>
                      <button
                        onClick={() => setUploadedPdfFile(null)}
                        className="p-1.5 text-slate-400 hover:text-rose-400 rounded-lg hover:bg-slate-700 transition-colors"
                        title="Remove PDF"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>

                    {/* Preview / Replace / Submit Actions */}
                    <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-700/60">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          const url = URL.createObjectURL(uploadedPdfFile);
                          window.open(url, "_blank");
                        }}
                        className="border-slate-600 text-slate-200 hover:bg-slate-700 text-xs font-semibold gap-1.5 bg-slate-800"
                      >
                        <Eye className="w-3.5 h-3.5 text-indigo-400" /> Preview PDF
                      </Button>

                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => fileInputRef.current?.click()}
                        className="border-slate-600 text-slate-200 hover:bg-slate-700 text-xs font-semibold gap-1.5 bg-slate-800"
                      >
                        <RefreshCw className="w-3.5 h-3.5 text-slate-400" /> Replace File
                      </Button>

                      <Button
                        type="button"
                        size="sm"
                        disabled={!canUpload || submittingAnswer}
                        onClick={handleSubmitAnswerSheet}
                        className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold gap-1.5 ml-auto shadow-md"
                      >
                        {submittingAnswer ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                        Submit Answer Sheet
                      </Button>
                    </div>
                  </div>
                )}

                {/* Captured Pages Gallery with Page Badges and Reordering */}
                {capturedPages.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span className="font-semibold text-slate-200 uppercase tracking-wider">
                        Answer Pages ({capturedPages.length})
                      </span>
                      <span>Review page order before submitting</span>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                      {capturedPages.map((page, index) => (
                        <div
                          key={page.id}
                          className="bg-slate-800/90 border border-slate-700 rounded-xl overflow-hidden shadow-sm flex flex-col group relative"
                        >
                          {/* Page Number Badge */}
                          <div className="absolute top-2 left-2 z-10 bg-slate-950/80 backdrop-blur-sm text-white text-xs font-bold px-2 py-0.5 rounded-md border border-slate-700">
                            Page {index + 1}
                          </div>

                          {/* Image Thumbnail */}
                          <div className="aspect-[3/4] bg-slate-950 overflow-hidden flex items-center justify-center p-1">
                            <img
                              src={page.previewUrl}
                              alt={`Page ${index + 1}`}
                              className="w-full h-full object-contain transition-transform"
                              style={{ transform: `rotate(${page.rotation}deg)` }}
                            />
                          </div>

                          {/* Controls Footer */}
                          <div className="bg-slate-900 border-t border-slate-800 p-1.5 flex items-center justify-between gap-1 text-slate-400">
                            <div className="flex items-center gap-1">
                              <button
                                type="button"
                                onClick={() => movePage(index, "left")}
                                disabled={index === 0}
                                className="p-1 hover:bg-slate-800 rounded disabled:opacity-30"
                                title="Move Left"
                              >
                                <ArrowLeft className="w-3.5 h-3.5" />
                              </button>
                              <button
                                type="button"
                                onClick={() => movePage(index, "right")}
                                disabled={index === capturedPages.length - 1}
                                className="p-1 hover:bg-slate-800 rounded disabled:opacity-30"
                                title="Move Right"
                              >
                                <ArrowRight className="w-3.5 h-3.5" />
                              </button>
                            </div>
                            <div className="flex items-center gap-1">
                              <button
                                type="button"
                                onClick={() => rotatePage(index)}
                                className="p-1 hover:bg-slate-800 rounded"
                                title="Rotate 90°"
                              >
                                <RotateCw className="w-3.5 h-3.5" />
                              </button>
                              <button
                                type="button"
                                onClick={() => removePage(index)}
                                className="p-1 hover:bg-rose-950 text-rose-400 rounded"
                                title="Delete"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Submit Button */}
                <div className="pt-4 border-t border-slate-800">
                  <Button
                    type="button"
                    onClick={handleSubmitAnswerSheet}
                    disabled={
                      submittingAnswer ||
                      (!uploadedPdfFile && capturedPages.length === 0) ||
                      !canUpload
                    }
                    className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-sm rounded-xl shadow-lg transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {submittingAnswer ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" /> Compiling &amp; Uploading PDF...
                      </>
                    ) : (
                      <>
                        <Send className="w-4 h-4" /> Finalize &amp; Submit Answer Sheet
                      </>
                    )}
                  </Button>
                  <p className="text-[11px] text-slate-500 text-center mt-2">
                    Images will be automatically rotated, scaled, and compressed into a high-clarity A4 PDF.
                  </p>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
