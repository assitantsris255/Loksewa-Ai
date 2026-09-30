"use client";

import React, { useState, useEffect } from "react";
import {
  Calendar, Clock, Plus, Search, CheckCircle2, AlertCircle,
  ExternalLink, Edit, Trash2, Star, Globe, Eye, MoreVertical,
  Loader2, Filter, Sparkles
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle
} from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuTrigger, DropdownMenuSeparator
} from "@/components/ui/dropdown-menu";
import { schedulesApi, OfficialExamSchedule } from "@/lib/api/schedules";
import { apiClient } from "@/lib/api/client";
import toast from "react-hot-toast";

interface CategoryOption {
  id: number;
  name: string;
}

interface ExamOption {
  id: number;
  name: string;
  category: number;
}

export default function AdminExamSchedulesPage() {
  const [schedules, setSchedules] = useState<OfficialExamSchedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [examTypeFilter, setExamTypeFilter] = useState<string>("all");

  // Options for form
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [exams, setExams] = useState<ExamOption[]>([]);

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<OfficialExamSchedule | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Form fields
  const [formData, setFormData] = useState({
    title: "",
    exam_type: "all",
    exam_category: "",
    exam: "",
    description: "",
    exam_date: "",
    exam_time: "08:00:00",
    timezone: "Asia/Kathmandu",
    application_deadline: "",
    result_expected_date: "",
    official_notice_url: "",
    is_published: true,
    is_active: true,
  });

  const loadData = async () => {
    try {
      setLoading(true);
      const [schedulesRes, catsRes, examsRes] = await Promise.all([
        schedulesApi.getAdminSchedules({ exam_type: examTypeFilter }),
        apiClient<any>("/admin/syllabus/categories/?page_size=100").catch(() => []),
        apiClient<any>("/admin/syllabus/exams/?page_size=100").catch(() => []),
      ]);
      setSchedules(Array.isArray(schedulesRes) ? schedulesRes : (schedulesRes as any)?.results || []);
      setCategories(Array.isArray(catsRes) ? catsRes : catsRes?.results || []);
      setExams(Array.isArray(examsRes) ? examsRes : examsRes?.results || []);
    } catch (err) {
      console.error("Failed to load admin exam schedules", err);
      toast.error("Failed to load exam schedules");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [examTypeFilter]);

  const openCreateModal = () => {
    setEditingSchedule(null);
    setFormData({
      title: "",
      exam_type: examTypeFilter !== "all" ? examTypeFilter : "all",
      exam_category: "",
      exam: "",
      description: "",
      exam_date: "",
      exam_time: "08:00:00",
      timezone: "Asia/Kathmandu",
      application_deadline: "",
      result_expected_date: "",
      official_notice_url: "",
      is_published: true,
      is_active: schedules.length === 0, // Auto-active if first
    });
    setModalOpen(true);
  };

  const openEditModal = (schedule: OfficialExamSchedule) => {
    setEditingSchedule(schedule);
    setFormData({
      title: schedule.title,
      exam_type: schedule.exam_type || "all",
      exam_category: schedule.exam_category ? String(schedule.exam_category) : "",
      exam: schedule.exam ? String(schedule.exam) : "",
      description: schedule.description || "",
      exam_date: schedule.exam_date || "",
      exam_time: schedule.exam_time || "08:00:00",
      timezone: schedule.timezone || "Asia/Kathmandu",
      application_deadline: schedule.application_deadline || "",
      result_expected_date: schedule.result_expected_date || "",
      official_notice_url: schedule.official_notice_url || "",
      is_published: schedule.is_published ?? true,
      is_active: schedule.is_active ?? false,
    });
    setModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.title.trim()) {
      toast.error("Exam Title is required");
      return;
    }
    if (!formData.exam_date) {
      toast.error("Exam Date is required");
      return;
    }

    try {
      setSubmitting(true);
      const payload: Partial<OfficialExamSchedule> = {
        title: formData.title.trim(),
        exam_type: (formData.exam_type as any) || "all",
        exam_category: formData.exam_category ? Number(formData.exam_category) : null,
        exam: formData.exam ? Number(formData.exam) : null,
        description: formData.description.trim(),
        exam_date: formData.exam_date,
        exam_time: formData.exam_time || null,
        timezone: formData.timezone || "Asia/Kathmandu",
        application_deadline: formData.application_deadline || null,
        result_expected_date: formData.result_expected_date || null,
        official_notice_url: formData.official_notice_url.trim(),
        is_published: formData.is_published,
        is_active: formData.is_active,
      };

      if (editingSchedule) {
        await schedulesApi.updateSchedule(editingSchedule.id, payload);
        toast.success("Exam schedule updated successfully!");
      } else {
        await schedulesApi.createSchedule(payload);
        toast.success("Official exam schedule created successfully!");
      }

      setModalOpen(false);
      loadData();
    } catch (err: any) {
      console.error("Save schedule error", err);
      const msg = err.response?.data?.detail || err.response?.data?.exam_date || "Failed to save schedule";
      toast.error(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setSubmitting(false);
    }
  };

  const handleSetActive = async (schedule: OfficialExamSchedule) => {
    try {
      await schedulesApi.setActiveSchedule(schedule.id);
      toast.success(`Set '${schedule.title}' as the Active Next Exam!`);
      loadData();
    } catch (err: any) {
      console.error(err);
      toast.error(err.response?.data?.detail || "Failed to activate schedule");
    }
  };

  const handleTogglePublish = async (schedule: OfficialExamSchedule) => {
    try {
      const updated = await schedulesApi.togglePublishSchedule(schedule.id);
      toast.success(updated.is_published ? "Schedule Published!" : "Schedule Unpublished!");
      loadData();
    } catch (err) {
      console.error(err);
      toast.error("Failed to toggle publish status");
    }
  };

  const handleDelete = async (schedule: OfficialExamSchedule) => {
    if (!confirm(`Are you sure you want to delete '${schedule.title}'?`)) return;
    try {
      await schedulesApi.deleteSchedule(schedule.id);
      toast.success("Schedule deleted successfully");
      loadData();
    } catch (err) {
      console.error(err);
      toast.error("Failed to delete schedule");
    }
  };

  const activeSchedule = schedules.find((s) => s.is_active);

  const filteredSchedules = schedules.filter((s) => {
    const matchSearch =
      s.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (s.category_name && s.category_name.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (s.exam_name && s.exam_name.toLowerCase().includes(searchTerm.toLowerCase()));

    if (!matchSearch) return false;

    if (examTypeFilter !== "all") {
      if (s.exam_type && s.exam_type !== "all" && s.exam_type !== examTypeFilter) return false;
    }

    if (statusFilter === "active") return s.is_active;
    if (statusFilter === "published") return s.is_published;
    if (statusFilter === "draft") return !s.is_published;
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black text-[#0B2545] tracking-tight">
            Official Exam Schedules
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Manage real database-backed Loksewa examination dates and public countdown targets.
          </p>
        </div>
        <Button
          onClick={openCreateModal}
          className="bg-[#0B2545] hover:bg-[#133E6D] text-white font-bold gap-2 self-start sm:self-auto"
        >
          <Plus className="w-4 h-4" /> Add Exam Schedule
        </Button>
      </div>

      {/* Active Next Loksewa Exam Hero Banner */}
      {activeSchedule && (
        <Card className="bg-gradient-to-r from-[#0B2545] to-[#163E6B] text-white border-none shadow-md overflow-hidden relative">
          <div className="absolute right-0 top-0 w-64 h-64 bg-[#D4A72C]/10 rounded-full blur-2xl pointer-events-none" />
          <CardContent className="p-6 relative z-10">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
              <div className="space-y-2">
                <div className="inline-flex items-center gap-1.5 px-3 py-1 bg-[#D4A72C] text-[#0B2545] rounded-full text-xs font-black tracking-wider uppercase">
                  <Star className="w-3.5 h-3.5 fill-current" /> Active "Next Loksewa Exam"
                </div>
                <h2 className="text-xl md:text-2xl font-black text-white">{activeSchedule.title}</h2>
                <div className="flex flex-wrap items-center gap-3 text-xs text-slate-300">
                  <span className="flex items-center gap-1">
                    <Calendar className="w-3.5 h-3.5 text-[#D4A72C]" />
                    {new Date(activeSchedule.exam_date).toLocaleDateString("en-US", {
                      weekday: "short",
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                    })}
                  </span>
                  {activeSchedule.exam_time && (
                    <span className="flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5 text-blue-300" />
                      {activeSchedule.exam_time.slice(0, 5)} (NPT)
                    </span>
                  )}
                  {activeSchedule.category_name && (
                    <Badge variant="secondary" className="bg-white/10 text-white text-[11px]">
                      {activeSchedule.category_name}
                    </Badge>
                  )}
                  {activeSchedule.exam_type && activeSchedule.exam_type !== "all" && (
                    <Badge variant="secondary" className="bg-[#D4A72C]/20 text-[#D4A72C] text-[11px] font-bold border-none uppercase tracking-wider">
                      {activeSchedule.exam_type === "topicwise" ? "Topicwise Test" : activeSchedule.exam_type === "subjective" ? "Subjective Exam" : "Objective Exam"}
                    </Badge>
                  )}
                </div>
                {activeSchedule.description && (
                  <p className="text-xs text-slate-300 max-w-2xl">{activeSchedule.description}</p>
                )}
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => openEditModal(activeSchedule)}
                  className="border-white/20 text-white hover:bg-white/10 hover:text-white font-bold bg-transparent text-xs"
                >
                  <Edit className="w-3.5 h-3.5 mr-1" /> Edit Schedule
                </Button>
                {activeSchedule.official_notice_url && (
                  <Button asChild size="sm" className="bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0B2545] font-black text-xs">
                    <a href={activeSchedule.official_notice_url} target="_blank" rel="noopener noreferrer">
                      View Notice <ExternalLink className="w-3.5 h-3.5 ml-1" />
                    </a>
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="relative w-full sm:w-80">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input
            placeholder="Search schedules or categories..."
            className="pl-9 bg-slate-50 border-slate-200 text-slate-900"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Type:</span>
            <select
              value={examTypeFilter}
              onChange={(e) => setExamTypeFilter(e.target.value)}
              className="px-3 py-2 bg-white border border-slate-200 text-slate-700 text-xs font-semibold rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4A72C]"
            >
              <option value="all">All Exam Types</option>
              <option value="topicwise">Topicwise Test</option>
              <option value="objective">Objective Exam</option>
              <option value="subjective">Subjective Exam</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5">
            <Filter className="w-4 h-4 text-slate-400" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-2 bg-white border border-slate-200 text-slate-700 text-xs font-semibold rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4A72C]"
            >
              <option value="all">All Statuses</option>
              <option value="active">Active Next Exam</option>
              <option value="published">Published</option>
              <option value="draft">Drafts</option>
            </select>
          </div>
        </div>
      </div>

      {/* Schedules Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-slate-50 hover:bg-slate-50">
                <TableHead className="text-slate-700">Exam Title & Details</TableHead>
                <TableHead className="text-slate-700">Exam Type</TableHead>
                <TableHead className="text-slate-700">Category & Level</TableHead>
                <TableHead className="text-slate-700">Exam Date & Time</TableHead>
                <TableHead className="text-slate-700">Application Deadline</TableHead>
                <TableHead className="text-slate-700">Status</TableHead>
                <TableHead className="text-right text-slate-700">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={7} className="h-32 text-center bg-white">
                    <Loader2 className="h-6 w-6 animate-spin mx-auto text-slate-400" />
                  </TableCell>
                </TableRow>
              ) : filteredSchedules.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="h-32 text-center text-slate-500 bg-white">
                    No exam schedules found. Click "Add Exam Schedule" to create one.
                  </TableCell>
                </TableRow>
              ) : (
                filteredSchedules.map((item) => (
                  <TableRow key={item.id} className="hover:bg-slate-50/50 border-b border-slate-200">
                    {/* Title */}
                    <TableCell>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-bold text-[#0B2545]">{item.title}</p>
                          {item.is_active && (
                            <Badge className="bg-[#D4A72C] hover:bg-[#D4A72C] text-[#0B2545] font-bold text-[10px] uppercase">
                              Active Next
                            </Badge>
                          )}
                        </div>
                        {item.description && (
                          <p className="text-xs text-slate-500 line-clamp-1 mt-0.5">{item.description}</p>
                        )}
                      </div>
                    </TableCell>

                    {/* Exam Type */}
                    <TableCell>
                      {item.exam_type === "topicwise" ? (
                        <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px] font-bold">
                          Topicwise Test
                        </Badge>
                      ) : item.exam_type === "objective" ? (
                        <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200 text-[10px] font-bold">
                          Objective Exam
                        </Badge>
                      ) : item.exam_type === "subjective" ? (
                        <Badge variant="outline" className="bg-purple-50 text-purple-700 border-purple-200 text-[10px] font-bold">
                          Subjective Exam
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="bg-slate-100 text-slate-700 border-slate-200 text-[10px] font-semibold">
                          All Types
                        </Badge>
                      )}
                    </TableCell>

                    {/* Category */}
                    <TableCell>
                      <div className="text-xs">
                        <p className="font-semibold text-slate-700">{item.category_name || "General"}</p>
                        {item.exam_name && <p className="text-slate-500">{item.exam_name}</p>}
                      </div>
                    </TableCell>

                    {/* Date & Time */}
                    <TableCell>
                      <div className="text-xs">
                        <p className="font-semibold text-[#0B2545]">
                          {new Date(item.exam_date).toLocaleDateString("en-US", {
                            year: "numeric",
                            month: "short",
                            day: "numeric",
                          })}
                        </p>
                        {item.exam_time && <p className="text-slate-500">{item.exam_time.slice(0, 5)} (NPT)</p>}
                      </div>
                    </TableCell>

                    {/* Deadline */}
                    <TableCell>
                      <span className="text-xs text-slate-600">
                        {item.application_deadline
                          ? new Date(item.application_deadline).toLocaleDateString("en-US", {
                              year: "numeric",
                              month: "short",
                              day: "numeric",
                            })
                          : "—"}
                      </span>
                    </TableCell>

                    {/* Status */}
                    <TableCell>
                      <div className="flex flex-col gap-1 items-start">
                        {item.is_published ? (
                          <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px] font-bold">
                            Published
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="bg-slate-100 text-slate-600 border-slate-200 text-[10px] font-bold">
                            Draft
                          </Badge>
                        )}
                      </div>
                    </TableCell>

                    {/* Actions */}
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {!item.is_active && (
                            <DropdownMenuItem onClick={() => handleSetActive(item)} className="font-medium">
                              <Star className="h-4 w-4 mr-2 text-[#D4A72C]" /> Set as Active Next Exam
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuItem onClick={() => handleTogglePublish(item)}>
                            <Globe className="h-4 w-4 mr-2" />
                            {item.is_published ? "Unpublish Schedule" : "Publish Schedule"}
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => openEditModal(item)}>
                            <Edit className="h-4 w-4 mr-2" /> Edit Details
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => handleDelete(item)} className="text-red-600">
                            <Trash2 className="h-4 w-4 mr-2" /> Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Create / Edit Schedule Dialog */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold text-[#0B2545]">
              {editingSchedule ? "Edit Exam Schedule" : "Create Official Exam Schedule"}
            </DialogTitle>
            <DialogDescription>
              Set the authoritative date, time, and details for official Loksewa examinations.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4 pt-2">
            {/* Title & Exam Type */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="sm:col-span-2">
                <label className="block text-xs font-bold text-slate-700 uppercase mb-1">
                  Exam Title <span className="text-red-500">*</span>
                </label>
                <Input
                  placeholder="e.g. Loksewa Section Officer 2083 First Paper"
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-1">
                  Exam Type <span className="text-red-500">*</span>
                </label>
                <select
                  value={formData.exam_type}
                  onChange={(e) => setFormData({ ...formData, exam_type: e.target.value })}
                  className="w-full px-3 py-2 bg-white border border-slate-200 rounded-md text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-[#D4A72C]"
                >
                  <option value="all">All Exam Types</option>
                  <option value="topicwise">Topicwise Test</option>
                  <option value="objective">Objective Exam</option>
                  <option value="subjective">Subjective Exam</option>
                </select>
              </div>
            </div>

            {/* Category and Position */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-1">
                  Exam Category
                </label>
                <select
                  value={formData.exam_category}
                  onChange={(e) => setFormData({ ...formData, exam_category: e.target.value })}
                  className="w-full px-3 py-2 bg-white border border-slate-200 rounded-md text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-[#D4A72C]"
                >
                  <option value="">-- Select Category --</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-1">
                  Position / Level
                </label>
                <select
                  value={formData.exam}
                  onChange={(e) => setFormData({ ...formData, exam: e.target.value })}
                  className="w-full px-3 py-2 bg-white border border-slate-200 rounded-md text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-[#D4A72C]"
                >
                  <option value="">-- Select Position --</option>
                  {exams
                    .filter((ex) => !formData.exam_category || ex.category === Number(formData.exam_category))
                    .map((ex) => (
                      <option key={ex.id} value={ex.id}>
                        {ex.name}
                      </option>
                    ))}
                </select>
              </div>
            </div>

            {/* Date and Time */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-1">
                  Exam Date (YYYY-MM-DD) <span className="text-red-500">*</span>
                </label>
                <Input
                  type="date"
                  value={formData.exam_date}
                  onChange={(e) => setFormData({ ...formData, exam_date: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-1">
                  Exam Start Time (NPT)
                </label>
                <Input
                  type="time"
                  step="1"
                  value={formData.exam_time}
                  onChange={(e) => setFormData({ ...formData, exam_time: e.target.value })}
                />
              </div>
            </div>

            {/* Application Deadline & Result Date */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-1">
                  Application Deadline (Optional)
                </label>
                <Input
                  type="date"
                  value={formData.application_deadline}
                  onChange={(e) => setFormData({ ...formData, application_deadline: e.target.value })}
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-1">
                  Result Expected Date (Optional)
                </label>
                <Input
                  type="date"
                  value={formData.result_expected_date}
                  onChange={(e) => setFormData({ ...formData, result_expected_date: e.target.value })}
                />
              </div>
            </div>

            {/* Notice URL */}
            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase mb-1">
                Official Notice URL (Optional)
              </label>
              <Input
                type="url"
                placeholder="https://psc.gov.np/notice/..."
                value={formData.official_notice_url}
                onChange={(e) => setFormData({ ...formData, official_notice_url: e.target.value })}
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase mb-1">
                Description / Instructions
              </label>
              <textarea
                rows={3}
                className="w-full px-3 py-2 bg-white border border-slate-200 rounded-md text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-[#D4A72C]"
                placeholder="Important examination instructions, center details, or remarks..."
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              />
            </div>

            {/* Toggles */}
            <div className="flex flex-col sm:flex-row gap-4 pt-2 border-t border-slate-100">
              <label className="flex items-center gap-2 cursor-pointer text-sm font-semibold text-slate-700">
                <input
                  type="checkbox"
                  checked={formData.is_published}
                  onChange={(e) => setFormData({ ...formData, is_published: e.target.checked })}
                  className="rounded border-slate-300 text-[#0B2545] focus:ring-[#D4A72C] h-4 w-4"
                />
                Published (Visible in Student Portal)
              </label>

              <label className="flex items-center gap-2 cursor-pointer text-sm font-semibold text-slate-700">
                <input
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  className="rounded border-slate-300 text-[#0B2545] focus:ring-[#D4A72C] h-4 w-4"
                />
                Set as Active "Next Loksewa Exam"
              </label>
            </div>

            <DialogFooter className="pt-4 border-t border-slate-100">
              <Button
                type="button"
                variant="outline"
                onClick={() => setModalOpen(false)}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={submitting}
                className="bg-[#0B2545] hover:bg-[#133E6D] text-white font-bold"
              >
                {submitting ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                {editingSchedule ? "Save Changes" : "Create Schedule"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
