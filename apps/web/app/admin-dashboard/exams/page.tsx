"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { 
  Search, Filter, PlusCircle, FileText, ChevronRight, MoreHorizontal, ClipboardList, Inbox, Award,
  Clock, DownloadCloud, Lock, Unlock, Eye, HelpCircle, Archive, Trash2, Calendar
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
  DropdownMenuSeparator
} from "@/components/ui/dropdown-menu";
import { adminExamApi, Examination, ObjectiveCategory } from "@/lib/api/admin-exams";
import { toast } from "sonner";

const CATEGORY_LABELS: Record<string, string> = {
  past_year: "Past Year Paper",
  model: "Model Exam",
  live: "Live Exam",
  topicwise: "Topicwise Exam",
};

const CategoryBadge = ({ category, examType }: { category: ObjectiveCategory; examType?: string }) => {
  if (examType === "subjective") {
    return <Badge variant="outline" className="bg-purple-50 text-purple-700 border-purple-200 font-bold">Subjective Exam</Badge>;
  }
  if (examType === "subject" || category === "topicwise") {
    return <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 font-bold">Topicwise Test</Badge>;
  }
  if (category) {
    const styles: Record<string, string> = {
      past_year: "bg-slate-100 text-slate-700 border-slate-200",
      model: "bg-blue-50 text-blue-700 border-blue-200",
      live: "bg-red-50 text-red-700 border-red-200",
    };
    return <Badge variant="outline" className={styles[category] || ""}>{CATEGORY_LABELS[category] || category}</Badge>;
  }
  return <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200 font-bold">Objective Exam</Badge>;
};

const StatusBadge = ({ status }: { status: string }) => {
  const styles: Record<string, string> = {
    live: "bg-emerald-50 text-emerald-700 border-emerald-200",
    published: "bg-emerald-50 text-emerald-700 border-emerald-200",
    draft: "bg-slate-100 text-slate-700 border-slate-200",
    archived: "bg-red-50 text-red-700 border-red-200",
    scheduled: "bg-blue-50 text-blue-700 border-blue-200",
    completed: "bg-amber-50 text-amber-700 border-amber-200"
  };
  const normalizedStatus = status.toLowerCase();
  const appliedStyle = styles[normalizedStatus] || "bg-slate-100 text-slate-700 border-slate-200";
  return <Badge variant="outline" className={`capitalize ${appliedStyle}`}>{status}</Badge>;
};

export default function ExamsOverviewPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [majorArea, setMajorArea] = useState<"all" | "topicwise" | "objective" | "subjective">("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [exams, setExams] = useState<Examination[]>([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<any>(null);
  
  // Pagination
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  useEffect(() => {
    fetchData();
  }, [page]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [overviewData, examsData] = await Promise.all([
        adminExamApi.getOverview(),
        adminExamApi.getExams({ page } as any) // Assuming pagination is supported, if not it will ignore
      ]);
      setStats(overviewData);
      
      if (examsData && Array.isArray(examsData.results)) {
        setExams(examsData.results);
        setTotalCount(examsData.count);
        setTotalPages(Math.ceil(examsData.count / 10)); // Assuming 10 per page
      } else {
        // Fallback if not paginated
        setExams(examsData as any);
        setTotalCount((examsData as any).length);
        setTotalPages(1);
      }
    } catch (error) {
      console.error("Failed to fetch exams data:", error);
      toast.error("Failed to load exams");
    } finally {
      setLoading(false);
    }
  };

  const filteredExams = exams
    .filter(e =>
      e.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (e.category_name || '').toLowerCase().includes(searchQuery.toLowerCase())
    )
    .filter(e => {
      // 1. Major area filtering
      if (majorArea === "topicwise") {
        if (e.exam_type !== "subject" && e.objective_category !== "topicwise") return false;
      } else if (majorArea === "objective") {
        if (e.exam_type === "subjective" || e.exam_type === "subject" || e.objective_category === "topicwise") return false;
      } else if (majorArea === "subjective") {
        if (e.exam_type !== "subjective") return false;
      }

      // 2. Sub-category filter
      if (categoryFilter !== "all") {
        if (categoryFilter === "subjective") {
          if (e.exam_type !== "subjective") return false;
        } else if (categoryFilter === "topicwise") {
          if (e.exam_type !== "subject" && e.objective_category !== "topicwise") return false;
        } else if (e.objective_category !== categoryFilter) {
          return false;
        }
      }
      return true;
    });

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      
      {/* Top Actions & Analytics Cards */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 mb-2">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 w-full md:w-3/4">
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <p className="text-sm font-semibold text-slate-500 mb-1">Total Exams</p>
            <h3 className="text-2xl font-bold text-[#0B2545]">{stats?.totalExams || 0}</h3>
          </div>
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <p className="text-sm font-semibold text-slate-500 mb-1">Active / Published</p>
            <h3 className="text-2xl font-bold text-emerald-600">{stats?.activeExams || 0}</h3>
          </div>
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <p className="text-sm font-semibold text-slate-500 mb-1">Total Attempts</p>
            <h3 className="text-2xl font-bold text-blue-600">{stats?.totalAttempts || 0}</h3>
          </div>
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <p className="text-sm font-semibold text-slate-500 mb-1">Drafts</p>
            <h3 className="text-2xl font-bold text-amber-600">{stats?.draftModelExams || 0}</h3>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 w-full md:w-auto">
          <Link href="/admin-dashboard/exams/submissions" className="w-full sm:w-auto">
            <Button variant="outline" className="w-full border-purple-200 text-purple-700 hover:bg-purple-50">
              <Award className="w-4 h-4 mr-2 text-purple-600" /> Submissions
            </Button>
          </Link>
          <Link href="/admin-dashboard/exams/requests" className="w-full sm:w-auto">
            <Button variant="outline" className="w-full">
              <Inbox className="w-4 h-4 mr-2" /> Requests
            </Button>
          </Link>
          <Link href="/admin-dashboard/exams/import" className="w-full sm:w-auto">
            <Button variant="outline" className="w-full">
              <DownloadCloud className="w-4 h-4 mr-2" /> Import Exam
            </Button>
          </Link>
          <Link href="/admin-dashboard/exams/new" className="w-full sm:w-auto">
            <Button className="w-full bg-[#0B2545] text-white hover:bg-[#163E6C]">
              <PlusCircle className="w-4 h-4 mr-2" /> Create Exam
            </Button>
          </Link>
        </div>
      </div>

      {/* ── 3 Major Exam Areas Navigation Tabs ────────────────────────── */}
      <div className="bg-slate-100 p-1.5 rounded-xl border border-slate-200 flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={() => { setMajorArea("all"); setCategoryFilter("all"); }}
          className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            majorArea === "all"
              ? "bg-white text-[#0B2545] shadow-sm ring-1 ring-slate-200"
              : "text-slate-600 hover:text-slate-900 hover:bg-white/50"
          }`}
        >
          All Exams ({exams.length})
        </button>

        <button
          type="button"
          onClick={() => { setMajorArea("topicwise"); setCategoryFilter("all"); }}
          className={`px-4 py-2 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
            majorArea === "topicwise"
              ? "bg-emerald-600 text-white shadow-sm"
              : "text-slate-600 hover:text-slate-900 hover:bg-white/50"
          }`}
        >
          <ClipboardList className="w-3.5 h-3.5" />
          1. Topicwise Test
        </button>

        <button
          type="button"
          onClick={() => { setMajorArea("objective"); setCategoryFilter("all"); }}
          className={`px-4 py-2 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
            majorArea === "objective"
              ? "bg-[#0B2545] text-white shadow-sm"
              : "text-slate-600 hover:text-slate-900 hover:bg-white/50"
          }`}
        >
          <FileText className="w-3.5 h-3.5" />
          2. Objective Exams
        </button>

        <button
          type="button"
          onClick={() => { setMajorArea("subjective"); setCategoryFilter("all"); }}
          className={`px-4 py-2 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
            majorArea === "subjective"
              ? "bg-purple-700 text-white shadow-sm"
              : "text-slate-600 hover:text-slate-900 hover:bg-white/50"
          }`}
        >
          <Award className="w-3.5 h-3.5" />
          3. Subjective Exams
        </button>
      </div>

      {/* Subjective Exams Submissions Banner */}
      {majorArea === "subjective" && (
        <div className="bg-gradient-to-r from-purple-900 via-indigo-900 to-slate-900 text-white rounded-xl p-5 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-purple-400/20 text-purple-200 border border-purple-400/30 uppercase tracking-wider mb-1.5">
              <Award className="w-3.5 h-3.5" /> Subjective Exams Workspace
            </div>
            <h3 className="text-lg font-bold text-white">Subjective Submissions &amp; Paper Evaluation</h3>
            <p className="text-xs text-purple-200 mt-1 max-w-xl">
              Inspect student handwritten PDF &amp; image answer sheets, run AI handwriting transcription, award per-question marks, and publish official results.
            </p>
          </div>
          <Link href="/admin-dashboard/exams/submissions">
            <Button className="bg-white text-indigo-950 hover:bg-purple-50 font-bold text-xs gap-1.5 shadow-md shrink-0">
              <Award className="w-4 h-4 text-purple-600" /> View Submissions &amp; Grading
            </Button>
          </Link>
        </div>
      )}

      {/* Filters & Search */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col lg:flex-row gap-4 items-end lg:items-center justify-between">
        <div className="relative w-full lg:w-80">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input 
            placeholder="Search exams, categories..." 
            className="pl-9 bg-slate-50"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        
        <div className="flex flex-wrap items-center gap-2 w-full lg:w-auto">
          {majorArea === "objective" && (
            <div className="relative">
              <Filter className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400 pointer-events-none" />
              <select
                value={categoryFilter}
                onChange={e => setCategoryFilter(e.target.value)}
                className="h-9 pl-8 pr-3 rounded-md border border-slate-200 bg-slate-50 text-sm text-slate-600 focus:outline-none"
              >
                <option value="all">Category: All Objective</option>
                <option value="past_year">Past Year Papers</option>
                <option value="model">Model Exams</option>
                <option value="live">Live Exams</option>
              </select>
            </div>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="text-blue-600 hover:text-blue-700 hover:bg-blue-50"
            onClick={() => { setSearchQuery(""); setCategoryFilter("all"); setMajorArea("all"); }}
          >
            Clear Filters
          </Button>
        </div>
      </div>

      {/* Data Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader className="bg-slate-50">
              <TableRow>
                <TableHead>Exam Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Category / Position</TableHead>
                <TableHead>Specs</TableHead>
                <TableHead>Performance</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                Array.from({ length: 4 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell><div className="h-10 bg-slate-100 rounded w-48 animate-pulse"></div></TableCell>
                    <TableCell><div className="h-5 bg-slate-100 rounded-full w-20 animate-pulse"></div></TableCell>
                    <TableCell><div className="h-8 bg-slate-100 rounded w-32 animate-pulse"></div></TableCell>
                    <TableCell><div className="h-8 bg-slate-100 rounded w-24 animate-pulse"></div></TableCell>
                    <TableCell><div className="h-8 bg-slate-100 rounded w-24 animate-pulse"></div></TableCell>
                    <TableCell><div className="h-5 bg-slate-100 rounded-full w-20 animate-pulse"></div></TableCell>
                    <TableCell className="text-right"><div className="h-8 w-8 bg-slate-100 rounded ml-auto animate-pulse"></div></TableCell>
                  </TableRow>
                ))
              ) : filteredExams.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="h-32 text-center text-slate-500">
                    No exams found. <button onClick={() => { setSearchQuery(""); setCategoryFilter("all"); }} className="text-blue-600 underline">Clear filters</button>
                  </TableCell>
                </TableRow>
              ) : (
                filteredExams.map((exam) => (
                  <TableRow key={exam.id} className="hover:bg-slate-50/50">
                    
                    <TableCell className="align-top">
                      <div className="flex flex-col">
                        <span className="text-sm font-bold text-[#0B2545] hover:text-blue-600 cursor-pointer">{exam.title}</span>
                        <div className="flex items-center gap-2 mt-1 text-xs">
                          {/* Assuming exams don't have premium/free yet, defaulting to logic or omitting */}
                          <span className="text-emerald-600 font-medium flex items-center gap-1"><Unlock className="w-3 h-3" /> Free</span>
                          <span className="text-slate-300">•</span>
                          <span className="text-slate-500 capitalize">{exam.exam_type}</span>
                        </div>
                      </div>
                    </TableCell>

                    <TableCell className="align-top">
                      <CategoryBadge category={exam.objective_category} examType={exam.exam_type} />
                    </TableCell>

                    <TableCell className="align-top">
                      <div className="flex flex-col max-w-[200px]">
                        <span className="text-sm font-semibold text-slate-800 truncate" title={exam.category_name || 'N/A'}>{exam.category_name || 'N/A'}</span>
                        <span className="text-xs text-slate-500 truncate mt-0.5" title={exam.exam_name || 'N/A'}>For: {exam.exam_name || 'N/A'}</span>
                      </div>
                    </TableCell>

                    <TableCell className="align-top">
                      <div className="flex flex-col gap-1 text-xs text-slate-600">
                        <div className="flex items-center gap-1"><HelpCircle className="w-3 h-3 text-slate-400" /> {exam.total_questions} Qs / {exam.total_marks} Marks</div>
                        <div className="flex items-center gap-1"><Clock className="w-3 h-3 text-slate-400" /> {exam.time_limit ? `${exam.time_limit} mins` : 'Unlimited'}</div>
                      </div>
                    </TableCell>

                    <TableCell className="align-top">
                      {exam.attempts_count > 0 ? (
                        <div className="flex flex-col gap-1 text-xs text-slate-600">
                          <div><span className="font-semibold text-slate-800">{exam.attempts_count.toLocaleString()}</span> Attempts</div>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400 italic">No attempts yet</span>
                      )}
                    </TableCell>

                    <TableCell className="align-top">
                      <StatusBadge status={exam.status} />
                      <div className="text-[10px] text-slate-400 mt-1.5 flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        {new Date(exam.updated_at).toLocaleDateString()}
                      </div>
                    </TableCell>

                    <TableCell className="align-top text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Link href={`/admin-dashboard/exams/${exam.id}`}>
                          <Button variant="ghost" size="sm" className="text-blue-600 hover:text-blue-700 hover:bg-blue-50 h-8">
                            View <ChevronRight className="w-4 h-4 ml-1" />
                          </Button>
                        </Link>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-slate-600">
                              <MoreHorizontal className="w-4 h-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem asChild>
                              <Link href={`/admin-dashboard/exams/${exam.id}`}>Overview</Link>
                            </DropdownMenuItem>
                            {exam.exam_type === "subjective" ? (
                              <DropdownMenuItem asChild>
                                <Link href={`/admin-dashboard/exams/${exam.id}/submissions`} className="font-semibold text-indigo-600">
                                  Submissions &amp; Grading
                                </Link>
                              </DropdownMenuItem>
                            ) : (
                              <DropdownMenuItem asChild>
                                <Link href={`/admin-dashboard/exams/${exam.id}/questions`}>Manage Questions</Link>
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuSeparator />
                            <DropdownMenuItem asChild>
                              <Link href={`/admin-dashboard/exams/new?draft=${exam.id}`} className="font-medium text-blue-600">
                                Edit Exam
                              </Link>
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem>Duplicate Exam</DropdownMenuItem>
                            <DropdownMenuSeparator />
                            {exam.status === "live" || (exam as any).status === "published" ? (
                              <DropdownMenuItem className="text-amber-600">Close Exam</DropdownMenuItem>
                            ) : (
                              <DropdownMenuItem className="text-emerald-600">Publish Exam</DropdownMenuItem>
                            )}
                            <DropdownMenuItem className="text-red-600">Archive</DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
        
        {/* Pagination */}
        <div className="border-t border-slate-200 p-4 flex items-center justify-between text-sm text-slate-500 bg-slate-50">
          <span>Showing {filteredExams.length} of {totalCount} exams</span>
          <div className="flex gap-1">
            <Button 
              variant="outline" 
              size="sm" 
              disabled={page === 1} 
              className="h-8"
              onClick={() => setPage(p => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <span className="px-3 py-1 text-sm font-medium">{page} / {totalPages}</span>
            <Button 
              variant="outline" 
              size="sm" 
              disabled={page >= totalPages} 
              className="h-8"
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            >
              Next
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
