"use client";

import { useState, useRef } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  UploadCloud,
  AlertCircle,
  CheckCircle,
  FileText,
  ChevronRight,
  Sparkles,
  Clock,
  FileCheck,
  Trash2,
  RefreshCw,
  ShieldCheck,
  Layers,
  BookOpen,
} from "lucide-react";
import { toast } from "react-hot-toast";
import { adminQuestionApi, ImportReport, ImportRow } from "@/lib/api/admin-questions";
import { adminExamApi, ObjectiveCategory } from "@/lib/api/admin-exams";
import { AcademicDependentSelect } from "@/components/admin/syllabus/AcademicDependentSelect";

type ImportCategory = Exclude<ObjectiveCategory, null | "custom">;
type ExamMode = "objective" | "subjective";

const MISSING_LABELS: Record<string, string> = {
  options: "Options A–D",
  correct_answer: "Correct answer",
  explanation: "Explanation",
};

const inputCls =
  "w-full p-2.5 border border-gray-200 rounded-lg bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-[#0B2545]/20";

const rowTone = (status: ImportRow["status"]) => {
  if (status === "valid") return "bg-green-50/50 border-green-100";
  if (status === "incomplete") return "bg-blue-50/50 border-blue-100";
  if (status === "duplicate") return "bg-amber-50/50 border-amber-100";
  return "bg-red-50/50 border-red-100";
};

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

export default function ImportExamPage() {
  const [examMode, setExamMode] = useState<ExamMode>("objective");
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [busy, setBusy] = useState(false);

  // Common Academic hierarchy
  const [category, setCategory] = useState<number | undefined>();
  const [position, setPosition] = useState<number | undefined>();
  const [subject, setSubject] = useState<number | undefined>();
  const [chapter, setChapter] = useState<number | undefined>();
  const [topic, setTopic] = useState<number | undefined>();

  // --- Objective Exam State ---
  const [objectiveTitle, setObjectiveTitle] = useState("");
  const [objectiveCategory, setObjectiveCategory] = useState<ImportCategory>("model");
  const [objectiveDuration, setObjectiveDuration] = useState<number>(60);
  const [objectiveFile, setObjectiveFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);

  // --- Subjective Exam State ---
  const [subjectiveTitle, setSubjectiveTitle] = useState("");
  const [writingDuration, setWritingDuration] = useState<number>(120);
  const [uploadDuration, setUploadDuration] = useState<number>(30);
  const [subjectivePdfFile, setSubjectivePdfFile] = useState<File | null>(null);
  const [pdfPageCount, setPdfPageCount] = useState<number>(0);
  const [pdfFileSize, setPdfFileSize] = useState<number>(0);
  const pdfInputRef = useRef<HTMLInputElement>(null);

  // --- Result State ---
  const [createdExamId, setCreatedExamId] = useState<number | null>(null);
  const [createdExamMode, setCreatedExamMode] = useState<ExamMode>("objective");
  const [importedIds, setImportedIds] = useState<number[] | null>(null);
  const [skippedDuplicates, setSkippedDuplicates] = useState(0);
  const [totalAttachedCount, setTotalAttachedCount] = useState(0);
  const [finishError, setFinishError] = useState<string | null>(null);

  const handleAcademicChange = (field: string, value: any) => {
    if (field === "category") {
      setCategory(value);
      setPosition(undefined);
      setSubject(undefined);
      setChapter(undefined);
      setTopic(undefined);
    } else if (field === "position" || field === "exam") {
      setPosition(value);
      setSubject(undefined);
      setChapter(undefined);
      setTopic(undefined);
    } else if (field === "subject") {
      setSubject(value);
      setChapter(undefined);
      setTopic(undefined);
    } else if (field === "chapter" || field === "unit") {
      setChapter(value);
      setTopic(undefined);
    } else if (field === "topic") {
      setTopic(value);
    }
  };

  const errMessage = (error: any, fallback: string) => {
    const data = error?.data;
    const firstField = data && typeof data === "object" ? Object.keys(data)[0] : null;
    return (
      data?.error ||
      data?.detail ||
      (firstField ? `${firstField}: ${Array.isArray(data[firstField]) ? data[firstField][0] : data[firstField]}` : null) ||
      error?.message ||
      fallback
    );
  };

  // ----------------------------------------------------
  // Objective Exam Handlers
  // ----------------------------------------------------
  const canAnalyzeObjective = Boolean(
    objectiveFile &&
      objectiveTitle.trim() &&
      objectiveDuration > 0 &&
      category &&
      position
  );

  const handleObjectiveUpload = async () => {
    if (!objectiveFile) return;
    setBusy(true);
    try {
      const res = await adminQuestionApi.uploadCSV(objectiveFile, {
        topic: topic || '',
      });
      setReport(res);
      setStep(2);
      toast.success(`Analyzed ${res.total_rows} rows`);
    } catch (error: any) {
      toast.error(errMessage(error, "Failed to analyze the file"));
    } finally {
      setBusy(false);
    }
  };

  const handleAiFill = async () => {
    if (!report) return;
    setBusy(true);
    try {
      setReport(await adminQuestionApi.aiFillImport(report.import_id));
      toast.success("AI filled the missing fields");
    } catch (error: any) {
      toast.error(errMessage(error, "AI could not fill the missing fields"));
    } finally {
      setBusy(false);
    }
  };

  const createObjectiveExamWith = async (allQuestionIds: number[], newIds: number[], duplicateCount: number) => {
    setFinishError(null);
    let createdId: number | null = createdExamId;
    try {
      if (!createdId) {
        const created = await adminExamApi.createExam({
          title: objectiveTitle.trim(),
          exam_type: "mock",
          objective_category: objectiveCategory,
          category,
          exam: position,
          subject: subject ?? null,
          time_limit: objectiveDuration, // Persisted server-authoritative duration!
        } as any);
        createdId = created.id;
        setCreatedExamId(created.id);
        setCreatedExamMode("objective");
      }
      if (allQuestionIds.length > 0) {
        await adminExamApi.addQuestions(createdId, allQuestionIds);
      }
      setTotalAttachedCount(allQuestionIds.length);
      setImportedIds(newIds);
      setSkippedDuplicates(duplicateCount);
      setStep(3);
    } catch (error: any) {
      setFinishError(errMessage(error, "Could not create the exam."));
    }
  };

  const handleObjectiveCommit = async () => {
    if (!report) return;
    setBusy(true);
    try {
      const res = await adminQuestionApi.commitCSV(report.import_id);
      const newIds = res.question_ids ?? [];
      const dupCount = res.skipped_duplicates?.length ?? 0;
      const allIds = res.all_question_ids ?? [...newIds, ...(res.existing_question_ids ?? [])];

      if (allIds.length === 0) {
        setFinishError("No valid or reusable questions were found in the file.");
        return;
      }

      await createObjectiveExamWith(allIds, newIds, dupCount);
    } catch (error: any) {
      toast.error(errMessage(error, "Failed to import"));
    } finally {
      setBusy(false);
    }
  };

  // ----------------------------------------------------
  // Subjective Exam Handlers
  // ----------------------------------------------------
  const handlePdfFileSelect = (file: File) => {
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      toast.error("Please upload a valid PDF document.");
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      toast.error("Question paper PDF must not exceed 20MB.");
      return;
    }
    setSubjectivePdfFile(file);
    setPdfFileSize(file.size);
  };

  const canCreateSubjective = Boolean(
    subjectiveTitle.trim() &&
      category &&
      position &&
      writingDuration > 0 &&
      uploadDuration >= 0 &&
      subjectivePdfFile
  );

  const handleCreateSubjectiveExam = async () => {
    if (!canCreateSubjective || !subjectivePdfFile) return;
    setBusy(true);
    setFinishError(null);
    try {
      // 1. Create canonical Examination with subjective configuration and dual timers
      const exam = await adminExamApi.createExam({
        title: subjectiveTitle.trim(),
        exam_type: "subjective",
        category,
        exam: position,
        subject: subject ?? null,
        time_limit: writingDuration, // Server-authoritative Writing Time
        upload_deadline_minutes: uploadDuration, // Server-authoritative Upload Window
        answer_upload_enabled: true,
        allowed_file_types: "jpg,jpeg,png,webp,pdf",
        max_upload_size_mb: 50,
        evaluation_type: "admin",
        status: "draft",
      } as any);

      // 2. Upload question paper PDF directly to the exam
      const uploadRes = await adminExamApi.uploadQuestionPaper(exam.id, subjectivePdfFile);
      setPdfPageCount(uploadRes.page_count);
      setPdfFileSize(uploadRes.file_size || subjectivePdfFile.size);

      // 3. Mark completion
      setCreatedExamId(exam.id);
      setCreatedExamMode("subjective");
      setStep(3);
      toast.success("Subjective examination created with Question Paper PDF!");
    } catch (error: any) {
      toast.error(errMessage(error, "Failed to create subjective exam."));
    } finally {
      setBusy(false);
    }
  };

  const resetAll = () => {
    setStep(1);
    setBusy(false);
    setObjectiveFile(null);
    setReport(null);
    setSubjectivePdfFile(null);
    setCreatedExamId(null);
    setImportedIds(null);
    setSkippedDuplicates(0);
    setTotalAttachedCount(0);
    setFinishError(null);
  };

  return (
    <div className="p-5 md:p-6 space-y-6 max-w-[1200px] mx-auto">
      {/* Top Header */}
      <div className="flex items-center gap-4">
        <Link href="/admin-dashboard/exams" className="p-2 hover:bg-gray-100 rounded-full transition-colors">
          <ArrowLeft className="w-5 h-5 text-gray-500" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Import Exam</h1>
          <p className="text-gray-500 mt-1">
            Create exams using either structured Objective questions or a Subjective Question Paper PDF with server-authoritative timers.
          </p>
        </div>
      </div>

      {/* Stepper */}
      <div className="flex items-center justify-between mb-8 px-4">
        {[
          { n: 1, label: examMode === "objective" ? "Details & Upload" : "Subjective Setup & PDF" },
          { n: 2, label: examMode === "objective" ? "Review & Import" : "Exam Review" },
          { n: 3, label: "Draft Exam Created" },
        ].map((s, i) => (
          <div key={s.n} className={i === 0 ? "flex items-center flex-1" : "flex items-center flex-1 justify-end"}>
            {i > 0 && <div className={`flex-1 h-1 mx-4 rounded ${step >= s.n ? "bg-[#0B2545]" : "bg-gray-100"}`} />}
            <div className="flex flex-col items-center gap-2">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center font-bold ${
                  step >= s.n ? "bg-[#0B2545] text-white" : "bg-gray-100 text-gray-400"
                }`}
              >
                {s.n}
              </div>
              <span className={`text-sm font-medium whitespace-nowrap ${step >= s.n ? "text-[#0B2545]" : "text-gray-400"}`}>
                {s.label}
              </span>
            </div>
          </div>
        ))}
      </div>

      {step === 1 && (
        <div className="space-y-6">
          {/* Mode Switcher */}
          <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm">
            <label className="block text-sm font-semibold text-gray-800 mb-2">Examination Mode &amp; Question Type</label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => setExamMode("objective")}
                className={`p-4 rounded-xl border text-left flex items-start gap-3 transition-all ${
                  examMode === "objective"
                    ? "border-[#0B2545] bg-blue-50/40 ring-2 ring-[#0B2545]/10"
                    : "border-gray-200 hover:bg-gray-50 text-gray-600"
                }`}
              >
                <div
                  className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                    examMode === "objective" ? "bg-[#0B2545] text-white" : "bg-gray-100 text-gray-500"
                  }`}
                >
                  <CheckCircle className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-gray-900">Objective Examination</h3>
                  <p className="text-xs text-gray-500 mt-1">
                    Multiple Choice &amp; True/False questions. Uploaded questions populate the canonical Master Question Bank with automatic duplicate reuse. Single exam countdown.
                  </p>
                </div>
              </button>

              <button
                type="button"
                onClick={() => setExamMode("subjective")}
                className={`p-4 rounded-xl border text-left flex items-start gap-3 transition-all ${
                  examMode === "subjective"
                    ? "border-purple-600 bg-purple-50/40 ring-2 ring-purple-600/10"
                    : "border-gray-200 hover:bg-gray-50 text-gray-600"
                }`}
              >
                <div
                  className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                    examMode === "subjective" ? "bg-purple-600 text-white" : "bg-gray-100 text-gray-500"
                  }`}
                >
                  <FileText className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-gray-900">Subjective Examination</h3>
                  <p className="text-xs text-gray-500 mt-1">
                    Upload official Question Paper PDF. Persistent Dual Timers (Writing Time + Upload Window). Handwritten answer capture, A4 compilation, and evaluator grading. Does NOT pollute Question Bank.
                  </p>
                </div>
              </button>
            </div>
          </div>

          {/* ========================================================= */}
          {/* OBJECTIVE EXAM WORKFLOW                                   */}
          {/* ========================================================= */}
          {examMode === "objective" && (
            <div className="space-y-6">
              <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm space-y-6">
                <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                  <CheckCircle className="w-5 h-5 text-blue-600" />
                  Objective Exam Configuration
                </h2>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="md:col-span-2">
                    <label htmlFor="obj-title" className="block text-sm font-medium text-gray-700 mb-1">
                      Exam Title <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="obj-title"
                      value={objectiveTitle}
                      onChange={(e) => setObjectiveTitle(e.target.value)}
                      placeholder="e.g. PSC Section Officer Paper I – Objective Model Test 01"
                      className={inputCls}
                    />
                  </div>

                  <div>
                    <label htmlFor="obj-cat" className="block text-sm font-medium text-gray-700 mb-1">
                      Exam Category
                    </label>
                    <select
                      id="obj-cat"
                      value={objectiveCategory}
                      onChange={(e) => setObjectiveCategory(e.target.value as ImportCategory)}
                      className={inputCls}
                    >
                      <option value="model">Model Exam</option>
                      <option value="old_past">Old Past Exam</option>
                      <option value="live">Live Exam</option>
                    </select>
                  </div>

                  <div>
                    <label htmlFor="obj-duration" className="block text-sm font-medium text-gray-700 mb-1">
                      Exam Duration (Minutes) <span className="text-red-500">*</span>
                    </label>
                    <div className="relative">
                      <input
                        id="obj-duration"
                        type="number"
                        min={1}
                        max={600}
                        value={objectiveDuration}
                        onChange={(e) => setObjectiveDuration(Math.max(1, parseInt(e.target.value) || 1))}
                        className={inputCls}
                      />
                      <span className="absolute right-3 top-2.5 text-xs text-gray-400 font-semibold pointer-events-none">
                        mins
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">
                      Server-authoritative timer. Students cannot reset timer on refresh or navigation.
                    </p>
                  </div>
                </div>

                <div className="pt-6 border-t border-gray-100">
                  <h3 className="text-sm font-semibold text-gray-900 mb-1">Syllabus &amp; Question Bank Target</h3>
                  <p className="text-sm text-gray-500 mb-4">
                    Category and Position are required. Subject, Chapter, and Topic are optional — questions will be stored under the selected Topic in the Master Question Bank if provided.
                  </p>
                  <AcademicDependentSelect
                    category={category}
                    position={position}
                    subject={subject}
                    chapter={chapter}
                    topic={topic}
                    onChange={handleAcademicChange}
                    maxLevel="topic"
                    requiredLevels={["category", "position"]}
                    layout="grid"
                  />
                </div>
              </div>

              {/* Upload Box for Objective */}
              <div className="bg-white p-8 rounded-xl border border-gray-200 shadow-sm">
                <div className="max-w-xl mx-auto flex flex-col items-center">
                  <div className="bg-blue-50 w-16 h-16 rounded-full flex items-center justify-center mb-6">
                    <UploadCloud className="w-8 h-8 text-blue-600" />
                  </div>
                  <h2 className="text-xl font-bold text-gray-900 mb-2">Upload Objective Questions Spreadsheet</h2>
                  <p className="text-gray-500 text-center mb-6 text-sm">
                    Upload an Excel (.xlsx) or CSV file with questions. Questions will be validated, deduplicated, and added to the Master Question Bank. Question format and difficulty are automatically parsed from each row in the imported file.
                  </p>
                  <button
                    type="button"
                    onClick={() =>
                      adminQuestionApi
                        .downloadTemplate()
                        .catch((e: any) => toast.error(e?.message || "Failed to download template"))
                    }
                    className="text-[#0B2545] font-medium hover:underline flex items-center gap-2 mb-6"
                  >
                    <FileText className="w-4 h-4" /> Download Question Import Template (.xlsx)
                  </button>

                  <div className="w-full border-2 border-dashed border-gray-300 rounded-xl p-8 hover:bg-gray-50 transition-colors text-center relative">
                    <input
                      type="file"
                      aria-label="Excel file"
                      accept=".xlsx,.xls,.csv"
                      onChange={(e) => e.target.files?.[0] && setObjectiveFile(e.target.files[0])}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    />
                    {!objectiveFile ? (
                      <div>
                        <p className="font-medium text-gray-700">Click to browse or drag and drop</p>
                        <p className="text-sm text-gray-500 mt-1">.xlsx, .xls or .csv</p>
                      </div>
                    ) : (
                      <div className="flex items-center justify-center gap-3">
                        <CheckCircle className="w-6 h-6 text-green-500" />
                        <span className="font-medium text-gray-900">{objectiveFile.name}</span>
                        <span className="text-xs text-gray-400">({formatBytes(objectiveFile.size)})</span>
                      </div>
                    )}
                  </div>

                  {!canAnalyzeObjective && (
                    <p className="text-sm text-amber-600 mt-4 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4" /> Please enter a title, select category and position, set duration (&gt;0), and choose a file.
                    </p>
                  )}

                  <button
                    disabled={!canAnalyzeObjective || busy}
                    onClick={handleObjectiveUpload}
                    className="w-full mt-6 bg-[#0B2545] hover:bg-[#163E6C] disabled:opacity-50 disabled:cursor-not-allowed text-white py-3 rounded-xl font-medium flex items-center justify-center gap-2 transition-colors"
                  >
                    {busy ? "Analyzing Questions..." : "Analyze & Validate Questions"}
                    {!busy && <ChevronRight className="w-5 h-5" />}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ========================================================= */}
          {/* SUBJECTIVE EXAM WORKFLOW                                  */}
          {/* ========================================================= */}
          {examMode === "subjective" && (
            <div className="space-y-6">
              <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm space-y-6">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                    <FileText className="w-5 h-5 text-purple-600" />
                    Subjective Examination Details
                  </h2>
                  <span className="text-xs bg-purple-100 text-purple-800 font-semibold px-2.5 py-1 rounded-full">
                    PDF Question Paper
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="md:col-span-2">
                    <label htmlFor="subj-title" className="block text-sm font-medium text-gray-700 mb-1">
                      Subjective Exam Title <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="subj-title"
                      value={subjectiveTitle}
                      onChange={(e) => setSubjectiveTitle(e.target.value)}
                      placeholder="e.g. Section Officer Paper II - Governance and Public Administration"
                      className={inputCls}
                    />
                  </div>

                  {/* Dual Timers Section */}
                  <div className="md:col-span-2 bg-gradient-to-r from-purple-50 to-indigo-50 border border-purple-100 p-5 rounded-xl space-y-4">
                    <div className="flex items-center gap-2 text-purple-900 font-semibold text-sm">
                      <Clock className="w-5 h-5 text-purple-600" />
                      Server-Authoritative Dual Timers Configuration
                    </div>
                    <p className="text-xs text-purple-700">
                      Subjective exams require two distinct server deadlines: Writing Duration for pen-and-paper writing, followed by an Answer Upload Window for mobile photo submission.
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="bg-white p-4 rounded-lg border border-purple-200 shadow-sm">
                        <label htmlFor="writing-duration" className="block text-sm font-bold text-gray-800 mb-1">
                          1. Answer Writing Time <span className="text-red-500">*</span>
                        </label>
                        <div className="relative mt-2">
                          <input
                            id="writing-duration"
                            type="number"
                            min={1}
                            max={600}
                            value={writingDuration}
                            onChange={(e) => setWritingDuration(Math.max(1, parseInt(e.target.value) || 1))}
                            className={inputCls}
                          />
                          <span className="absolute right-3 top-2.5 text-xs text-gray-500 font-semibold pointer-events-none">
                            mins
                          </span>
                        </div>
                        <p className="text-xs text-gray-500 mt-2">
                          Time students have to read question paper and write answers on paper.
                        </p>
                      </div>

                      <div className="bg-white p-4 rounded-lg border border-purple-200 shadow-sm">
                        <label htmlFor="upload-duration" className="block text-sm font-bold text-gray-800 mb-1">
                          2. Answer Upload Window <span className="text-red-500">*</span>
                        </label>
                        <div className="relative mt-2">
                          <input
                            id="upload-duration"
                            type="number"
                            min={0}
                            max={180}
                            value={uploadDuration}
                            onChange={(e) => setUploadDuration(Math.max(0, parseInt(e.target.value) || 0))}
                            className={inputCls}
                          />
                          <span className="absolute right-3 top-2.5 text-xs text-gray-500 font-semibold pointer-events-none">
                            mins
                          </span>
                        </div>
                        <p className="text-xs text-gray-500 mt-2">
                          Upload deadline after writing ends to photograph &amp; upload answer sheets.
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 text-xs text-purple-800 font-medium bg-white/70 px-3 py-2 rounded-lg border border-purple-200">
                      <ShieldCheck className="w-4 h-4 text-purple-600 shrink-0" />
                      <span>
                        Total Session Window: <strong>{writingDuration + uploadDuration} minutes</strong> ({writingDuration}m Writing + {uploadDuration}m Upload). Back/Refresh will NOT extend or reset either timer.
                      </span>
                    </div>
                  </div>
                </div>

                <div className="pt-6 border-t border-gray-100">
                  <h3 className="text-sm font-semibold text-gray-900 mb-1">Syllabus Scope</h3>
                  <p className="text-sm text-gray-500 mb-4">
                    Select the target Category and Position/Exam (Subject is optional) for this subjective examination.
                  </p>
                  <AcademicDependentSelect
                    category={category}
                    position={position}
                    subject={subject}
                    onChange={handleAcademicChange}
                    maxLevel="subject"
                    requiredLevels={["category", "position"]}
                    layout="grid"
                  />
                </div>
              </div>

              {/* Upload Box for Subjective Question Paper PDF */}
              <div className="bg-white p-8 rounded-xl border border-gray-200 shadow-sm">
                <div className="max-w-xl mx-auto flex flex-col items-center">
                  <div className="bg-purple-50 w-16 h-16 rounded-full flex items-center justify-center mb-6">
                    <FileText className="w-8 h-8 text-purple-600" />
                  </div>
                  <h2 className="text-xl font-bold text-gray-900 mb-2">Upload Question Paper PDF</h2>
                  <p className="text-gray-500 text-center mb-6 text-sm">
                    Upload the official PDF question paper. Students will view or download this document during their active writing window.
                  </p>

                  <div className="w-full border-2 border-dashed border-gray-300 rounded-xl p-8 hover:bg-gray-50 transition-colors text-center relative">
                    <input
                      ref={pdfInputRef}
                      type="file"
                      aria-label="Question Paper PDF"
                      accept=".pdf,application/pdf"
                      onChange={(e) => e.target.files?.[0] && handlePdfFileSelect(e.target.files[0])}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    />
                    {!subjectivePdfFile ? (
                      <div>
                        <UploadCloud className="w-10 h-10 text-gray-400 mx-auto mb-2" />
                        <p className="font-medium text-gray-700">Click to select or drag and drop PDF</p>
                        <p className="text-xs text-gray-400 mt-1">PDF format only (Max 20MB)</p>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        <div className="flex items-center justify-center gap-3">
                          <FileCheck className="w-8 h-8 text-purple-600" />
                          <div className="text-left">
                            <p className="font-semibold text-gray-900">{subjectivePdfFile.name}</p>
                            <p className="text-xs text-gray-500">{formatBytes(pdfFileSize)} • Ready for attach</p>
                          </div>
                        </div>
                        <div className="flex justify-center gap-3 pt-2">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSubjectivePdfFile(null);
                              if (pdfInputRef.current) pdfInputRef.current.value = "";
                            }}
                            className="text-xs text-red-600 hover:text-red-700 flex items-center gap-1 bg-red-50 hover:bg-red-100 px-3 py-1.5 rounded-lg font-medium transition-colors"
                          >
                            <Trash2 className="w-3.5 h-3.5" /> Remove
                          </button>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Clean Master Question Bank Notice */}
                  <div className="mt-6 bg-slate-50 border border-slate-200 rounded-xl p-4 w-full flex items-start gap-3">
                    <ShieldCheck className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                    <div className="text-xs text-slate-600 leading-relaxed">
                      <strong className="text-slate-800">Master Question Bank Protection:</strong> Subjective Question Paper PDFs are scoped strictly to this Examination and will <strong>NOT</strong> create Question records or alter Master Question Bank counts.
                    </div>
                  </div>

                  {!canCreateSubjective && (
                    <p className="text-sm text-amber-600 mt-4 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4" /> Please provide title, category, position, valid durations, and select a PDF file.
                    </p>
                  )}

                  <button
                    disabled={!canCreateSubjective || busy}
                    onClick={handleCreateSubjectiveExam}
                    className="w-full mt-6 bg-[#0B2545] hover:bg-[#163E6C] disabled:opacity-50 disabled:cursor-not-allowed text-white py-3 rounded-xl font-medium flex items-center justify-center gap-2 transition-colors shadow-sm"
                  >
                    {busy ? "Creating Subjective Exam & Uploading PDF..." : "Create Subjective Exam"}
                    {!busy && <ChevronRight className="w-5 h-5" />}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ========================================================= */}
      {/* STEP 2: OBJECTIVE REVIEW & COMMIT                         */}
      {/* ========================================================= */}
      {step === 2 && report && examMode === "objective" && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {[
              { label: "Total Rows", value: report.total_rows, tone: "border-gray-100 text-gray-900", lbl: "text-gray-500" },
              { label: "Ready", value: report.valid_rows, tone: "border-green-100 text-green-700", lbl: "text-green-600" },
              { label: "Needs Info", value: report.incomplete_rows, tone: "border-blue-100 text-blue-700", lbl: "text-blue-600" },
              { label: "Duplicates", value: report.duplicate_rows, tone: "border-amber-100 text-amber-700", lbl: "text-amber-600" },
              { label: "Errors", value: report.error_rows, tone: "border-red-100 text-red-700", lbl: "text-red-600" },
            ].map((c) => (
              <div key={c.label} className={`bg-white p-6 rounded-xl border text-center ${c.tone.split(" ")[0]}`}>
                <p className={`text-sm font-medium ${c.lbl}`}>{c.label}</p>
                <p className={`text-3xl font-bold mt-2 ${c.tone.split(" ")[1]}`}>{c.value}</p>
              </div>
            ))}
          </div>

          {report.incomplete_rows > 0 && (
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <Sparkles className="w-5 h-5 text-blue-600 mt-0.5" />
                <p className="font-semibold text-blue-900">
                  {report.incomplete_rows} row{report.incomplete_rows === 1 ? " is" : "s are"} missing information — the AI can fill it in.
                </p>
              </div>
              <button
                onClick={handleAiFill}
                disabled={busy}
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg font-medium whitespace-nowrap"
              >
                {busy ? "Filling..." : "Fill missing fields with AI"}
              </button>
            </div>
          )}

          {report.duplicate_rows > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
              <Layers className="w-5 h-5 text-amber-700 shrink-0 mt-0.5" />
              <div className="text-sm text-amber-800">
                <strong>Duplicate Reuse Active:</strong> {report.duplicate_rows} question(s) already exist in the Master Question Bank. They will be <strong>reused</strong> and attached to this exam without creating duplicate Question records.
              </div>
            </div>
          )}

          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
            <div className="p-4 border-b border-gray-200 bg-gray-50 flex justify-between items-center">
              <h3 className="font-bold text-gray-900">Validation Report</h3>
              <p className="text-sm text-gray-500">Ready questions and existing canonical questions will be attached to the exam.</p>
            </div>
            <div className="max-h-[400px] overflow-y-auto p-4 space-y-3">
              {report.report_data.map((row) => (
                <div key={row.row_index} className={`p-3 border rounded-lg ${rowTone(row.status)}`}>
                  <p className="text-sm font-medium text-gray-900">
                    Row {row.row_index}: {row.data.question || "(no question text)"}
                  </p>
                  {row.missing?.length > 0 && (
                    <p className="mt-1 text-sm text-blue-700">
                      Missing: {row.missing.map((m) => MISSING_LABELS[m] || m).join(", ")}
                    </p>
                  )}
                  {row.errors?.length > 0 && (
                    <ul className="mt-1 list-disc list-inside text-sm text-red-600">
                      {row.errors.map((err, j) => (
                        <li key={j}>{err}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </div>

          {finishError && (
            <div role="alert" className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 flex flex-wrap items-center justify-between gap-3">
              <span>{finishError}</span>
            </div>
          )}

          <div className="flex justify-end gap-3">
            <button onClick={resetAll} className="px-6 py-3 font-medium text-gray-700 hover:bg-gray-100 rounded-xl transition-colors">
              Cancel &amp; Start Over
            </button>
            <button
              disabled={(report.valid_rows === 0 && report.duplicate_rows === 0) || busy}
              onClick={handleObjectiveCommit}
              className="px-8 py-3 font-medium text-white bg-[#0B2545] hover:bg-[#163E6C] disabled:opacity-50 disabled:cursor-not-allowed rounded-xl transition-colors shadow-sm"
            >
              {busy ? "Importing & Creating Exam..." : `Import & Create Exam (${report.valid_rows + report.duplicate_rows} Questions)`}
            </button>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* STEP 3: CREATED CONFIRMATION                              */}
      {/* ========================================================= */}
      {step === 3 && (
        <div className="bg-white p-8 rounded-xl border border-gray-200 shadow-sm text-center max-w-2xl mx-auto">
          <div className="w-20 h-20 bg-green-50 rounded-full flex items-center justify-center mx-auto mb-6">
            <CheckCircle className="w-10 h-10 text-green-500" />
          </div>

          <span className="text-xs uppercase tracking-wider font-bold px-3 py-1 rounded-full bg-slate-100 text-slate-700">
            {createdExamMode === "objective" ? "Objective Examination Created" : "Subjective Examination Created"}
          </span>

          <h2 className="text-2xl font-bold text-gray-900 mt-3 mb-2">
            &ldquo;{createdExamMode === "objective" ? objectiveTitle.trim() : subjectiveTitle.trim()}&rdquo;
          </h2>

          <p className="text-gray-500 mb-6 text-sm">
            {createdExamMode === "objective" ? (
              <>
                Created as draft with <strong>{totalAttachedCount}</strong> questions attached ({importedIds?.length ?? 0} new in Master Question Bank, {skippedDuplicates} existing canonical questions reused). Exam duration configured to <strong>{objectiveDuration} minutes</strong>.
              </>
            ) : (
              <>
                Subjective exam created with <strong>{writingDuration} minutes</strong> writing time and <strong>{uploadDuration} minutes</strong> upload deadline. Question Paper PDF attached ({pdfPageCount} pages, {formatBytes(pdfFileSize)}). Master Question Bank remains clean.
              </>
            )}
          </p>

          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 mb-8 text-left space-y-2 text-xs text-slate-700">
            <div className="flex justify-between py-1 border-b border-slate-200">
              <span className="text-slate-500 font-medium">Exam Type:</span>
              <span className="font-semibold text-slate-900 capitalize">{createdExamMode}</span>
            </div>
            {createdExamMode === "objective" ? (
              <>
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-500 font-medium">Exam Duration:</span>
                  <span className="font-semibold text-slate-900">{objectiveDuration} minutes (Server-enforced)</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-500 font-medium">Total Questions Attached:</span>
                  <span className="font-semibold text-slate-900">{totalAttachedCount}</span>
                </div>
              </>
            ) : (
              <>
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-500 font-medium">Answer Writing Duration:</span>
                  <span className="font-semibold text-purple-900">{writingDuration} minutes</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-500 font-medium">Answer Sheet Upload Window:</span>
                  <span className="font-semibold text-purple-900">{uploadDuration} minutes</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-500 font-medium">Question Paper PDF:</span>
                  <span className="font-semibold text-slate-900">{subjectivePdfFile?.name || "Attached"}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-500 font-medium">Master Question Bank:</span>
                  <span className="font-semibold text-emerald-700">0 questions added (Isolated)</span>
                </div>
              </>
            )}
          </div>

          <div className="flex flex-wrap justify-center gap-4">
            <Link
              href="/admin-dashboard/exams"
              className="px-6 py-3 font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-xl transition-colors"
            >
              Back to Exams
            </Link>
            {createdExamMode === "subjective" && createdExamId && (
              <Link
                href={`/admin-dashboard/exams/${createdExamId}/submissions`}
                className="px-6 py-3 font-medium text-purple-700 bg-purple-50 hover:bg-purple-100 rounded-xl transition-colors border border-purple-200"
              >
                Submissions Dashboard
              </Link>
            )}
            <Link
              href={`/admin-dashboard/exams/new?draft=${createdExamId}`}
              className="px-6 py-3 font-medium text-white bg-[#0B2545] hover:bg-[#163E6C] rounded-xl transition-colors"
            >
              Continue Setting Up
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
