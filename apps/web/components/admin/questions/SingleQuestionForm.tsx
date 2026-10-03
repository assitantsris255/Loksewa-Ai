'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { adminQuestionApi, AdminQuestion } from '@/lib/api/admin-questions';
import { adminCollectionsApi, QuestionCollection } from '@/lib/api/admin-collections';
import { adminApi, AdminTag } from '@/lib/api/admin';
import { publicApi, PublicCourse } from '@/lib/api/public-api';
import { Save, FileText, Wand2, BookOpen } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { AcademicDependentSelect } from '@/components/admin/syllabus/AcademicDependentSelect';
import { Button } from '@/components/ui/button';

/** Pulls the most useful message out of a DRF error body, which may be
 *  { detail }, { non_field_errors: [...] }, or { <field>: [...] }. */
function extractApiError(error: any, fallback: string): string {
  const data = error?.data;
  if (!data) return error?.message || fallback;
  if (typeof data === 'string') return data;
  if (data.detail) return data.detail;
  if (Array.isArray(data.non_field_errors) && data.non_field_errors.length) {
    return data.non_field_errors[0];
  }
  const firstField = Object.keys(data)[0];
  if (firstField) {
    const value = data[firstField];
    const message = Array.isArray(value) ? value[0] : value;
    return `${firstField}: ${message}`;
  }
  return fallback;
}

export function SingleQuestionForm({ initialData, onSaveSuccess }: { initialData?: any, onSaveSuccess?: () => void }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  
  // Form State
  const qType = 'mcq';
  const [status, setStatus] = useState<'draft' | 'pending_review' | 'approved' | 'rejected'>(initialData?.status || 'draft');
  const [text, setText] = useState(initialData?.text || '');
  const [marks, setMarks] = useState(initialData?.marks || 1);
  const [negativeMarks, setNegativeMarks] = useState(initialData?.negative_marks || 0);
  const [expectedTime, setExpectedTime] = useState(initialData?.expected_time_minutes || 1);
  const [explanation, setExplanation] = useState(initialData?.explanation || '');
  const [hint, setHint] = useState(initialData?.hint || '');
  
  // AI Generation
  const [aiGenerate, setAiGenerate] = useState(false);
  
  // MCQ specifics
  const [options, setOptions] = useState({ 
    A: initialData?.option_a || '', 
    B: initialData?.option_b || '', 
    C: initialData?.option_c || '', 
    D: initialData?.option_d || '' 
  });
  const [correctOption, setCorrectOption] = useState<'A'|'B'|'C'|'D'|''>(initialData?.correct_option || '');

  // Course & Syllabus Cascading
  const [courses, setCourses] = useState<PublicCourse[]>([]);
  const [selCourse, setSelCourse] = useState(initialData?.course_id ? String(initialData.course_id) : '');
  const [selCategory, setSelCategory] = useState(initialData?.category_id || '');
  const [selPosition, setSelPosition] = useState(initialData?.position_id || '');
  const [selSubject, setSelSubject] = useState(initialData?.subject_id || '');
  const [selChapter, setSelChapter] = useState(initialData?.chapter_id || '');
  const [selTopic, setSelTopic] = useState(initialData?.topic || '');

  useEffect(() => {
    publicApi.getCourses()
      .then(res => setCourses(res || []))
      .catch(() => setCourses([]));
  }, []);

  // Add to Collection (Optional) - a question can belong to zero, one, or
  // several reusable QuestionCollections. Loaded from the real backend list,
  // never hardcoded.
  const [collections, setCollections] = useState<QuestionCollection[]>([]);
  const [selectedCollectionIds, setSelectedCollectionIds] = useState<number[]>(
    (initialData?.collections || []).map((c: any) => c.id)
  );
  useEffect(() => {
    adminCollectionsApi.getCollections()
      .then(setCollections)
      .catch(() => setCollections([]));
  }, []);
  const toggleCollection = (id: number) => {
    setSelectedCollectionIds(prev =>
      prev.includes(id) ? prev.filter(existing => existing !== id) : [...prev, id]
    );
  };

  // Tags (Optional) - search/filter/discovery metadata, independent of
  // Collections. Only active tags are offered for NEW selection; a tag
  // already on this question (even if since deactivated) stays checked.
  const [tags, setTags] = useState<AdminTag[]>([]);
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>(
    (initialData?.tag_objects || []).map((t: any) => t.id)
  );
  useEffect(() => {
    adminApi.getTags({ pageSize: 200 })
      .then(res => setTags(res.results || []))
      .catch(() => setTags([]));
  }, []);
  const toggleTag = (id: number) => {
    setSelectedTagIds(prev =>
      prev.includes(id) ? prev.filter(existing => existing !== id) : [...prev, id]
    );
  };
  const selectableTags = tags.filter(t => t.is_active || selectedTagIds.includes(t.id));

  const handleCourseChange = (courseId: string) => {
    setSelCourse(courseId);
    if (!courseId) return;
    const course = courses.find(c => String(c.id) === String(courseId));
    if (course?.exam) {
      if (course.exam.category_id) {
        setSelCategory(course.exam.category_id);
      }
      setSelPosition(course.exam.id);
      setSelSubject('');
      setSelChapter('');
      setSelTopic('');
    }
  };

  const handleAcademicChange = (field: string, value: any) => {
    if (field === 'category') {
      setSelCategory(value || '');
      setSelPosition('');
      setSelSubject('');
      setSelChapter('');
      setSelTopic('');
      if (selCourse) {
        const currentCourse = courses.find(c => String(c.id) === String(selCourse));
        if (currentCourse?.exam?.category_id && String(currentCourse.exam.category_id) !== String(value)) {
          setSelCourse('');
        }
      }
    } else if (field === 'position' || field === 'exam') {
      setSelPosition(value || '');
      setSelSubject('');
      setSelChapter('');
      setSelTopic('');
      const matchingCourse = courses.find(c => c.exam && String(c.exam.id) === String(value));
      if (matchingCourse) {
        setSelCourse(String(matchingCourse.id));
      } else {
        setSelCourse('');
      }
    } else if (field === 'subject') {
      setSelSubject(value || '');
      setSelChapter('');
      setSelTopic('');
    } else if (field === 'chapter' || field === 'unit') {
      setSelChapter(value || '');
      setSelTopic('');
    } else if (field === 'topic') {
      setSelTopic(value || '');
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!text.trim()) {
      toast.error('Question text is required.');
      return;
    }

    if (!selCategory || !selPosition) {
      toast.error('Please select Category and Position/Level.');
      return;
    }

    if (!aiGenerate && (!correctOption || !options.A || !options.B || !options.C || !options.D)) {
      toast.error('MCQ requires all 4 options (A, B, C, D) and a correct option selected.');
      return;
    }

    setLoading(true);
    try {
      const payload: Partial<AdminQuestion> = {
        question_type: 'mcq',
        status,
        course: selCourse ? Number(selCourse) : undefined,
        category: Number(selCategory),
        position: Number(selPosition),
        subject: selSubject ? Number(selSubject) : undefined,
        chapter: selChapter ? Number(selChapter) : null,
        topic: selTopic ? Number(selTopic) : null,
        text,
        marks: Number(marks),
        negative_marks: Number(negativeMarks),
        expected_time_minutes: Number(expectedTime),
        explanation,
        hint,
        collection_ids: selectedCollectionIds,
        tag_ids: selectedTagIds,
      };

      if (!aiGenerate) {
        payload.option_a = options.A;
        payload.option_b = options.B;
        payload.option_c = options.C;
        payload.option_d = options.D;
        payload.correct_option = correctOption as 'A'|'B'|'C'|'D';
      } else {
        payload.ai_generate_options = true;
      }

      if (initialData?.id) {
        await adminQuestionApi.updateQuestion(initialData.id, payload);
        toast.success('Question updated successfully!');
      } else {
        await adminQuestionApi.createQuestion(payload);
        toast.success('Question created successfully!');
      }
      
      if (onSaveSuccess) {
        onSaveSuccess();
      } else {
        router.push('/admin-dashboard/academic/questions');
      }
    } catch (error: any) {
      console.error('Failed to create question', error);
      toast.error(extractApiError(error, 'Failed to create question'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSave} className="space-y-6">
      {/* Core Settings */}
      <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm space-y-6">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <FileText className="w-5 h-5 text-[#0B2545]" />
          Configuration
        </h2>
        
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Status</label>
            <select value={status} onChange={(e: any) => setStatus(e.target.value)} className="w-full border border-gray-200 rounded-lg px-3 py-2">
              <option value="draft">Draft</option>
              <option value="pending_review">Pending Review</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Marks</label>
            <input type="number" step="0.5" value={marks} onChange={e => setMarks(Number(e.target.value))} className="w-full border border-gray-200 rounded-lg px-3 py-2" required />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Negative Marks</label>
            <input type="number" step="0.1" value={negativeMarks} onChange={e => setNegativeMarks(Number(e.target.value))} className="w-full border border-gray-200 rounded-lg px-3 py-2" required />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Expected Time (min)</label>
            <input type="number" value={expectedTime} onChange={e => setExpectedTime(Number(e.target.value))} className="w-full border border-gray-200 rounded-lg px-3 py-2" required />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Add to Collection (Optional)</label>
          {collections.length === 0 ? (
            <p className="text-sm text-gray-400">No collections yet — create one under Academic Management → Collections.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {collections.map(c => (
                <label
                  key={c.id}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm cursor-pointer ${
                    selectedCollectionIds.includes(c.id)
                      ? 'bg-[#0B2545] text-white border-[#0B2545]'
                      : 'bg-white text-gray-700 border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <input
                    type="checkbox"
                    className="hidden"
                    checked={selectedCollectionIds.includes(c.id)}
                    onChange={() => toggleCollection(c.id)}
                  />
                  {c.name}
                </label>
              ))}
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Tags (Optional)</label>
          <p className="text-xs text-gray-400 mb-2">Search &amp; filter metadata - separate from Collections.</p>
          {selectableTags.length === 0 ? (
            <p className="text-sm text-gray-400">No tags yet — create one under Academic Management → Tags.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {selectableTags.map(t => {
                const checked = selectedTagIds.includes(t.id);
                return (
                  <label
                    key={t.id}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm cursor-pointer transition-colors"
                    style={checked ? { backgroundColor: t.color, borderColor: t.color, color: '#fff' } : { borderColor: '#e5e7eb' }}
                  >
                    <input
                      type="checkbox"
                      className="hidden"
                      checked={checked}
                      onChange={() => toggleTag(t.id)}
                    />
                    {t.name}
                    {!t.is_active && <span className="text-[10px] opacity-70">(inactive)</span>}
                  </label>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Syllabus Selection */}
      <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm space-y-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-[#0B2545]" />
          Course &amp; Academic Scope Mapping
        </h2>
        <p className="text-sm text-gray-500 mb-2">
          Questions intended for student practice must map to an active Course. Select a Course to automatically configure the matching Exam/Position scope, or select the academic hierarchy manually.
        </p>

        <div className="p-4 bg-navy-50/50 border border-navy-100 rounded-lg space-y-2 mb-4">
          <label className="block text-sm font-semibold text-navy-950">
            Target Course (Recommended for Student Practice)
          </label>
          <select
            value={selCourse}
            onChange={(e) => handleCourseChange(e.target.value)}
            className="w-full p-2.5 border border-gray-200 bg-white rounded-lg focus:outline-none focus:ring-2 focus:ring-[#0B2545]/20 text-sm font-medium"
          >
            <option value="">Select Course (or choose Position manually below)</option>
            {courses.map(c => (
              <option key={c.id} value={String(c.id)}>
                {c.title} {c.exam?.title ? `(${c.exam.title})` : ''}
              </option>
            ))}
          </select>
          <p className="text-xs text-navy-700">
            Selecting a Course scopes academic selectors to its syllabus. Questions with approved status require a valid Course mapping to be served to enrolled students.
          </p>
        </div>
        
        <AcademicDependentSelect
          category={selCategory}
          position={selPosition}
          subject={selSubject}
          chapter={selChapter}
          topic={selTopic}
          onChange={handleAcademicChange}
          requiredLevels={['category', 'position']}
          maxLevel="topic"
          layout="grid"
        />
      </div>

      {/* Question Text */}
      <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm space-y-4">
        <label className="block text-sm font-medium text-gray-700">Question Content</label>
        <textarea 
          value={text} 
          onChange={e => setText(e.target.value)} 
          className="w-full border border-gray-200 rounded-lg px-3 py-2 min-h-[120px]" 
          placeholder="Type your question here..."
          required
        />
      </div>

      {/* Options */}
      <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Options</h2>
          <label className="flex items-center gap-2 cursor-pointer bg-amber-50 text-amber-700 px-3 py-1.5 rounded-lg border border-amber-200">
            <input 
              type="checkbox" 
              checked={aiGenerate}
              onChange={(e) => setAiGenerate(e.target.checked)}
              className="w-4 h-4 text-amber-600 rounded focus:ring-amber-500"
            />
            <span className="text-sm font-medium flex items-center gap-1"><Wand2 className="w-3.5 h-3.5" /> Auto-generate Options with AI</span>
          </label>
        </div>
        <div className="space-y-4">
          {(['A', 'B', 'C', 'D'] as const).map(opt => (
            <div key={opt} className="flex items-center gap-4">
              <input 
                type="radio" 
                name="correct" 
                checked={correctOption === opt}
                onChange={() => setCorrectOption(opt)}
                disabled={aiGenerate}
                className="w-5 h-5 text-[#0B2545] border-gray-300 focus:ring-[#0B2545] disabled:opacity-50"
              />
              <span className="font-bold text-gray-700 w-6">{opt}.</span>
              <input 
                type="text" 
                value={options[opt]}
                onChange={e => setOptions({...options, [opt]: e.target.value})}
                disabled={aiGenerate}
                className="flex-1 border border-gray-200 rounded-lg px-3 py-2 disabled:opacity-50 disabled:bg-gray-50"
                placeholder={aiGenerate ? `AI will generate Option ${opt}` : `Option ${opt}`}
                required={!aiGenerate}
              />
            </div>
          ))}
        </div>

        <div className="mt-6">
          <h2 className="text-lg font-semibold mb-2">Explanation (Optional)</h2>
          <textarea 
            value={explanation} 
            onChange={e => setExplanation(e.target.value)} 
            className="w-full border border-gray-200 rounded-lg px-3 py-2 min-h-[100px]" 
            placeholder="Provide a detailed explanation for the correct answer..."
          />
        </div>

        <div className="mt-6">
          <h2 className="text-lg font-semibold mb-2">Hint (Optional)</h2>
          <textarea
            value={hint}
            onChange={e => setHint(e.target.value)}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 min-h-[80px]"
            placeholder="A short hint to help the student answer..."
          />
        </div>
      </div>

      <div className="flex justify-end gap-4 pt-4 pb-12">
        <Button type="button" variant="outline" onClick={() => router.back()} disabled={loading}>
          Cancel
        </Button>
        <Button type="submit" disabled={loading} className="bg-[#0B2545] hover:bg-[#0B2545]/90 text-white flex items-center gap-2">
          <Save className="w-4 h-4" />
          {loading ? 'Saving...' : (initialData ? 'Update Question' : 'Save Question')}
        </Button>
      </div>
    </form>
  );
}
