'use client';

import { useState, useEffect, useRef } from 'react';
import { adminQuestionApi, AdminQuestion, QuestionStats } from '@/lib/api/admin-questions';
import { adminCollectionsApi, QuestionCollection } from '@/lib/api/admin-collections';
import { adminApi, AdminTag } from '@/lib/api/admin';
import { publicApi, PublicCourse } from '@/lib/api/public-api';
import Link from 'next/link';
import {
  CheckSquare, Plus, Search, Upload,
  Edit2, Trash2, Copy, BookOpen, Layers,
  Wand2, FolderPlus, ClipboardCheck, Tag as TagIcon, ChevronRight
} from 'lucide-react';
import { toast } from 'react-hot-toast';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { InlineLoader } from '@/components/ui/loading-states';
import { AcademicDependentSelect } from '@/components/admin/syllabus/AcademicDependentSelect';

export default function QuestionBankPage() {
  const [questions, setQuestions] = useState<AdminQuestion[]>([]);
  const [stats, setStats] = useState<QuestionStats | null>(null);
  const [collections, setCollections] = useState<QuestionCollection[]>([]);
  const [tags, setTags] = useState<AdminTag[]>([]);
  const [courses, setCourses] = useState<PublicCourse[]>([]);
  const [loading, setLoading] = useState(true);

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // Modals
  const [isCollectionModalOpen, setIsCollectionModalOpen] = useState(false);
  const [selectedCollectionId, setSelectedCollectionId] = useState<string>('');
  const [isTagModalOpen, setIsTagModalOpen] = useState(false);
  const [selectedBulkTagIds, setSelectedBulkTagIds] = useState<number[]>([]);

  // Bulk Academic Mapping Modal
  const [isBulkMapModalOpen, setIsBulkMapModalOpen] = useState(false);
  const [bulkMapCourseId, setBulkMapCourseId] = useState<string>('');
  const [bulkMapCategoryId, setBulkMapCategoryId] = useState<string>('');
  const [bulkMapExamId, setBulkMapExamId] = useState<string>('');
  const [bulkMapSubjectId, setBulkMapSubjectId] = useState<string>('');
  const [bulkMapChapterId, setBulkMapChapterId] = useState<string>('');
  const [bulkMapTopicId, setBulkMapTopicId] = useState<string>('');
  const [bulkMapLoading, setBulkMapLoading] = useState(false);

  // Filters
  const [search, setSearch] = useState('');
  const [selectedType, setSelectedType] = useState('');
  const [selectedStatus, setSelectedStatus] = useState('');
  const [selectedDifficulty, setSelectedDifficulty] = useState('');
  const [selectedAiStatus, setSelectedAiStatus] = useState('');
  const [selectedMapping, setSelectedMapping] = useState<'all' | 'mapped' | 'needs_mapping'>('all');
  const [selectedCourse, setSelectedCourse] = useState<string>('');
  // Tag filter: multi-select, matches ANY of the selected tags
  // (tag_objects__in on the backend) - see QuestionSelectionService docs.
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([]);
  
  // Pagination
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);

  // Guards against a slow earlier fetch overwriting a newer one's results.
  const latestRequestId = useRef(0);

  useEffect(() => {
    fetchStats();
    fetchCollections();
    fetchTags();
    fetchCourses();
  }, []);

  // Debounce search: wait for typing to pause before hitting the API,
  // instead of firing a request on every keystroke.
  const [debouncedSearch, setDebouncedSearch] = useState('');
  useEffect(() => {
    const timeout = setTimeout(() => setDebouncedSearch(search), 350);
    return () => clearTimeout(timeout);
  }, [search]);

  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, selectedType, selectedStatus, selectedDifficulty, selectedAiStatus, selectedTagIds, selectedMapping, selectedCourse]);

  useEffect(() => {
    fetchQuestions();
  }, [page, debouncedSearch, selectedType, selectedStatus, selectedDifficulty, selectedAiStatus, selectedTagIds, selectedMapping, selectedCourse]);

  const fetchStats = async () => {
    try {
      const data = await adminQuestionApi.getStats();
      setStats(data);
    } catch (error) {
      console.error('Failed to load stats', error);
    }
  };

  const fetchCollections = async () => {
    try {
      const data = await adminCollectionsApi.getCollections();
      setCollections(data);
    } catch (error) {
      console.error('Failed to load collections', error);
    }
  };

  const fetchTags = async () => {
    try {
      const data = await adminApi.getTags({ pageSize: 200 });
      setTags(data.results || []);
    } catch (error) {
      console.error('Failed to load tags', error);
    }
  };

  const fetchCourses = async () => {
    try {
      const data = await publicApi.getCourses();
      setCourses(data || []);
    } catch (error) {
      console.error('Failed to load courses', error);
    }
  };

  const fetchQuestions = async () => {
    const requestId = ++latestRequestId.current;
    setLoading(true);
    try {
      const data = await adminQuestionApi.getQuestions({
        page,
        search: debouncedSearch || undefined,
        question_type: selectedType || undefined,
        status: selectedStatus || undefined,
        difficulty: selectedDifficulty || undefined,
        ai_status: selectedAiStatus || undefined,
        tag_objects__in: selectedTagIds.length > 0 ? selectedTagIds.join(',') : undefined,
        mapping: selectedMapping !== 'all' ? selectedMapping : undefined,
        course: selectedCourse || undefined,
      });
      // A slower earlier request must not overwrite a newer one's results.
      if (requestId !== latestRequestId.current) return;
      const results = Array.isArray(data) ? data : (data.results || []);
      setQuestions(results);
      setHasMore(!Array.isArray(data) && !!data.next);
      setSelectedIds(new Set()); // clear selection on reload
    } catch (error) {
      if (requestId !== latestRequestId.current) return;
      toast.error('Failed to load questions');
    } finally {
      if (requestId === latestRequestId.current) setLoading(false);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    // Bypass the debounce timer on explicit submit (Enter key).
    setDebouncedSearch(search);
    setPage(1);
  };

  const handleDuplicate = async (id: number) => {
    try {
      await adminQuestionApi.duplicateQuestion(id);
      toast.success('Question duplicated as draft');
      fetchStats();
      fetchQuestions();
    } catch (error) {
      toast.error('Failed to duplicate question');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this question?')) return;
    try {
      await adminQuestionApi.deleteQuestion(id);
      toast.success('Question deleted');
      fetchStats();
      fetchQuestions();
    } catch (error) {
      toast.error('Failed to delete question');
    }
  };
  
  const handleBulkAction = async (
    action: 'publish' | 'draft' | 'archive' | 'delete' | 'add_to_collection' | 'remove_from_collection' | 'add_tags' | 'remove_tags',
    collectionIds?: number[],
    tagIds?: number[]
  ) => {
    if (selectedIds.size === 0) return;
    if (action === 'delete' && !confirm(`Are you sure you want to delete ${selectedIds.size} questions?`)) return;

    try {
      // The backend's bulk action for "Publish" is named `approve` (it also enforces
      // that an admin cannot approve their own question); 'publish' is not a valid action.
      const res = await adminQuestionApi.bulkAction(action === 'publish' ? 'approve' : action, Array.from(selectedIds), collectionIds, tagIds);
      if (res.error) {
        toast.error(res.error);
      } else {
        toast.success(`Successfully applied action to ${res.count} questions`);
        fetchStats();
        fetchQuestions();
        setIsCollectionModalOpen(false);
        setIsTagModalOpen(false);
        setSelectedBulkTagIds([]);
      }
    } catch (error: any) {
      toast.error(error?.data?.error || `Failed to perform bulk action`);
    }
  };

  const handleBulkMapCourseChange = (cid: string) => {
    setBulkMapCourseId(cid);
    const course = courses.find(c => String(c.id) === cid);
    if (course?.exam) {
      if (course.exam.category_id) {
        setBulkMapCategoryId(String(course.exam.category_id));
      }
      setBulkMapExamId(String(course.exam.id));
      setBulkMapSubjectId('');
      setBulkMapChapterId('');
      setBulkMapTopicId('');
    }
  };

  const handleBulkMapSubmit = async () => {
    if (selectedIds.size === 0 || !bulkMapCourseId) {
      toast.error('Please select a target course');
      return;
    }
    if (!confirm(`Are you sure you want to map ${selectedIds.size} questions to this academic scope? Question IDs, text, options, answers, and student history will be preserved.`)) return;

    setBulkMapLoading(true);
    try {
      const res = await adminQuestionApi.bulkAction(
        'map_academic',
        Array.from(selectedIds),
        undefined,
        undefined,
        {
          course_id: Number(bulkMapCourseId),
          exam_id: bulkMapExamId ? Number(bulkMapExamId) : undefined,
          subject_id: bulkMapSubjectId ? Number(bulkMapSubjectId) : undefined,
          chapter_id: bulkMapChapterId ? Number(bulkMapChapterId) : undefined,
          topic_id: bulkMapTopicId ? Number(bulkMapTopicId) : undefined,
        }
      );
      if (res.error) {
        toast.error(res.error);
      } else {
        toast.success(res.message || `Successfully mapped ${res.count} questions`);
        setIsBulkMapModalOpen(false);
        setBulkMapCourseId('');
        setBulkMapExamId('');
        setBulkMapSubjectId('');
        setBulkMapChapterId('');
        setBulkMapTopicId('');
        fetchStats();
        fetchQuestions();
      }
    } catch (error: any) {
      toast.error(error?.data?.error || 'Failed to apply academic mapping');
    } finally {
      setBulkMapLoading(false);
    }
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === questions.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(questions.map(q => q.id)));
    }
  };

  const toggleSelect = (id: number) => {
    const newSet = new Set(selectedIds);
    if (newSet.has(id)) newSet.delete(id);
    else newSet.add(id);
    setSelectedIds(newSet);
  };

  // Group the current (filtered/paginated) results by Collection: a question
  // in one or more Collections is shown once under its first Collection
  // instead of as its own row, so the list reads as "collections, then
  // uncategorized questions" rather than a flat mix of both. Opening a
  // collection's own page (linked below) lists every question inside it.
  const collectionGroups: { collection: QuestionCollection; questions: AdminQuestion[] }[] = [];
  const uncategorized: AdminQuestion[] = [];
  {
    const groupsById = new Map<number, AdminQuestion[]>();
    for (const q of questions) {
      const first = q.collections && q.collections.length > 0 ? q.collections[0] : null;
      if (!first) {
        uncategorized.push(q);
        continue;
      }
      if (!groupsById.has(first.id)) groupsById.set(first.id, []);
      groupsById.get(first.id)!.push(q);
    }
    for (const [collectionId, qs] of groupsById) {
      const collection = collections.find(c => c.id === collectionId);
      if (collection) {
        collectionGroups.push({ collection, questions: qs });
      } else {
        uncategorized.push(...qs);
      }
    }
  }

  return (
    <div className="p-5 md:p-6 space-y-6 max-w-[1600px] mx-auto">
      <div className="flex flex-wrap justify-between items-start gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Objective Question Bank</h1>
          <p className="text-gray-500 mt-1">Manage individual objective and MCQ questions across the platform.</p>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <Link
            href="/admin-dashboard/academic/questions/import"
            className="bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 px-4 py-2 rounded-lg flex items-center gap-2 transition-colors font-medium text-sm whitespace-nowrap"
          >
            <Upload className="w-4 h-4" />
            Import Excel
          </Link>
          <Link
            href="/admin-dashboard/academic/questions/create"
            className="bg-[#0B2545] hover:bg-[#163E6C] text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors font-medium text-sm shadow-md whitespace-nowrap"
          >
            <Plus className="w-4 h-4" />
            Add Question
          </Link>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500">Total Questions</p>
              <p className="text-3xl font-bold text-gray-900 mt-1">{stats.total}</p>
            </div>
            <div className="p-3 bg-navy-50 rounded-lg">
              <Layers className="w-6 h-6 text-navy-600" />
            </div>
          </div>
          <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500">Mapped Questions</p>
              <p className="text-3xl font-bold text-emerald-600 mt-1">{stats.mapped ?? 0}</p>
            </div>
            <div className="p-3 bg-emerald-50 rounded-lg">
              <CheckSquare className="w-6 h-6 text-emerald-600" />
            </div>
          </div>
          <div className={`p-6 rounded-xl border shadow-sm flex items-center justify-between transition-colors ${
            (stats.needs_mapping ?? 0) > 0 ? 'bg-amber-50/70 border-amber-200' : 'bg-white border-gray-100'
          }`}>
            <div>
              <p className="text-sm font-medium text-amber-800">Needs Mapping</p>
              <p className="text-3xl font-bold text-amber-900 mt-1">{stats.needs_mapping ?? 0}</p>
            </div>
            <div className="p-3 bg-amber-100 rounded-lg">
              <BookOpen className="w-6 h-6 text-amber-600" />
            </div>
          </div>
          <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500">Active Questions</p>
              <p className="text-3xl font-bold text-gray-900 mt-1">{stats.active}</p>
            </div>
            <div className="p-3 bg-blue-50 rounded-lg">
              <BookOpen className="w-6 h-6 text-blue-600" />
            </div>
          </div>
        </div>
      )}

      {/* Needs Mapping Banner */}
      {stats && (stats.needs_mapping ?? 0) > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-amber-900 shadow-sm">
          <div className="flex items-center gap-2.5">
            <span className="flex h-3 w-3 rounded-full bg-amber-500 animate-pulse shrink-0" />
            <p className="text-sm font-medium">
              Some questions need academic mapping before they can be used in student practice. ({stats.needs_mapping} question{(stats.needs_mapping ?? 0) > 1 ? 's' : ''} require course/syllabus mapping)
            </p>
          </div>
          <button
            type="button"
            onClick={() => setSelectedMapping('needs_mapping')}
            className="px-3.5 py-1.5 bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors whitespace-nowrap"
          >
            Filter Needs Mapping
          </button>
        </div>
      )}

      {/* Toolbar */}
      <div className="bg-white p-4 rounded-xl border border-gray-100 shadow-sm flex flex-col md:flex-row gap-4 justify-between items-center">
        <div className="flex items-center gap-3 w-full md:w-auto">
          <form onSubmit={handleSearch} className="relative w-full md:w-96">
            <Search className="w-5 h-5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input 
              type="text" 
              placeholder="Search questions, options, or answers..." 
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:border-navy-500"
            />
          </form>
          {loading && questions.length > 0 && (
            <InlineLoader text="Refreshing..." className="shrink-0 text-xs" />
          )}
        </div>
        
        <div className="flex gap-2 w-full md:w-auto items-center flex-wrap">
          {selectedIds.size > 0 && (
            <div className="flex items-center gap-2 mr-2 bg-navy-50 px-3 py-1.5 rounded-lg border border-navy-100 flex-wrap">
              <span className="text-sm font-medium text-navy-800">{selectedIds.size} selected</span>
              <div className="h-4 w-px bg-navy-200 mx-1"></div>
              <button onClick={() => setIsBulkMapModalOpen(true)} className="text-xs font-semibold text-blue-700 hover:text-blue-800 flex items-center gap-1"><BookOpen className="w-3.5 h-3.5"/> Map Academic Scope</button>
              <div className="h-4 w-px bg-navy-200 mx-1"></div>
              <button onClick={() => setIsCollectionModalOpen(true)} className="text-xs font-medium text-indigo-700 hover:text-indigo-800 flex items-center gap-1"><FolderPlus className="w-3 h-3"/> Add to Collection</button>
              <button onClick={() => setIsTagModalOpen(true)} className="text-xs font-medium text-indigo-700 hover:text-indigo-800 flex items-center gap-1 ml-1"><TagIcon className="w-3 h-3"/> Add Tags</button>
              <button onClick={() => handleBulkAction('publish')} className="text-xs font-medium text-green-700 hover:text-green-800 ml-1">Publish</button>
              <button onClick={() => handleBulkAction('draft')} className="text-xs font-medium text-gray-600 hover:text-gray-800 ml-1">Draft</button>
              <button onClick={() => handleBulkAction('delete')} className="text-xs font-medium text-red-600 hover:text-red-800 ml-1">Delete</button>
            </div>
          )}
          <select 
            value={selectedMapping} 
            onChange={(e) => setSelectedMapping(e.target.value as any)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-navy-500 font-medium"
          >
            <option value="all">Mapping: All</option>
            <option value="mapped">Mapping: Mapped Only</option>
            <option value="needs_mapping">Mapping: Needs Mapping</option>
          </select>
          <select 
            value={selectedCourse} 
            onChange={(e) => setSelectedCourse(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-navy-500 max-w-[180px]"
          >
            <option value="">All Courses</option>
            {courses.map(c => (
              <option key={c.id} value={String(c.id)}>{c.title}</option>
            ))}
          </select>
          <select 
            value={selectedAiStatus} 
            onChange={(e) => setSelectedAiStatus(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-navy-500"
          >
            <option value="">All AI Status</option>
            <option value="pending">Pending AI Generation</option>
            <option value="reviewed">AI Reviewed</option>
            <option value="approved">AI Approved</option>
          </select>
          <select 
            value={selectedType} 
            onChange={(e) => setSelectedType(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-navy-500"
          >
            <option value="">All Types</option>
            <option value="mcq">MCQ</option>
            <option value="true_false">True / False</option>
          </select>
          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-navy-500"
          >
            <option value="">All Statuses</option>
            <option value="draft">Draft</option>
            <option value="pending_review">Pending Review</option>
            <option value="approved">Approved</option>
            <option value="changes_requested">Changes Requested</option>
            <option value="rejected">Rejected</option>
            <option value="archived">Archived</option>
          </select>
          {tags.length > 0 && (
            <details className="relative">
              <summary className="list-none cursor-pointer border border-gray-200 rounded-lg px-3 py-2 text-sm flex items-center gap-1.5">
                <TagIcon className="w-3.5 h-3.5" />
                {selectedTagIds.length > 0 ? `${selectedTagIds.length} Tag${selectedTagIds.length > 1 ? 's' : ''}` : 'All Tags'}
              </summary>
              <div className="absolute right-0 mt-1 z-10 bg-white border border-gray-200 rounded-lg shadow-lg p-2 w-56 max-h-64 overflow-y-auto">
                {tags.filter(t => t.is_active).map(t => (
                  <label key={t.id} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-gray-50 cursor-pointer text-sm">
                    <input
                      type="checkbox"
                      checked={selectedTagIds.includes(t.id)}
                      onChange={() => {
                        setSelectedTagIds(prev =>
                          prev.includes(t.id) ? prev.filter(id => id !== t.id) : [...prev, t.id]
                        );
                        setPage(1);
                      }}
                    />
                    <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: t.color }} />
                    {t.name}
                  </label>
                ))}
                {selectedTagIds.length > 0 && (
                  <button
                    type="button"
                    onClick={() => { setSelectedTagIds([]); setPage(1); }}
                    className="text-xs text-gray-500 hover:text-gray-700 mt-1 px-2"
                  >
                    Clear
                  </button>
                )}
              </div>
            </details>
          )}
        </div>
      </div>

      <Dialog open={isCollectionModalOpen} onOpenChange={setIsCollectionModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add {selectedIds.size} Question{selectedIds.size !== 1 ? 's' : ''} to Collection</DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-2 max-h-60 overflow-y-auto">
            {collections.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">
                No collections yet. <Link href="/admin-dashboard/academic/collections/create" className="text-[#0B2545] underline">Create one first.</Link>
              </p>
            ) : (
              collections.map(c => (
                <label key={c.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                  <input
                    type="radio"
                    name="collection"
                    value={c.id}
                    checked={selectedCollectionId === String(c.id)}
                    onChange={() => setSelectedCollectionId(String(c.id))}
                    className="w-4 h-4 text-[#0B2545]"
                  />
                  <div className="flex items-center gap-2 flex-1">
                    <div className="w-7 h-7 rounded-md flex items-center justify-center text-white text-xs font-bold" style={{ backgroundColor: c.color || '#0B2545' }}>
                      {c.name[0]?.toUpperCase()}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-800">{c.name}</p>
                      <p className="text-xs text-gray-400">{c.question_count ?? 0} questions</p>
                    </div>
                  </div>
                </label>
              ))
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setIsCollectionModalOpen(false); setSelectedCollectionId(''); }}>Cancel</Button>
            <Button
              onClick={() => handleBulkAction('add_to_collection', selectedCollectionId ? [parseInt(selectedCollectionId)] : [])}
              disabled={!selectedCollectionId}
              className="bg-[#0B2545] hover:bg-[#163E6C] text-white"
            >
              Add Questions
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={isTagModalOpen} onOpenChange={setIsTagModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Tags to {selectedIds.size} Question{selectedIds.size !== 1 ? 's' : ''}</DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-1 max-h-60 overflow-y-auto">
            {tags.filter(t => t.is_active).length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">
                No tags yet. <Link href="/admin-dashboard/academic/tags" className="text-[#0B2545] underline">Create one first.</Link>
              </p>
            ) : (
              tags.filter(t => t.is_active).map(t => (
                <label key={t.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedBulkTagIds.includes(t.id)}
                    onChange={() => setSelectedBulkTagIds(prev =>
                      prev.includes(t.id) ? prev.filter(id => id !== t.id) : [...prev, t.id]
                    )}
                    className="w-4 h-4"
                  />
                  <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: t.color }} />
                  <p className="text-sm font-medium text-gray-800">{t.name}</p>
                </label>
              ))
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setIsTagModalOpen(false); setSelectedBulkTagIds([]); }}>Cancel</Button>
            <Button
              onClick={() => handleBulkAction('add_tags', undefined, selectedBulkTagIds)}
              disabled={selectedBulkTagIds.length === 0}
              className="bg-[#0B2545] hover:bg-[#163E6C] text-white"
            >
              Add Tags
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>


      <Dialog open={isBulkMapModalOpen} onOpenChange={setIsBulkMapModalOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Map Academic Scope for {selectedIds.size} Question{selectedIds.size !== 1 ? 's' : ''}</DialogTitle>
          </DialogHeader>
          <div className="py-3 space-y-4 max-h-[70vh] overflow-y-auto pr-1">
            <div className="bg-blue-50/70 border border-blue-200 text-blue-900 text-xs p-3.5 rounded-lg space-y-1">
              <p className="font-semibold flex items-center gap-1.5">
                <BookOpen className="w-4 h-4 text-blue-700" /> Safe Academic Scope Assignment
              </p>
              <p>
                The target academic hierarchy will be validated before committing. Existing question text, options, answers, question IDs, and student attempt histories are strictly preserved.
              </p>
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-800 mb-1">
                Target Course <span className="text-red-500">*</span>
              </label>
              <select
                value={bulkMapCourseId}
                onChange={(e) => handleBulkMapCourseChange(e.target.value)}
                className="w-full border border-gray-200 rounded-lg p-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#0B2545]/20 font-medium"
              >
                <option value="">Select Target Course</option>
                {courses.map(c => (
                  <option key={c.id} value={String(c.id)}>
                    {c.title} {c.exam?.title ? `(${c.exam.title})` : ''}
                  </option>
                ))}
              </select>
              <p className="text-xs text-gray-500 mt-1">
                Selecting a course automatically scopes the academic selectors below to that course&apos;s curriculum.
              </p>
            </div>

            <div className="pt-2 border-t border-gray-100">
              <AcademicDependentSelect
                category={bulkMapCategoryId}
                position={bulkMapExamId}
                subject={bulkMapSubjectId}
                chapter={bulkMapChapterId}
                topic={bulkMapTopicId}
                onChange={(field, val) => {
                  if (field === 'category') {
                    setBulkMapCategoryId(val || '');
                    setBulkMapExamId('');
                    setBulkMapSubjectId('');
                    setBulkMapChapterId('');
                    setBulkMapTopicId('');
                  } else if (field === 'position' || field === 'exam') {
                    setBulkMapExamId(val || '');
                    setBulkMapSubjectId('');
                    setBulkMapChapterId('');
                    setBulkMapTopicId('');
                  } else if (field === 'subject') {
                    setBulkMapSubjectId(val || '');
                    setBulkMapChapterId('');
                    setBulkMapTopicId('');
                  } else if (field === 'chapter') {
                    setBulkMapChapterId(val || '');
                    setBulkMapTopicId('');
                  } else if (field === 'topic') {
                    setBulkMapTopicId(val || '');
                  }
                }}
                requiredLevels={['category', 'position']}
                maxLevel="topic"
                layout="grid"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsBulkMapModalOpen(false)} disabled={bulkMapLoading}>
              Cancel
            </Button>
            <Button
              onClick={handleBulkMapSubmit}
              disabled={!bulkMapCourseId || bulkMapLoading}
              className="bg-[#0B2545] hover:bg-[#163E6C] text-white"
            >
              {bulkMapLoading ? 'Applying...' : `Apply Mapping (${selectedIds.size} questions)`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Data Table */}
      <div className="bg-white border border-gray-100 shadow-sm rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100 text-sm text-gray-500">
                <th className="p-4 w-12">
                  <input 
                    type="checkbox" 
                    checked={questions.length > 0 && selectedIds.size === questions.length}
                    onChange={toggleSelectAll}
                    className="rounded text-navy-600 focus:ring-navy-500 w-4 h-4"
                  />
                </th>
                <th className="p-4 font-medium">Question</th>
                <th className="p-4 font-medium">Type</th>
                <th className="p-4 font-medium">Course &amp; Academic Scope</th>
                <th className="p-4 font-medium">Mapping Status</th>
                <th className="p-4 font-medium">Status</th>
                <th className="p-4 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading && questions.length === 0 ? (
                Array.from({ length: 6 }).map((_, r) => (
                  <tr key={r} className="animate-pulse">
                    <td className="p-4 w-12"><div className="h-4 w-4 bg-gray-200 rounded" /></td>
                    <td className="p-4"><div className="h-4 w-72 bg-gray-200 rounded mb-1.5" /><div className="h-3 w-40 bg-gray-100 rounded" /></td>
                    <td className="p-4"><div className="h-4 w-16 bg-gray-200 rounded" /></td>
                    <td className="p-4"><div className="h-4 w-32 bg-gray-200 rounded" /></td>
                    <td className="p-4"><div className="h-5 w-20 bg-gray-200 rounded-full" /></td>
                    <td className="p-4"><div className="h-6 w-20 bg-gray-200 rounded-full" /></td>
                    <td className="p-4 text-right"><div className="h-8 w-8 bg-gray-200 rounded ml-auto" /></td>
                  </tr>
                ))
              ) : questions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-8 text-center text-gray-500">
                    <p className="mb-3">No questions found matching your criteria.</p>
                    <Link
                      href="/admin-dashboard/academic/questions/create"
                      className="inline-flex items-center gap-2 bg-[#0B2545] hover:bg-[#163E6C] text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                    >
                      <Plus className="w-4 h-4" />
                      Add Question
                    </Link>
                  </td>
                </tr>
              ) : (
                <>
                {collectionGroups.map(({ collection, questions: groupQuestions }) => (
                  <tr key={`collection-${collection.id}`} className="hover:bg-indigo-50/40 transition-colors">
                    <td className="p-4"></td>
                    <td colSpan={6} className="p-0">
                      <Link
                        href={`/admin-dashboard/academic/collections/${collection.id}`}
                        className="flex items-center justify-between gap-3 px-4 py-3"
                      >
                        <div className="flex items-center gap-3">
                          <div
                            className="w-8 h-8 rounded-md flex items-center justify-center text-white text-xs font-bold shrink-0"
                            style={{ backgroundColor: collection.color || '#0B2545' }}
                          >
                            {collection.name[0]?.toUpperCase()}
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                              <FolderPlus className="w-4 h-4 text-indigo-500" /> {collection.name}
                            </p>
                            <p className="text-xs text-gray-500 mt-0.5">
                              {groupQuestions.length} question{groupQuestions.length === 1 ? '' : 's'} in this view
                              {typeof collection.question_count === 'number' && collection.question_count !== groupQuestions.length
                                ? ` • ${collection.question_count} total in collection` : ''}
                            </p>
                          </div>
                        </div>
                        <ChevronRight className="w-4 h-4 text-gray-400" />
                      </Link>
                    </td>
                  </tr>
                ))}
                {uncategorized.map((q) => (
                  <tr key={q.id} className={`hover:bg-gray-50 transition-colors group ${selectedIds.has(q.id) ? 'bg-blue-50/50' : ''}`}>
                    <td className="p-4">
                      <input 
                        type="checkbox" 
                        checked={selectedIds.has(q.id)}
                        onChange={() => toggleSelect(q.id)}
                        className="rounded text-navy-600 focus:ring-navy-500 w-4 h-4"
                      />
                    </td>
                    <td className="p-4">
                      <div className="flex items-start gap-2">
                        <span className="font-mono text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded mt-0.5 whitespace-nowrap">
                          {q.question_id || `Q-${q.id.toString().padStart(6, '0')}`}
                        </span>
                        <div>
                          <div className="line-clamp-2 text-sm font-medium text-gray-900 max-w-md">
                            {q.text}
                          </div>
                          <div className="text-xs text-gray-500 mt-1 flex items-center gap-2 flex-wrap">
                            <span>{q.marks} Marks • {q.expected_time_minutes} min</span>
                            {q.usage_count > 0 && (
                              <span className="text-blue-600 bg-blue-50 px-1.5 rounded-full flex items-center gap-1">
                                <Layers className="w-3 h-3" /> Used in {q.usage_count} sets
                              </span>
                            )}
                            {q.collections && q.collections.length > 0 && (
                              <span className="text-indigo-600 bg-indigo-50 px-1.5 rounded-full flex items-center gap-1">
                                <FolderPlus className="w-3 h-3" /> {q.collections.length} Collections
                              </span>
                            )}
                            {q.tag_objects && q.tag_objects.slice(0, 3).map(t => (
                              <span
                                key={t.id}
                                className="px-1.5 rounded-full text-white"
                                style={{ backgroundColor: t.color }}
                              >
                                {t.name}
                              </span>
                            ))}
                            {q.tag_objects && q.tag_objects.length > 3 && (
                              <span className="text-gray-500 bg-gray-100 px-1.5 rounded-full">
                                +{q.tag_objects.length - 3}
                              </span>
                            )}
                            {q.ai_status === 'pending' && (
                              <span className="text-amber-600 bg-amber-50 px-1.5 rounded-full flex items-center gap-1">
                                <Wand2 className="w-3 h-3" /> AI Pending
                              </span>
                            )}
                            {q.ai_status === 'approved' && (
                              <span className="text-emerald-600 bg-emerald-50 px-1.5 rounded-full flex items-center gap-1">
                                <Wand2 className="w-3 h-3" /> AI Generated
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="p-4">
                      <span className={`inline-flex items-center px-2 py-1 rounded-md text-xs font-medium ${
                        q.question_type === 'mcq' ? 'bg-blue-50 text-blue-700' : 
                        'bg-purple-50 text-purple-700'
                      }`}>
                        {q.question_type.replace('_', ' ').toUpperCase()}
                      </span>
                    </td>
                    <td className="p-4">
                      <div className="text-xs font-semibold text-navy-800">
                        {q.course_title ? (
                          <span className="flex items-center gap-1">
                            <BookOpen className="w-3 h-3 text-blue-600 shrink-0 inline" />
                            <span className="truncate max-w-[180px]">{q.course_title}</span>
                          </span>
                        ) : (
                          <span className="text-gray-400 italic">No Course</span>
                        )}
                      </div>
                      <div className="text-xs text-gray-700 font-medium mt-0.5">{q.position_name || 'No Position'}</div>
                      <div className="text-xs text-gray-500 truncate max-w-[200px] mt-0.5">
                        {q.subject_name || 'No Subject'} {q.chapter_name ? `• ${q.chapter_name}` : ''} {q.topic_name ? `• ${q.topic_name}` : ''}
                      </div>
                    </td>
                    <td className="p-4">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold capitalize ${
                        q.mapping_status === 'mapped'
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          : q.mapping_status === 'incomplete'
                          ? 'bg-amber-50 text-amber-700 border border-amber-200'
                          : q.mapping_status === 'invalid'
                          ? 'bg-purple-50 text-purple-700 border border-purple-200'
                          : 'bg-rose-50 text-rose-700 border border-rose-200'
                      }`}>
                        {q.mapping_status_display || (
                          q.mapping_status === 'mapped' ? 'Mapped' :
                          q.mapping_status === 'incomplete' ? 'Incomplete' :
                          q.mapping_status === 'invalid' ? 'Invalid' : 'Unassigned'
                        )}
                      </span>
                    </td>
                    <td className="p-4">
                      <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                        q.status === 'approved' || q.status === 'published' ? 'bg-green-100 text-green-700' : 
                        q.status === 'draft' ? 'bg-gray-100 text-gray-700' : 'bg-red-100 text-red-700'
                      }`}>
                        {q.status}
                      </span>
                    </td>
                    <td className="p-4 text-right">
                      <div className="flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        {q.status === 'pending_review' && (
                          <Link 
                            href={`/admin-dashboard/questions/review/${q.id}`}
                            className="p-1.5 text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded"
                            title="Review Question"
                          >
                            <ClipboardCheck className="w-4 h-4" />
                          </Link>
                        )}
                        {q.ai_status === 'pending' && (
                          <Link 
                            href={`/admin-dashboard/academic/questions/${q.id}/edit`}
                            className="p-1.5 text-amber-600 hover:text-amber-700 hover:bg-amber-50 rounded"
                            title="Generate AI Options"
                          >
                            <Wand2 className="w-4 h-4" />
                          </Link>
                        )}
                        <button 
                          onClick={() => handleDuplicate(q.id)}
                          className="p-1.5 text-gray-400 hover:text-navy-600 hover:bg-navy-50 rounded"
                          title="Duplicate"
                        >
                          <Copy className="w-4 h-4" />
                        </button>
                        <Link 
                          href={`/admin-dashboard/academic/questions/${q.id}/edit`}
                          className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded"
                          title="Edit"
                        >
                          <Edit2 className="w-4 h-4" />
                        </Link>
                        <button 
                          onClick={() => handleDelete(q.id)}
                          className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded"
                          title="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                </>
              )}
            </tbody>
          </table>
        </div>
        {(hasMore || page > 1) && (
          <div className="flex items-center justify-center gap-4 p-4 border-t border-gray-100">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1 || loading}
              className="px-3 py-1.5 text-sm font-medium text-gray-600 border border-gray-200 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              Previous
            </button>
            <span className="text-sm text-gray-500">Page {page}</span>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={!hasMore || loading}
              className="px-3 py-1.5 text-sm font-medium text-gray-600 border border-gray-200 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

