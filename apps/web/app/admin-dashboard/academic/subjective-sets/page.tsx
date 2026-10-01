'use client';

import { useState, useEffect } from 'react';
import { adminSubjectiveSetsApi, SubjectiveQuestionSet, SubjectiveSetFilterParams } from '@/lib/api/admin-subjective-sets';
import { adminSyllabusApi, AdminExamCategory } from '@/lib/api/admin-syllabus';
import { AcademicDependentSelect } from '@/components/admin/syllabus/AcademicDependentSelect';
import Link from 'next/link';
import { 
  Plus, Search, RefreshCw, FileText, Download, Eye, Edit2, 
  Archive, CheckCircle2, XCircle, Trash2, ExternalLink, PlusCircle
} from 'lucide-react';
import { toast } from 'react-hot-toast';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { ButtonSpinner, InlineLoader } from '@/components/ui/loading-states';

function formatBytes(bytes?: number): string {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export default function SubjectiveQuestionBankPage() {
  const [sets, setSets] = useState<SubjectiveQuestionSet[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalCount, setTotalCount] = useState(0);
  const [categories, setCategories] = useState<AdminExamCategory[]>([]);

  // Filters
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [page, setPage] = useState(1);

  // Modals
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [activeSet, setActiveSet] = useState<SubjectiveQuestionSet | null>(null);

  // Form State for Upload / Edit
  const [formTitle, setFormTitle] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formCategory, setFormCategory] = useState<number | undefined>();
  const [formPosition, setFormPosition] = useState<number | undefined>();
  const [formSubject, setFormSubject] = useState<number | undefined>();
  const [formDuration, setFormDuration] = useState<number>(180);
  const [formMarks, setFormMarks] = useState<number>(100);
  const [formQuestionCount, setFormQuestionCount] = useState<number>(10);
  const [formStatus, setFormStatus] = useState<'active' | 'inactive'>('active');
  const [formPdfFile, setFormPdfFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Debounce search
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedSearch(search), 350);
    return () => clearTimeout(handler);
  }, [search]);

  // Load categories for filter
  useEffect(() => {
    adminSyllabusApi.getCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  // Fetch sets when filters change
  useEffect(() => {
    fetchSets();
  }, [debouncedSearch, selectedCategory, selectedStatus, page]);

  const fetchSets = async () => {
    setLoading(true);
    try {
      const params: SubjectiveSetFilterParams = {
        page,
        ordering: '-created_at',
      };
      if (debouncedSearch.trim()) params.search = debouncedSearch.trim();
      if (selectedCategory) params.exam_category = selectedCategory;
      if (selectedStatus) params.status = selectedStatus;

      const res = await adminSubjectiveSetsApi.getSets(params);
      const items: SubjectiveQuestionSet[] = Array.isArray(res) ? res : (res?.results || []);
      const count = Array.isArray(res) ? res.length : (res?.count ?? items.length);
      setSets(items);
      setTotalCount(count);
    } catch (error: any) {
      toast.error(error.message || 'Failed to load subjective question sets');
    } finally {
      setLoading(false);
    }
  };

  const handleAcademicChange = (field: string, value: any) => {
    if (field === 'category') {
      setFormCategory(value);
      setFormPosition(undefined);
      setFormSubject(undefined);
    } else if (field === 'position' || field === 'exam') {
      setFormPosition(value);
      setFormSubject(undefined);
    } else if (field === 'subject') {
      setFormSubject(value);
    }
  };

  const resetForm = () => {
    setFormTitle('');
    setFormDescription('');
    setFormCategory(undefined);
    setFormPosition(undefined);
    setFormSubject(undefined);
    setFormDuration(180);
    setFormMarks(100);
    setFormQuestionCount(10);
    setFormStatus('active');
    setFormPdfFile(null);
    setActiveSet(null);
  };

  const openUploadModal = () => {
    resetForm();
    setIsUploadOpen(true);
  };

  const openEditModal = (set: SubjectiveQuestionSet) => {
    setActiveSet(set);
    setFormTitle(set.title);
    setFormDescription(set.description || '');
    setFormCategory(set.category_id || set.exam_category);
    setFormPosition(set.level_id || set.level);
    setFormSubject(set.subject || undefined);
    setFormDuration(set.duration_minutes || 180);
    setFormMarks(set.total_marks || 100);
    setFormQuestionCount(set.question_count || 10);
    setFormStatus(set.status === 'archived' ? 'inactive' : set.status);
    setFormPdfFile(null);
    setIsEditOpen(true);
  };

  const openPreviewModal = (set: SubjectiveQuestionSet) => {
    setActiveSet(set);
    setIsPreviewOpen(true);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
      toast.error('Only PDF documents (.pdf) are allowed.');
      e.target.value = '';
      return;
    }

    if (file.size > 20 * 1024 * 1024) {
      toast.error('PDF file size must not exceed 20MB.');
      e.target.value = '';
      return;
    }

    setFormPdfFile(file);
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formTitle.trim()) {
      toast.error('Please enter a Question Paper title.');
      return;
    }
    if (!formCategory || !formPosition) {
      toast.error('Category and Position / Level are required.');
      return;
    }
    if (!formPdfFile) {
      toast.error('Please select a PDF Question Paper file.');
      return;
    }

    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append('title', formTitle.trim());
      formData.append('exam_category', String(formCategory));
      formData.append('level', String(formPosition));
      if (formSubject) formData.append('subject', String(formSubject));
      if (formDescription.trim()) formData.append('description', formDescription.trim());
      formData.append('duration_minutes', String(formDuration));
      formData.append('total_marks', String(formMarks));
      formData.append('question_count', String(formQuestionCount));
      formData.append('status', formStatus);
      formData.append('pdf_file', formPdfFile);

      await adminSubjectiveSetsApi.createSet(formData);
      toast.success('Subjective Question Paper uploaded successfully!');
      setIsUploadOpen(false);
      resetForm();
      fetchSets();
    } catch (error: any) {
      toast.error(error?.data?.error || error.message || 'Failed to upload question paper');
    } finally {
      setSubmitting(false);
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeSet) return;
    if (!formTitle.trim()) {
      toast.error('Please enter a Question Paper title.');
      return;
    }
    if (!formCategory || !formPosition) {
      toast.error('Category and Position / Level are required.');
      return;
    }

    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append('title', formTitle.trim());
      formData.append('exam_category', String(formCategory));
      formData.append('level', String(formPosition));
      if (formSubject) {
        formData.append('subject', String(formSubject));
      } else {
        formData.append('subject', '');
      }
      formData.append('description', formDescription.trim());
      formData.append('duration_minutes', String(formDuration));
      formData.append('total_marks', String(formMarks));
      formData.append('question_count', String(formQuestionCount));
      formData.append('status', formStatus);
      if (formPdfFile) {
        formData.append('pdf_file', formPdfFile);
      }

      await adminSubjectiveSetsApi.updateSet(activeSet.id, formData);
      toast.success('Subjective Question Paper updated successfully!');
      setIsEditOpen(false);
      resetForm();
      fetchSets();
    } catch (error: any) {
      toast.error(error?.data?.error || error.message || 'Failed to update question paper');
    } finally {
      setSubmitting(false);
    }
  };

  const handleArchive = async (set: SubjectiveQuestionSet) => {
    try {
      await adminSubjectiveSetsApi.archiveSet(set.id);
      toast.success(`Question set "${set.title}" has been archived.`);
      fetchSets();
    } catch (error: any) {
      toast.error(error.message || 'Failed to archive question set');
    }
  };

  const handleActivate = async (set: SubjectiveQuestionSet) => {
    try {
      await adminSubjectiveSetsApi.activateSet(set.id);
      toast.success(`Question set "${set.title}" is now active.`);
      fetchSets();
    } catch (error: any) {
      toast.error(error.message || 'Failed to activate question set');
    }
  };

  const handleDelete = async (set: SubjectiveQuestionSet) => {
    if (!confirm(`Are you sure you want to delete "${set.title}"?`)) return;
    try {
      await adminSubjectiveSetsApi.deleteSet(set.id);
      toast.success('Question set deleted.');
      fetchSets();
    } catch (error: any) {
      toast.error(error.message || 'Failed to delete question set');
    }
  };

  const statsActive = sets.filter(s => s.status === 'active').length;
  const statsArchived = sets.filter(s => s.status === 'archived').length;
  const statsInactive = sets.filter(s => s.status === 'inactive').length;

  return (
    <div className="p-5 md:p-6 space-y-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-start gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Subjective Question Bank</h1>
          <p className="text-gray-500 mt-1">
            Manage complete subjective question paper sets stored as PDF documents.
          </p>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <Button
            onClick={openUploadModal}
            className="bg-[#0B2545] hover:bg-[#163E6C] text-white flex items-center gap-2 shadow-sm font-medium"
          >
            <Plus className="w-4 h-4" />
            Upload Question Paper
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-500">Total Paper Sets</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{totalCount}</p>
          </div>
          <div className="p-3 bg-blue-50 rounded-lg text-blue-600">
            <FileText className="w-6 h-6" />
          </div>
        </div>
        <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-500">Active Papers</p>
            <p className="text-2xl font-bold text-green-700 mt-1">{statsActive}</p>
          </div>
          <div className="p-3 bg-green-50 rounded-lg text-green-600">
            <CheckCircle2 className="w-6 h-6" />
          </div>
        </div>
        <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-500">Inactive Papers</p>
            <p className="text-2xl font-bold text-gray-700 mt-1">{statsInactive}</p>
          </div>
          <div className="p-3 bg-gray-50 rounded-lg text-gray-500">
            <XCircle className="w-6 h-6" />
          </div>
        </div>
        <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-500">Archived Papers</p>
            <p className="text-2xl font-bold text-amber-700 mt-1">{statsArchived}</p>
          </div>
          <div className="p-3 bg-amber-50 rounded-lg text-amber-600">
            <Archive className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Toolbar / Filters */}
      <div className="bg-white p-4 rounded-xl border border-gray-100 shadow-sm flex flex-col md:flex-row gap-4 justify-between items-center">
        <div className="flex items-center gap-3 w-full md:w-96">
          <div className="relative w-full">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search paper by name, level, subject..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-[#0B2545]"
            />
          </div>
        </div>

        <div className="flex gap-2 w-full md:w-auto items-center flex-wrap">
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#0B2545]"
          >
            <option value="">All Categories</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>

          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#0B2545]"
          >
            <option value="">All Statuses</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="archived">Archived</option>
          </select>

          <Button
            variant="outline"
            size="sm"
            onClick={fetchSets}
            className="border-gray-200 text-gray-600 hover:text-gray-900"
          >
            <RefreshCw className="w-4 h-4 mr-1" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Sets Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200 text-gray-600 font-semibold">
              <tr>
                <th className="px-4 py-3.5 text-left">Paper Name</th>
                <th className="px-4 py-3.5 text-left">Category</th>
                <th className="px-4 py-3.5 text-left">Level / Position</th>
                <th className="px-4 py-3.5 text-left">Subject</th>
                <th className="px-4 py-3.5 text-left">Document File</th>
                <th className="px-4 py-3.5 text-left">Details</th>
                <th className="px-4 py-3.5 text-left">Status</th>
                <th className="px-4 py-3.5 text-left">Created At</th>
                <th className="px-4 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr>
                  <td colSpan={9} className="text-center py-12">
                    <InlineLoader text="Loading subjective sets..." />
                  </td>
                </tr>
              ) : sets.length === 0 ? (
                <tr>
                  <td colSpan={9} className="text-center py-12">
                    <div className="flex flex-col items-center justify-center text-gray-400">
                      <FileText className="w-12 h-12 stroke-[1.5] mb-2" />
                      <p className="text-base font-medium text-gray-700">No Subjective Question Papers found</p>
                      <p className="text-sm text-gray-400 mt-1">Upload a complete PDF question paper set to get started.</p>
                      <Button onClick={openUploadModal} className="mt-4 bg-[#0B2545] text-white">
                        <Plus className="w-4 h-4 mr-2" /> Upload Question Paper
                      </Button>
                    </div>
                  </td>
                </tr>
              ) : (
                sets.map((set) => (
                  <tr key={set.id} className="hover:bg-gray-50/80 transition-colors">
                    <td className="px-4 py-3 font-medium text-gray-900">
                      <div>
                        <span>{set.title}</span>
                        {set.description && (
                          <p className="text-xs text-gray-400 mt-0.5 line-clamp-1 max-w-[280px]">
                            {set.description}
                          </p>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {set.category_name || `Category #${set.exam_category}`}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {set.level_name || `Level #${set.level}`}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {set.subject_name || (
                        <span className="text-xs text-gray-400 italic">All / Multi-subject</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      <div className="flex items-center gap-2">
                        <span className="p-1.5 bg-red-50 text-red-600 rounded">
                          <FileText className="w-4 h-4" />
                        </span>
                        <div>
                          <p className="text-xs font-medium text-gray-800 truncate max-w-[160px]" title={set.file_name || 'Question Paper.pdf'}>
                            {set.file_name || 'Question Paper.pdf'}
                          </p>
                          <p className="text-[11px] text-gray-400">{formatBytes(set.file_size)}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">
                      <div>{set.duration_minutes} mins</div>
                      <div className="text-gray-400">{set.total_marks} marks • {set.question_count} Qs</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium capitalize ${
                        set.status === 'active'
                          ? 'bg-green-100 text-green-800'
                          : set.status === 'archived'
                          ? 'bg-amber-100 text-amber-800'
                          : 'bg-gray-100 text-gray-700'
                      }`}>
                        {set.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">
                      {new Date(set.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => openPreviewModal(set)}
                          title="Preview PDF"
                          className="p-1.5 hover:bg-gray-100 text-blue-600 rounded transition-colors"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <a
                          href={set.pdf_file}
                          target="_blank"
                          rel="noreferrer"
                          download
                          title="Download PDF"
                          className="p-1.5 hover:bg-gray-100 text-gray-600 rounded transition-colors"
                        >
                          <Download className="w-4 h-4" />
                        </a>
                        {set.status === 'active' && (
                          <Link
                            href={`/admin-dashboard/exams/new?type=subjective&subjectiveSet=${set.id}&category=${set.exam_category}&position=${set.level}${set.subject ? `&subject=${set.subject}` : ''}`}
                            title="Create Exam with this Paper"
                            className="p-1.5 hover:bg-indigo-50 text-indigo-600 rounded transition-colors"
                          >
                            <PlusCircle className="w-4 h-4" />
                          </Link>
                        )}
                        <button
                          onClick={() => openEditModal(set)}
                          title="Edit Set"
                          className="p-1.5 hover:bg-gray-100 text-gray-600 rounded transition-colors"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        {set.status === 'active' ? (
                          <button
                            onClick={() => handleArchive(set)}
                            title="Archive"
                            className="p-1.5 hover:bg-amber-50 text-amber-600 rounded transition-colors"
                          >
                            <Archive className="w-4 h-4" />
                          </button>
                        ) : (
                          <button
                            onClick={() => handleActivate(set)}
                            title="Activate"
                            className="p-1.5 hover:bg-green-50 text-green-600 rounded transition-colors"
                          >
                            <CheckCircle2 className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(set)}
                          title="Delete"
                          className="p-1.5 hover:bg-red-50 text-red-600 rounded transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {totalCount > 20 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 bg-gray-50/50">
            <span className="text-xs text-gray-500">
              Showing page {page} of {Math.ceil(totalCount / 20)} ({totalCount} total)
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="text-xs"
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= Math.ceil(totalCount / 20)}
                onClick={() => setPage((p) => p + 1)}
                className="text-xs"
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Upload Question Paper Modal */}
      <Dialog open={isUploadOpen} onOpenChange={setIsUploadOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold">Upload Subjective Question Paper</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleUploadSubmit} className="space-y-4 pt-2">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Question Paper Name *
              </label>
              <input
                type="text"
                value={formTitle}
                onChange={(e) => setFormTitle(e.target.value)}
                placeholder="e.g. Civil Engineering Model Set 01"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#0B2545]"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Academic Hierarchy
              </label>
              <p className="text-xs text-gray-500 mb-3">
                Category and Position/Level are required. Subject is optional if the paper covers multiple subjects.
              </p>
              <AcademicDependentSelect
                category={formCategory}
                position={formPosition}
                subject={formSubject}
                onChange={handleAcademicChange}
                requiredLevels={['category', 'position']}
                maxLevel="subject"
                layout="grid"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Duration (Minutes)</label>
                <input
                  type="number"
                  value={formDuration}
                  onChange={(e) => setFormDuration(Number(e.target.value))}
                  min={1}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#0B2545]"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Total Marks</label>
                <input
                  type="number"
                  value={formMarks}
                  onChange={(e) => setFormMarks(Number(e.target.value))}
                  min={1}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#0B2545]"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Question Count</label>
                <input
                  type="number"
                  value={formQuestionCount}
                  onChange={(e) => setFormQuestionCount(Number(e.target.value))}
                  min={1}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#0B2545]"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Description (Optional)</label>
              <textarea
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                placeholder="Brief notes about this question paper set..."
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm min-h-[70px] focus:outline-none focus:border-[#0B2545]"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                PDF Question Paper *
              </label>
              <div className="border-2 border-dashed border-gray-300 rounded-xl p-6 text-center hover:bg-gray-50 transition-colors">
                <input
                  type="file"
                  accept=".pdf,application/pdf"
                  onChange={handleFileChange}
                  className="hidden"
                  id="pdf-upload-input"
                  required
                />
                <label htmlFor="pdf-upload-input" className="cursor-pointer block">
                  <div className="w-12 h-12 bg-red-50 text-red-600 rounded-full flex items-center justify-center mx-auto mb-2">
                    <FileText className="w-6 h-6" />
                  </div>
                  {formPdfFile ? (
                    <div>
                      <p className="font-semibold text-gray-900 text-sm">{formPdfFile.name}</p>
                      <p className="text-xs text-gray-500 mt-1">{formatBytes(formPdfFile.size)} • Click to replace</p>
                    </div>
                  ) : (
                    <div>
                      <p className="font-medium text-gray-700 text-sm">Choose PDF Question Paper</p>
                      <p className="text-xs text-gray-400 mt-1">Accepts PDF documents up to 20MB</p>
                    </div>
                  )}
                </label>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
              <select
                value={formStatus}
                onChange={(e) => setFormStatus(e.target.value as any)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#0B2545]"
              >
                <option value="active">Active (Eligible for student exam assignment)</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>

            <DialogFooter className="pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => setIsUploadOpen(false)}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={submitting}
                className="bg-[#0B2545] hover:bg-[#163E6C] text-white"
              >
                {submitting ? <ButtonSpinner text="Uploading PDF..." /> : 'Upload Question Paper'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Modal */}
      <Dialog open={isEditOpen} onOpenChange={setIsEditOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold">Edit Subjective Question Paper</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleEditSubmit} className="space-y-4 pt-2">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Question Paper Name *
              </label>
              <input
                type="text"
                value={formTitle}
                onChange={(e) => setFormTitle(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#0B2545]"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Academic Hierarchy
              </label>
              <AcademicDependentSelect
                category={formCategory}
                position={formPosition}
                subject={formSubject}
                onChange={handleAcademicChange}
                requiredLevels={['category', 'position']}
                maxLevel="subject"
                layout="grid"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Duration (Minutes)</label>
                <input
                  type="number"
                  value={formDuration}
                  onChange={(e) => setFormDuration(Number(e.target.value))}
                  min={1}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#0B2545]"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Total Marks</label>
                <input
                  type="number"
                  value={formMarks}
                  onChange={(e) => setFormMarks(Number(e.target.value))}
                  min={1}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#0B2545]"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Question Count</label>
                <input
                  type="number"
                  value={formQuestionCount}
                  onChange={(e) => setFormQuestionCount(Number(e.target.value))}
                  min={1}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#0B2545]"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Description (Optional)</label>
              <textarea
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm min-h-[70px] focus:outline-none focus:border-[#0B2545]"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Replace PDF File (Optional)
              </label>
              <p className="text-xs text-gray-500 mb-2">
                Current file: <span className="font-medium text-gray-700">{activeSet?.file_name || 'Question Paper.pdf'}</span> ({formatBytes(activeSet?.file_size)})
              </p>
              <input
                type="file"
                accept=".pdf,application/pdf"
                onChange={handleFileChange}
                className="w-full text-xs text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
              <select
                value={formStatus}
                onChange={(e) => setFormStatus(e.target.value as any)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#0B2545]"
              >
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>

            <DialogFooter className="pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => setIsEditOpen(false)}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={submitting}
                className="bg-[#0B2545] hover:bg-[#163E6C] text-white"
              >
                {submitting ? <ButtonSpinner text="Saving Changes..." /> : 'Save Changes'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* PDF Preview Modal */}
      <Dialog open={isPreviewOpen} onOpenChange={setIsPreviewOpen}>
        <DialogContent className="max-w-4xl h-[85vh] flex flex-col p-4">
          <DialogHeader className="flex flex-row items-center justify-between border-b pb-3">
            <div>
              <DialogTitle className="text-lg font-bold">{activeSet?.title}</DialogTitle>
              <p className="text-xs text-gray-500 mt-0.5">
                {activeSet?.category_name} • {activeSet?.level_name} {activeSet?.subject_name ? `• ${activeSet.subject_name}` : ''}
              </p>
            </div>
            {activeSet?.pdf_file && (
              <div className="flex items-center gap-2">
                <a
                  href={activeSet.pdf_file}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-1.5 rounded-lg transition-colors"
                >
                  <ExternalLink className="w-3.5 h-3.5" /> Open in New Tab
                </a>
                <a
                  href={activeSet.pdf_file}
                  download
                  className="inline-flex items-center gap-1 text-xs bg-[#0B2545] hover:bg-[#163E6C] text-white px-3 py-1.5 rounded-lg transition-colors"
                >
                  <Download className="w-3.5 h-3.5" /> Download
                </a>
              </div>
            )}
          </DialogHeader>

          <div className="flex-1 w-full h-full min-h-0 bg-gray-100 rounded-lg overflow-hidden mt-3">
            {activeSet?.pdf_file ? (
              <iframe
                src={`${activeSet.pdf_file}#toolbar=1`}
                className="w-full h-full border-0"
                title={activeSet.title}
              />
            ) : (
              <div className="flex items-center justify-center h-full text-gray-400">
                No PDF file available
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
