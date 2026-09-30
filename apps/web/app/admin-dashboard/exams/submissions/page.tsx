"use client";

import React, { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  FileText, Search, Loader2, CheckCircle2, Clock,
  Award, ArrowLeft, ArrowRight, RefreshCw, Download,
  Camera
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { adminExamApi, AdminSubjectiveSubmission } from "@/lib/api/admin-exams";
import toast from "react-hot-toast";

export default function GlobalSubjectiveSubmissionsPage() {
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [fileTypeFilter, setFileTypeFilter] = useState<"all" | "pdf" | "images">("all");
  const [selectedExamId, setSelectedExamId] = useState<string>("all");

  const {
    data: rawSubmissions = [],
    isLoading,
    isRefetching,
    refetch,
  } = useQuery({
    queryKey: ["admin", "all-subjective-submissions", selectedExamId, statusFilter, searchTerm],
    queryFn: () => adminExamApi.getAllSubjectiveSubmissions({
      exam_id: selectedExamId !== "all" ? Number(selectedExamId) : undefined,
      status: statusFilter !== "all" ? statusFilter : undefined,
      search: searchTerm.trim() || undefined,
    }),
    refetchInterval: 15000,
  });

  const submissions = useMemo(() => {
    return Array.isArray(rawSubmissions) ? rawSubmissions : (rawSubmissions as any)?.results || [];
  }, [rawSubmissions]);

  // Unique exams list for filter dropdown
  const uniqueExams = useMemo(() => {
    const map = new Map<number, string>();
    submissions.forEach((s: AdminSubjectiveSubmission) => {
      if (s.examination_id && s.examination_title) {
        map.set(s.examination_id, s.examination_title);
      }
    });
    return Array.from(map.entries()).map(([id, title]) => ({ id, title }));
  }, [submissions]);

  // Aggregate Real Backend Metrics
  const stats = useMemo(() => {
    const total = submissions.length;
    const pending = submissions.filter((s: AdminSubjectiveSubmission) => !s.is_published && s.status !== "evaluated").length;
    const evaluated = submissions.filter((s: AdminSubjectiveSubmission) => s.status === "evaluated" && !s.is_published).length;
    const published = submissions.filter((s: AdminSubjectiveSubmission) => s.is_published).length;
    return { total, pending, evaluated, published };
  }, [submissions]);

  // Client-side refinement for file type
  const filteredSubmissions = useMemo(() => {
    return submissions.filter((s: AdminSubjectiveSubmission) => {
      if (fileTypeFilter === "pdf" && !s.has_answer_pdf && !s.is_pdf) return false;
      if (fileTypeFilter === "images" && (s.has_answer_pdf || s.is_pdf)) return false;
      return true;
    });
  }, [submissions, fileTypeFilter]);

  const handleDownloadPdf = async (e: React.MouseEvent, submissionId: number, studentName: string) => {
    e.stopPropagation();
    try {
      const blob = await adminExamApi.getAnswerSheetBlob(submissionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `answer-sheet-${studentName.replace(/\s+/g, "_")}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Could not download answer sheet PDF.");
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            href="/admin-dashboard/exams"
            className="p-2 rounded-lg text-slate-500 hover:text-[#0B2545] hover:bg-slate-100 transition-colors"
            title="Back to Exams"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-2xl sm:text-3xl font-black text-[#0B2545] tracking-tight">
              Subjective Exam Submissions
            </h1>
            <p className="text-slate-500 text-sm mt-1">
              Centralized evaluation workspace for candidate answer sheets, PDF inspection, and official grading.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isRefetching}
            className="text-xs font-semibold gap-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefetching ? "animate-spin text-indigo-600" : ""}`} />
            Refresh
          </Button>
          <Link href="/admin-dashboard/exams/new">
            <Button className="bg-[#0B2545] text-white hover:bg-[#163E6C] text-xs font-bold">
              Create Subjective Exam
            </Button>
          </Link>
        </div>
      </div>

      {/* Analytics / Stats Banner */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-xs font-bold uppercase tracking-wider">Total Submissions</span>
            <FileText className="w-4 h-4 text-slate-400" />
          </div>
          <p className="text-2xl font-black text-[#0B2545] mt-1.5">{stats.total}</p>
          <span className="text-xs text-slate-400 mt-1 block">Answer sheets uploaded</span>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
          <div className="flex items-center justify-between text-amber-600">
            <span className="text-xs font-bold uppercase tracking-wider">Pending Evaluation</span>
            <Clock className="w-4 h-4 text-amber-500" />
          </div>
          <p className="text-2xl font-black text-amber-700 mt-1.5">{stats.pending}</p>
          <span className="text-xs text-slate-400 mt-1 block">Awaiting examiner scoring</span>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
          <div className="flex items-center justify-between text-indigo-600">
            <span className="text-xs font-bold uppercase tracking-wider">Evaluated (Draft)</span>
            <Award className="w-4 h-4 text-indigo-500" />
          </div>
          <p className="text-2xl font-black text-indigo-700 mt-1.5">{stats.evaluated}</p>
          <span className="text-xs text-slate-400 mt-1 block">Scored, ready to publish</span>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
          <div className="flex items-center justify-between text-emerald-600">
            <span className="text-xs font-bold uppercase tracking-wider">Published Results</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          </div>
          <p className="text-2xl font-black text-emerald-700 mt-1.5">{stats.published}</p>
          <span className="text-xs text-slate-400 mt-1 block">Visible to candidate</span>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col lg:flex-row items-center justify-between gap-4">
        <div className="relative w-full lg:w-80">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input
            placeholder="Search candidate name, email, exam..."
            className="pl-9 bg-slate-50 border-slate-200 text-slate-900"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="flex flex-wrap items-center gap-2 w-full lg:w-auto">
          {/* Exam Filter */}
          {uniqueExams.length > 0 && (
            <select
              value={selectedExamId}
              onChange={(e) => setSelectedExamId(e.target.value)}
              className="px-3 py-2 bg-white border border-slate-200 text-slate-700 text-xs font-semibold rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4A72C] max-w-[200px] truncate"
            >
              <option value="all">All Exams</option>
              {uniqueExams.map((ex) => (
                <option key={ex.id} value={ex.id}>
                  {ex.title}
                </option>
              ))}
            </select>
          )}

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 bg-white border border-slate-200 text-slate-700 text-xs font-semibold rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4A72C]"
          >
            <option value="all">All Evaluation Statuses</option>
            <option value="pending">Pending Evaluation</option>
            <option value="evaluated">Evaluated (Draft)</option>
            <option value="published">Result Published</option>
          </select>

          {/* File Type Filter */}
          <select
            value={fileTypeFilter}
            onChange={(e) => setFileTypeFilter(e.target.value as any)}
            className="px-3 py-2 bg-white border border-slate-200 text-slate-700 text-xs font-semibold rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4A72C]"
          >
            <option value="all">All File Types</option>
            <option value="pdf">PDF Answer Sheets</option>
            <option value="images">Image Uploads</option>
          </select>

          <Button
            variant="ghost"
            size="sm"
            className="text-blue-600 hover:text-blue-700 hover:bg-blue-50 text-xs"
            onClick={() => {
              setSearchTerm("");
              setStatusFilter("all");
              setFileTypeFilter("all");
              setSelectedExamId("all");
            }}
          >
            Clear
          </Button>
        </div>
      </div>

      {/* Submissions Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-slate-50 hover:bg-slate-50">
                <TableHead className="text-slate-700">Student</TableHead>
                <TableHead className="text-slate-700">Exam</TableHead>
                <TableHead className="text-slate-700">Submission File</TableHead>
                <TableHead className="text-slate-700">Submitted At</TableHead>
                <TableHead className="text-slate-700">Evaluation Status</TableHead>
                <TableHead className="text-slate-700">Marks</TableHead>
                <TableHead className="text-right text-slate-700">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={7} className="h-32 text-center bg-white">
                    <Loader2 className="h-6 w-6 animate-spin mx-auto text-slate-400" />
                  </TableCell>
                </TableRow>
              ) : filteredSubmissions.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="h-32 text-center text-slate-500 bg-white">
                    No subjective submissions match the selected criteria.
                  </TableCell>
                </TableRow>
              ) : (
                filteredSubmissions.map((sub: AdminSubjectiveSubmission) => {
                  const isPdf = sub.has_answer_pdf || sub.is_pdf;
                  const isPublished = sub.is_published;
                  const isEvaluated = sub.status === "evaluated";

                  return (
                    <TableRow key={sub.id} className="hover:bg-slate-50/50 border-b border-slate-200">
                      {/* Student */}
                      <TableCell>
                        <div>
                          <p className="font-bold text-[#0B2545]">{sub.student_name}</p>
                          <p className="text-xs text-slate-500">
                            {sub.student_email || `@${sub.student_username}`}
                          </p>
                        </div>
                      </TableCell>

                      {/* Exam */}
                      <TableCell>
                        <div className="max-w-[220px]">
                          <p className="font-semibold text-slate-800 text-xs truncate" title={sub.examination_title}>
                            {sub.examination_title}
                          </p>
                          <span className="text-[11px] text-slate-400">Attempt #{sub.attempt_id}</span>
                        </div>
                      </TableCell>

                      {/* File Type & Details */}
                      <TableCell>
                        <div className="flex flex-col gap-1">
                          <div className="flex items-center gap-1.5">
                            {isPdf ? (
                              <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200 text-[10px] font-bold inline-flex items-center gap-1">
                                <FileText className="w-3 h-3" /> PDF
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200 text-[10px] font-bold inline-flex items-center gap-1">
                                <Camera className="w-3 h-3" /> Images
                              </Badge>
                            )}
                            <span className="text-xs text-slate-600 font-medium truncate max-w-[130px]">
                              {sub.file_name || (isPdf ? "answer-sheet.pdf" : `${sub.page_count} pages`)}
                            </span>
                          </div>
                          <span className="text-[11px] text-slate-400">
                            {sub.page_count} {sub.page_count === 1 ? "page" : "pages"}
                            {sub.file_size_bytes > 0 && ` · ${(sub.file_size_bytes / (1024 * 1024)).toFixed(1)} MB`}
                          </span>
                        </div>
                      </TableCell>

                      {/* Submitted At */}
                      <TableCell>
                        <div className="text-xs text-slate-600">
                          <p className="font-medium text-slate-700">
                            {sub.submitted_at
                              ? new Date(sub.submitted_at).toLocaleDateString("en-US", {
                                  month: "short",
                                  day: "numeric",
                                  year: "numeric",
                                })
                              : "—"}
                          </p>
                          {sub.submitted_at && (
                            <p className="text-slate-400">
                              {new Date(sub.submitted_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                            </p>
                          )}
                        </div>
                      </TableCell>

                      {/* Evaluation Status */}
                      <TableCell>
                        {isPublished ? (
                          <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px] font-bold inline-flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" /> Result Published
                          </Badge>
                        ) : isEvaluated ? (
                          <Badge variant="outline" className="bg-indigo-50 text-indigo-700 border-indigo-200 text-[10px] font-bold inline-flex items-center gap-1">
                            <Award className="w-3 h-3" /> Evaluated (Draft)
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200 text-[10px] font-bold inline-flex items-center gap-1">
                            <Clock className="w-3 h-3" /> Pending Evaluation
                          </Badge>
                        )}
                      </TableCell>

                      {/* Marks */}
                      <TableCell>
                        {isEvaluated || isPublished ? (
                          <div className="text-xs">
                            <p className="font-bold text-[#0B2545]">
                              {sub.score} / {sub.total_marks}
                            </p>
                            <p className="text-slate-400 font-medium">{sub.percentage}%</p>
                          </div>
                        ) : (
                          <span className="text-xs text-slate-400 italic">Not graded</span>
                        )}
                      </TableCell>

                      {/* Action */}
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {isPdf && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={(e) => handleDownloadPdf(e, sub.id, sub.student_name)}
                              className="h-8 px-2 text-slate-600 hover:text-slate-900"
                              title="Download Answer Sheet PDF"
                            >
                              <Download className="w-3.5 h-3.5" />
                            </Button>
                          )}
                          <Link href={`/admin-dashboard/exams/${sub.examination_id}/submissions/${sub.attempt_id}`}>
                            <Button
                              size="sm"
                              className={`h-8 text-xs font-bold gap-1 ${
                                isPublished
                                  ? "bg-slate-100 hover:bg-slate-200 text-slate-800"
                                  : isEvaluated
                                  ? "bg-indigo-600 hover:bg-indigo-700 text-white"
                                  : "bg-[#0B2545] hover:bg-[#163E6C] text-white"
                              }`}
                            >
                              {isPublished ? "View Evaluation" : isEvaluated ? "Review & Publish" : "Evaluate"}
                              <ArrowRight className="w-3.5 h-3.5" />
                            </Button>
                          </Link>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
