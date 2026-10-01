'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { adminQuestionApi } from '@/lib/api/admin-questions';
import { Plus, Trash2, Copy, Trash, Save, Wand2, CheckCircle2, AlertCircle } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { AcademicDependentSelect } from '@/components/admin/syllabus/AcademicDependentSelect';

interface BulkRow {
  id: string;
  text: string;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  correct_option: string;
  explanation: string;
  errors: Record<string, string>;
  isAiPreview: boolean;
}

const generateId = () => Math.random().toString(36).substr(2, 9);

const emptyRow = (): BulkRow => ({
  id: generateId(),
  text: '',
  option_a: '',
  option_b: '',
  option_c: '',
  option_d: '',
  correct_option: '',
  explanation: '',
  errors: {},
  isAiPreview: false,
});

export function BulkQuestionEntry() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);

  // Global Defaults
  const [qType, setQType] = useState<'mcq'>('mcq'); // Bulk mostly for MCQ right now
  const [marks, setMarks] = useState(1);
  const [negativeMarks, setNegativeMarks] = useState(0);

  // AI Options
  const [genMissingOptions, setGenMissingOptions] = useState(false);
  const [genMissingExplanations, setGenMissingExplanations] = useState(false);

  // Syllabus Cascading
  const [selCategory, setSelCategory] = useState('');
  const [selPosition, setSelPosition] = useState('');
  const [selSubject, setSelSubject] = useState('');
  const [selChapter, setSelChapter] = useState('');
  const [selTopic, setSelTopic] = useState('');

  const handleAcademicChange = (field: string, value: any) => {
    if (field === 'category') {
      setSelCategory(value || '');
      setSelPosition('');
      setSelSubject('');
      setSelChapter('');
      setSelTopic('');
    } else if (field === 'position' || field === 'exam') {
      setSelPosition(value || '');
      setSelSubject('');
      setSelChapter('');
      setSelTopic('');
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

  // Grid Data
  const [rows, setRows] = useState<BulkRow[]>([emptyRow(), emptyRow(), emptyRow()]);

  // Grid Actions
  const addRow = () => setRows([...rows, emptyRow()]);
  const deleteRow = (id: string) => setRows(rows.filter(r => r.id !== id));
  const duplicateRow = (row: BulkRow) => setRows([...rows, { ...row, id: generateId(), errors: {}, isAiPreview: false }]);
  const clearAll = () => setRows([emptyRow(), emptyRow(), emptyRow()]);

  const updateRow = (id: string, field: keyof BulkRow, value: any) => {
    setRows(rows.map(r => r.id === id ? { ...r, [field]: value } : r));
  };

  // Paste Handler
  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    const clipboardData = e.clipboardData.getData('Text');
    if (!clipboardData) return;
    
    if (clipboardData.indexOf('\t') !== -1 || clipboardData.indexOf('\n') !== -1) {
      e.preventDefault();
      
      const pastedRows = clipboardData.split('\n').filter(r => r.trim());
      const newRows: BulkRow[] = [];
      
      for (const rowText of pastedRows) {
        const cols = rowText.split('\t');
        if (cols.length > 0) {
          const nr = emptyRow();
          nr.text = cols[0]?.trim() || '';
          nr.option_a = cols[1]?.trim() || '';
          nr.option_b = cols[2]?.trim() || '';
          nr.option_c = cols[3]?.trim() || '';
          nr.option_d = cols[4]?.trim() || '';
          nr.correct_option = cols[5]?.trim().toUpperCase() || '';
          nr.explanation = cols[6]?.trim() || '';
          newRows.push(nr);
        }
      }
      
      if (newRows.length > 0) {
        setRows(prev => {
          const filtered = prev.filter(r => r.text.trim() || r.option_a.trim());
          return [...filtered, ...newRows];
        });
        toast.success(`Pasted ${newRows.length} rows`);
      }
    }
  }, []);

  // Validation
  const validateRows = () => {
    let isValid = true;
    const validated = rows.map(r => {
      const errs: Record<string, string> = {};
      
      if (r.text.trim() || r.option_a.trim()) {
        if (!r.text.trim()) errs.text = 'Question text is required';
        if (!r.option_a.trim()) errs.option_a = 'Required';
        if (!r.option_b.trim()) errs.option_b = 'Required';
        if (!r.option_c.trim()) errs.option_c = 'Required';
        if (!r.option_d.trim()) errs.option_d = 'Required';
        if (!r.correct_option) errs.correct_option = 'Required';
        else if (!['A','B','C','D'].includes(r.correct_option)) errs.correct_option = 'Must be A, B, C, or D';
      }
      
      if (Object.keys(errs).length > 0) isValid = false;
      return { ...r, errors: errs };
    });
    
    setRows(validated);
    return isValid;
  };

  const handleValidateClick = () => {
    if (validateRows()) {
      toast.success('All rows are valid!');
    } else {
      toast.error('Found validation errors in some rows.');
    }
  };

  // AI Content Generation
  const handleAiGenerate = async () => {
    const rowsToGen = rows.filter(r => r.text.trim() && (
      (genMissingOptions && (!r.option_a || !r.option_b || !r.option_c || !r.option_d)) ||
      (genMissingExplanations && !r.explanation)
    ));

    if (rowsToGen.length === 0) {
      toast.error('No rows require AI generation based on current filters.');
      return;
    }

    setAiLoading(true);
    const toastId = toast.loading(`AI is generating content for ${rowsToGen.length} questions...`);

    try {
      const payload = {
        subject: 'General',
        generate_options: genMissingOptions,
        generate_explanations: genMissingExplanations,
        questions: rowsToGen.map(r => ({
          id: r.id,
          text: r.text,
          option_a: r.option_a,
          option_b: r.option_b,
          option_c: r.option_c,
          option_d: r.option_d,
          correct_option: r.correct_option,
          explanation: r.explanation
        }))
      };

      const res = await adminQuestionApi.generateBulkAIContent(payload);
      
      const newRows = [...rows];
      res.questions.forEach((aiRow: any) => {
        const idx = newRows.findIndex(r => r.id === aiRow.id);
        if (idx !== -1) {
          const oldRow = newRows[idx];
          if (oldRow) {
            newRows[idx] = {
              ...oldRow,
              option_a: aiRow.option_a || oldRow.option_a,
              option_b: aiRow.option_b || oldRow.option_b,
              option_c: aiRow.option_c || oldRow.option_c,
              option_d: aiRow.option_d || oldRow.option_d,
              correct_option: aiRow.correct_answer || aiRow.correct_option || oldRow.correct_option,
              explanation: aiRow.explanation || oldRow.explanation,
              isAiPreview: true,
              errors: {}
            };
          }
        }
      });
      
      setRows(newRows);
      toast.success('AI generation complete!', { id: toastId });
    } catch (err: any) {
      toast.error('AI generation failed.', { id: toastId });
    } finally {
      setAiLoading(false);
    }
  };

  const handleSaveAll = async () => {
    if (!selCategory || !selPosition) {
      toast.error('Please select Category and Position/Level.');
      return;
    }

    if (!validateRows()) {
      toast.error('Please fix validation errors before saving.');
      return;
    }

    const validRows = rows.filter(r => r.text.trim() && Object.keys(r.errors).length === 0);
    
    if (validRows.length === 0) {
      toast.error('No valid rows to save.');
      return;
    }

    setLoading(true);
    const toastId = toast.loading(`Saving ${validRows.length} questions...`);

    try {
      const payload = validRows.map(r => ({
        question_type: qType,
        status: 'published',
        category: Number(selCategory),
        position: Number(selPosition),
        subject: selSubject ? Number(selSubject) : undefined,
        chapter: selChapter ? Number(selChapter) : null,
        topic: selTopic ? Number(selTopic) : null,
        marks: Number(marks),
        negative_marks: Number(negativeMarks),
        expected_time_minutes: 1,
        text: r.text,
        option_a: r.option_a,
        option_b: r.option_b,
        option_c: r.option_c,
        option_d: r.option_d,
        correct_option: r.correct_option as 'A'|'B'|'C'|'D',
        explanation: r.explanation,
        ai_status: r.isAiPreview ? 'approved' : undefined,
      }));

      await adminQuestionApi.bulkCreateQuestions(payload);
      toast.success(`Successfully saved ${validRows.length} questions!`, { id: toastId });
      router.push('/admin-dashboard/academic/questions');
    } catch (error: any) {
      toast.error(error.response?.data?.error || 'Failed to bulk save questions', { id: toastId });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-[100vw] overflow-hidden">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8 bg-white p-5 rounded-xl border border-gray-200 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-800 mb-3 uppercase tracking-wider">1. Global Syllabus Mapping</h2>
          <div className="-mx-3 scale-[0.85] origin-top-left md:scale-100 md:mx-0">
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
        </div>

        <div className="lg:col-span-4 bg-white p-5 rounded-xl border border-gray-200 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-800 mb-3 uppercase tracking-wider">2. Global Settings</h2>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10px] font-medium text-gray-500 uppercase">Marks</label>
              <input type="number" step="0.5" value={marks} onChange={e => setMarks(Number(e.target.value))} className="mt-1 w-full border border-gray-200 rounded px-2 py-1 text-xs" />
            </div>
            <div>
              <label className="block text-[10px] font-medium text-gray-500 uppercase">Negative Marks</label>
              <input type="number" step="0.1" value={negativeMarks} onChange={e => setNegativeMarks(Number(e.target.value))} className="mt-1 w-full border border-gray-200 rounded px-2 py-1 text-xs" />
            </div>
          </div>
        </div>
      </div>

      {/* AI Toggles */}
      <div className="bg-amber-50/50 border border-amber-100 p-4 rounded-xl flex flex-wrap gap-6 items-center">
        <div className="flex items-center gap-2">
          <Wand2 className="w-5 h-5 text-amber-500" />
          <span className="font-semibold text-amber-900 text-sm">AI Assist</span>
        </div>
        <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-700">
          <input type="checkbox" checked={genMissingOptions} onChange={e => setGenMissingOptions(e.target.checked)} className="w-4 h-4 text-amber-600 rounded border-gray-300 focus:ring-amber-500" />
          Generate Missing Options
        </label>
        <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-700">
          <input type="checkbox" checked={genMissingExplanations} onChange={e => setGenMissingExplanations(e.target.checked)} className="w-4 h-4 text-amber-600 rounded border-gray-300 focus:ring-amber-500" />
          Generate Missing Explanations
        </label>
        
        <button 
          type="button"
          onClick={handleAiGenerate}
          disabled={aiLoading || (!genMissingOptions && !genMissingExplanations)}
          className="ml-auto bg-amber-500 hover:bg-amber-600 text-white px-4 py-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
        >
          {aiLoading ? 'Generating...' : 'Generate AI Content'}
        </button>
      </div>

      {/* Spreadsheet Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col" onPaste={handlePaste}>
        <div className="overflow-x-auto min-h-[400px]">
          <table className="w-full text-left border-collapse text-sm min-w-[1200px]">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="p-2 w-12 text-center text-gray-500 font-medium border-r border-gray-200">#</th>
                <th className="p-2 min-w-[250px] font-medium text-gray-700 border-r border-gray-200">Question Text *</th>
                <th className="p-2 min-w-[120px] font-medium text-gray-700 border-r border-gray-200">Option A *</th>
                <th className="p-2 min-w-[120px] font-medium text-gray-700 border-r border-gray-200">Option B *</th>
                <th className="p-2 min-w-[120px] font-medium text-gray-700 border-r border-gray-200">Option C *</th>
                <th className="p-2 min-w-[120px] font-medium text-gray-700 border-r border-gray-200">Option D *</th>
                <th className="p-2 w-[100px] font-medium text-gray-700 border-r border-gray-200">Ans *</th>
                <th className="p-2 min-w-[200px] font-medium text-gray-700 border-r border-gray-200">Explanation</th>
                <th className="p-2 w-[80px] font-medium text-gray-700 text-center">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {rows.map((row, idx) => (
                <tr key={row.id} className={`hover:bg-gray-50 transition-colors ${row.isAiPreview ? 'bg-amber-50/30' : ''}`}>
                  <td className="p-2 text-center text-gray-400 font-mono text-xs border-r border-gray-200 align-top">
                    {idx + 1}
                  </td>
                  <td className="p-0 border-r border-gray-200 align-top">
                    <textarea 
                      value={row.text} 
                      onChange={e => updateRow(row.id, 'text', e.target.value)}
                      className={`w-full h-full min-h-[60px] p-2 resize-y focus:outline-none focus:ring-1 focus:ring-navy-500 ${row.errors.text ? 'bg-red-50 focus:ring-red-500' : 'bg-transparent'}`}
                      placeholder="Question..."
                    />
                  </td>
                  <td className="p-0 border-r border-gray-200 align-top">
                    <textarea 
                      value={row.option_a} 
                      onChange={e => updateRow(row.id, 'option_a', e.target.value)}
                      className={`w-full h-full min-h-[60px] p-2 resize-y focus:outline-none focus:ring-1 focus:ring-navy-500 ${row.errors.option_a ? 'bg-red-50 focus:ring-red-500' : 'bg-transparent'} ${row.isAiPreview ? 'text-amber-900' : ''}`}
                    />
                  </td>
                  <td className="p-0 border-r border-gray-200 align-top">
                    <textarea 
                      value={row.option_b} 
                      onChange={e => updateRow(row.id, 'option_b', e.target.value)}
                      className={`w-full h-full min-h-[60px] p-2 resize-y focus:outline-none focus:ring-1 focus:ring-navy-500 ${row.errors.option_b ? 'bg-red-50 focus:ring-red-500' : 'bg-transparent'} ${row.isAiPreview ? 'text-amber-900' : ''}`}
                    />
                  </td>
                  <td className="p-0 border-r border-gray-200 align-top">
                    <textarea 
                      value={row.option_c} 
                      onChange={e => updateRow(row.id, 'option_c', e.target.value)}
                      className={`w-full h-full min-h-[60px] p-2 resize-y focus:outline-none focus:ring-1 focus:ring-navy-500 ${row.errors.option_c ? 'bg-red-50 focus:ring-red-500' : 'bg-transparent'} ${row.isAiPreview ? 'text-amber-900' : ''}`}
                    />
                  </td>
                  <td className="p-0 border-r border-gray-200 align-top">
                    <textarea 
                      value={row.option_d} 
                      onChange={e => updateRow(row.id, 'option_d', e.target.value)}
                      className={`w-full h-full min-h-[60px] p-2 resize-y focus:outline-none focus:ring-1 focus:ring-navy-500 ${row.errors.option_d ? 'bg-red-50 focus:ring-red-500' : 'bg-transparent'} ${row.isAiPreview ? 'text-amber-900' : ''}`}
                    />
                  </td>
                  <td className="p-0 border-r border-gray-200 align-top">
                    <input 
                      type="text" 
                      value={row.correct_option} 
                      onChange={e => updateRow(row.id, 'correct_option', e.target.value.toUpperCase())}
                      maxLength={1}
                      className={`w-full h-full min-h-[60px] p-2 text-center uppercase font-bold focus:outline-none focus:ring-1 focus:ring-navy-500 ${row.errors.correct_option ? 'bg-red-50 focus:ring-red-500' : 'bg-transparent'} ${row.isAiPreview ? 'text-amber-900' : ''}`}
                      placeholder="A/B/C/D"
                    />
                  </td>
                  <td className="p-0 border-r border-gray-200 align-top">
                    <textarea 
                      value={row.explanation} 
                      onChange={e => updateRow(row.id, 'explanation', e.target.value)}
                      className={`w-full h-full min-h-[60px] p-2 resize-y focus:outline-none focus:ring-1 focus:ring-navy-500 bg-transparent ${row.isAiPreview ? 'text-amber-900' : ''}`}
                    />
                  </td>
                  <td className="p-2 align-top text-center space-y-2">
                    <div className="flex justify-center gap-2">
                      <button type="button" onClick={() => duplicateRow(row)} className="p-1 text-gray-400 hover:text-navy-600 hover:bg-navy-50 rounded" title="Duplicate Row">
                        <Copy className="w-4 h-4" />
                      </button>
                      <button type="button" onClick={() => deleteRow(row.id)} className="p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded" title="Delete Row">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                    {Object.keys(row.errors).length > 0 && (
                       <div className="flex justify-center" title={Object.values(row.errors).join(', ')}>
                         <AlertCircle className="w-4 h-4 text-red-500" />
                       </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        
        {/* Table Footer Actions */}
        <div className="bg-gray-50 border-t border-gray-200 p-3 flex items-center justify-between">
          <div className="flex gap-2">
            <button type="button" onClick={addRow} className="flex items-center gap-1 text-sm font-medium text-navy-600 hover:text-navy-700 hover:bg-navy-50 px-3 py-1.5 rounded-lg transition-colors">
              <Plus className="w-4 h-4" /> Add Row
            </button>
            <button type="button" onClick={clearAll} className="flex items-center gap-1 text-sm font-medium text-gray-500 hover:text-red-600 hover:bg-red-50 px-3 py-1.5 rounded-lg transition-colors">
              <Trash className="w-4 h-4" /> Clear All
            </button>
          </div>
          <p className="text-xs text-gray-500">
            Tip: You can paste data directly from Excel or Google Sheets.
          </p>
        </div>
      </div>

      {/* Main Actions */}
      <div className="flex justify-end gap-4 pt-4 pb-12">
        <button 
          type="button" 
          onClick={handleValidateClick}
          className="border border-gray-300 bg-white hover:bg-gray-50 text-gray-700 px-6 py-3 rounded-xl font-medium flex items-center gap-2 transition-colors"
        >
          <CheckCircle2 className="w-5 h-5" />
          Validate Questions
        </button>
        <button 
          type="button" 
          onClick={handleSaveAll}
          disabled={loading}
          className="bg-navy-600 hover:bg-navy-700 text-white px-8 py-3 rounded-xl font-medium flex items-center gap-2 transition-colors disabled:opacity-70"
        >
          {loading ? 'Saving...' : (
            <>
              <Save className="w-5 h-5" />
              Save All Valid Questions
            </>
          )}
        </button>
      </div>

    </div>
  );
}
