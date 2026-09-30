"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Loader2, PlusCircle, Search, Shuffle, Trash2, X, AlertTriangle,
  ChevronLeft, ChevronRight, Filter, ArrowUp, ArrowDown,
} from "lucide-react";
import {
  adminExamApi, AssignedQuestion, BankQuestion, GenerateQuestionsResult,
  PaginatedBank, QuestionAvailability,
} from "@/lib/api/admin-exams";
import { adminSyllabusApi } from "@/lib/api/admin-syllabus";
import { adminCollectionsApi, QuestionCollection } from "@/lib/api/admin-collections";
import toast from "react-hot-toast";

interface Props {
  examinationId: number;
  /** The exam's own academic targeting, used as the default bank scope. */
  defaultSubjectId?: number | null;
  /** Locks the question bank to the configured Topicwise Test topic. */
  defaultTopicId?: number | null;
  /** Pre-selects a QuestionCollection as the bank source - set when arriving
   *  here via "Use in Mock Exam" from the admin Collections page. */
  defaultCollectionId?: number | null;
  onSelectionChange?: (count: number, totalMarks: number) => void;
}

const DIFFICULTY_TONE: Record<string, string> = {
  easy: "text-emerald-700 bg-emerald-50 border-emerald-200",
  medium: "text-amber-700 bg-amber-50 border-amber-200",
  hard: "text-red-700 bg-red-50 border-red-200",
};

export function QuestionSelectionWorkspace({
  examinationId, defaultSubjectId, defaultTopicId, defaultCollectionId, onSelectionChange,
}: Props) {
  // Bank (left)
  const [bank, setBank] = useState<PaginatedBank | null>(null);
  const [bankLoading, setBankLoading] = useState(true);
  const [bankError, setBankError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  // Filters
  const [showFilters, setShowFilters] = useState(false);
  const [subjectId, setSubjectId] = useState<number | undefined>(defaultSubjectId ?? undefined);
  const [chapterId, setChapterId] = useState<number | undefined>();
  const [topicId, setTopicId] = useState<number | undefined>(defaultTopicId ?? undefined);
  const [questionType, setQuestionType] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [subjects, setSubjects] = useState<any[]>([]);
  const [chapters, setChapters] = useState<any[]>([]);
  const [topics, setTopics] = useState<any[]>([]);
  const [collectionId, setCollectionId] = useState<number | undefined>(defaultCollectionId ?? undefined);
  const [collections, setCollections] = useState<QuestionCollection[]>([]);
  useEffect(() => {
    adminCollectionsApi.getCollections().then(setCollections).catch(() => setCollections([]));
  }, []);

  // Assigned (right)
  const [assigned, setAssigned] = useState<AssignedQuestion[]>([]);
  const [assignedMarks, setAssignedMarks] = useState(0);
  const [assignedLoading, setAssignedLoading] = useState(true);

  // Availability summary
  const [availability, setAvailability] = useState<QuestionAvailability | null>(null);

  // Random generation
  const [randomMode, setRandomMode] = useState(false);
  const [randomCount, setRandomCount] = useState(10);
  const [useDistribution, setUseDistribution] = useState(false);
  const [dist, setDist] = useState({ easy: 0, medium: 0, hard: 0 });
  const [previewResult, setPreviewResult] = useState<GenerateQuestionsResult | null>(null);
  const [generating, setGenerating] = useState(false);
  const [replaceMode, setReplaceMode] = useState(false);

  const [busyIds, setBusyIds] = useState<Set<number>>(new Set());

  // Guards against a slow earlier bank fetch overwriting a newer one.
  const bankRequestId = useRef(0);

  const scopeParams = useCallback(() => ({
    subject: subjectId,
    chapter: chapterId,
    topic: topicId,
    question_type: questionType || undefined,
    collection: collectionId,
  }), [subjectId, chapterId, topicId, questionType, collectionId]);

  // ── Debounce search so typing doesn't hammer the API ──────────────────────
  useEffect(() => {
    const id = setTimeout(() => { setDebouncedSearch(search); setPage(1); }, 350);
    return () => clearTimeout(id);
  }, [search]);

  const loadBank = useCallback(async () => {
    const reqId = ++bankRequestId.current;
    setBankLoading(true);
    setBankError(null);
    try {
      const res = await adminExamApi.getAvailableQuestions(examinationId, {
        ...scopeParams(),
        search: debouncedSearch || undefined,
        difficulty: difficulty || undefined,
        page,
        page_size: 10,
      });
      if (reqId !== bankRequestId.current) return;
      setBank(res);
    } catch (error: any) {
      if (reqId !== bankRequestId.current) return;
      setBankError(
        error?.status === 403
          ? "You don't have permission to manage examinations."
          : "Unable to load the Master Question Bank."
      );
    } finally {
      if (reqId === bankRequestId.current) setBankLoading(false);
    }
  }, [examinationId, scopeParams, debouncedSearch, difficulty, page]);

  const loadAvailability = useCallback(async () => {
    try {
      setAvailability(await adminExamApi.getQuestionAvailability(examinationId, scopeParams()));
    } catch {
      setAvailability(null);
    }
  }, [examinationId, scopeParams]);

  const loadAssigned = useCallback(async () => {
    setAssignedLoading(true);
    try {
      const res = await adminExamApi.getExamQuestions(examinationId);
      setAssigned(res.results);
      setAssignedMarks(res.total_marks);
      onSelectionChange?.(res.count, res.total_marks);
    } catch {
      toast.error("Unable to load the exam's questions.");
    } finally {
      setAssignedLoading(false);
    }
  }, [examinationId, onSelectionChange]);

  useEffect(() => { loadBank(); }, [loadBank]);
  useEffect(() => { loadAvailability(); }, [loadAvailability, assigned.length]);
  useEffect(() => { loadAssigned();   }, [examinationId]);

  // ── Filter dropdown data, from the canonical academic hierarchy ───────────
  useEffect(() => {
    adminSyllabusApi.getSubjects().then(r => setSubjects(Array.isArray(r) ? r : [])).catch(() => {});
  }, []);
  useEffect(() => {
    setChapters([]); setTopics([]);
    if (!subjectId) return;
    adminSyllabusApi.getChapters(subjectId).then(r => setChapters(Array.isArray(r) ? r : [])).catch(() => {});
  }, [subjectId]);
  useEffect(() => {
    setTopics([]);
    if (!chapterId) return;
    adminSyllabusApi.getTopics(chapterId).then(r => setTopics(Array.isArray(r) ? r : [])).catch(() => {});
  }, [chapterId]);

  useEffect(() => {
    if (!defaultTopicId) return;
    adminSyllabusApi.getTopic(defaultTopicId)
      .then(topic => { if (topic.chapter) setChapterId(topic.chapter); })
      .catch(() => toast.error("Could not load the selected topic."));
  }, [defaultTopicId]);

  const withBusy = async (id: number, fn: () => Promise<void>) => {
    setBusyIds(prev => new Set(prev).add(id));
    try { await fn(); } finally {
      setBusyIds(prev => { const n = new Set(prev); n.delete(id); return n; });
    }
  };

  const addQuestion = (q: BankQuestion) => withBusy(q.id, async () => {
    try {
      const res = await adminExamApi.addQuestions(examinationId, [q.id]);
      if (res.added_count === 0) {
        toast.error(
          res.not_approved_or_missing.length
            ? "That question is not approved, so it can't be added."
            : "That question is already on this exam."
        );
        return;
      }
      await Promise.all([loadAssigned(), loadBank()]);
    } catch (error: any) {
      toast.error(error?.data?.error || "Could not add the question.");
    }
  });

  const removeQuestion = (q: AssignedQuestion) => withBusy(q.id, async () => {
    try {
      await adminExamApi.removeQuestions(examinationId, [q.id]);
      await Promise.all([loadAssigned(), loadBank()]);
    } catch (error: any) {
      toast.error(error?.data?.error || "Could not remove the question.");
    }
  });

  const removeAll = async () => {
    if (assigned.length === 0) return;
    if (!confirm(
      `Remove all ${assigned.length} question(s) from this exam?\n\n` +
      `They stay in the Master Question Bank — only their link to this exam is removed.`
    )) return;
    try {
      await adminExamApi.removeQuestions(examinationId, assigned.map(q => q.id));
      toast.success("All questions removed from this exam");
      await Promise.all([loadAssigned(), loadBank()]);
    } catch {
      toast.error("Could not clear the exam's questions.");
    }
  };

  const move = async (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= assigned.length) return;
    const next = [...assigned];
    const moved = next[index];
    const displaced = next[target];
    if (!moved || !displaced) return;
    next[index] = displaced;
    next[target] = moved;
    setAssigned(next); // optimistic, corrected by the reload below
    try {
      await adminExamApi.reorderQuestions(
        examinationId,
        next.map((q, i) => ({ question_id: q.id, order: i + 1 }))
      );
      loadAssigned();
    } catch {
      toast.error("Could not save the new order.");
      loadAssigned();
    }
  };

  const buildGeneratePayload = (extra: Record<string, any> = {}) => ({
    ...scopeParams(),
    ...(useDistribution
      ? { difficulty_distribution: dist }
      : { count: randomCount }),
    ...extra,
  });

  const runPreview = async (replace: boolean) => {
    setReplaceMode(replace);
    setGenerating(true);
    try {
      const res = await adminExamApi.generateQuestions(
        examinationId, buildGeneratePayload({ preview: true, replace })
      );
      setPreviewResult(res);
    } catch (error: any) {
      // A 409 carries the shortfall detail, which is exactly what to show.
      const data = error?.data;
      if (data?.warnings) setPreviewResult({ ...data, preview: true });
      else toast.error(data?.error || "Could not check availability.");
    } finally {
      setGenerating(false);
    }
  };

  const commitGeneration = async () => {
    setGenerating(true);
    try {
      const res = await adminExamApi.generateQuestions(
        examinationId, buildGeneratePayload({ replace: replaceMode })
      );
      toast.success(`${res.selected} question(s) selected · ${res.total_marks} marks`);
      setPreviewResult(null);
      await Promise.all([loadAssigned(), loadBank()]);
    } catch (error: any) {
      const data = error?.data;
      toast.error(data?.error || "Generation failed.");
      if (data?.warnings) setPreviewResult({ ...data, preview: true });
    } finally {
      setGenerating(false);
    }
  };

  const distTotal = dist.easy + dist.medium + dist.hard;

  return (
    <div className="flex flex-col gap-4">
      {/* ── Question Collections summary ──────────────────────────────────── */}
      <div className="bg-white border border-slate-200 rounded-xl p-4">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h3 className="font-bold text-[#0B2545]">Question Collections</h3>
          <span className="text-xs text-slate-500">
            Live counts from the approved Master Question Bank
          </span>
        </div>
        {!availability ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading availability...
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {[
              { label: "Total Available", value: availability.total_available, tone: "text-[#0B2545]" },
              { label: "Easy", value: availability.by_difficulty.easy, tone: "text-emerald-600" },
              { label: "Medium", value: availability.by_difficulty.medium, tone: "text-amber-600" },
              { label: "Hard", value: availability.by_difficulty.hard, tone: "text-red-600" },
              { label: "Selected", value: availability.selected, tone: "text-blue-600" },
              { label: "MCQ", value: availability.by_type.mcq, tone: "text-slate-700" },
            ].map(stat => (
              <div key={stat.label} className="border border-slate-100 rounded-lg p-2.5 bg-slate-50/60">
                <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wide">{stat.label}</p>
                <p className={`text-xl font-bold mt-0.5 ${stat.tone}`}>{stat.value}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Random selection ──────────────────────────────────────────────── */}
      <div className="bg-blue-50/50 border border-blue-200 rounded-xl p-4">
        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={randomMode}
            onChange={(e) => { setRandomMode(e.target.checked); setPreviewResult(null); }}
            className="mt-0.5 w-4 h-4 rounded text-[#0B2545]"
          />
          <span>
            <span className="block text-sm font-semibold text-slate-900">Choose Questions Randomly</span>
            <span className="block text-xs text-slate-600 mt-0.5">
              The server picks approved questions matching this exam&rsquo;s configuration.
            </span>
          </span>
        </label>

        {randomMode && (
          <div className="mt-4 pl-7 space-y-3">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={useDistribution}
                onChange={(e) => setUseDistribution(e.target.checked)}
                className="w-4 h-4 rounded text-[#0B2545]"
              />
              Set a difficulty split
            </label>

            {useDistribution ? (
              <div className="flex flex-wrap items-end gap-3">
                {(["easy", "medium", "hard"] as const).map(level => (
                  <div key={level}>
                    <label className="block text-xs font-medium text-slate-600 mb-1 capitalize">{level}</label>
                    <input
                      type="number" min={0}
                      value={dist[level]}
                      onChange={(e) => setDist({ ...dist, [level]: Math.max(0, Number(e.target.value) || 0) })}
                      className="w-24 px-2 py-1.5 border border-slate-200 rounded-lg text-sm bg-white text-slate-900"
                    />
                    {availability && (
                      <p className="text-[11px] text-slate-500 mt-1">
                        {availability.by_difficulty[level]} available
                      </p>
                    )}
                  </div>
                ))}
                <p className="text-sm text-slate-600 pb-1.5">Total: <strong>{distTotal}</strong></p>
              </div>
            ) : (
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Number of Questions</label>
                <input
                  type="number" min={1}
                  value={randomCount}
                  onChange={(e) => setRandomCount(Math.max(1, Number(e.target.value) || 1))}
                  className="w-32 px-2 py-1.5 border border-slate-200 rounded-lg text-sm bg-white text-slate-900"
                />
              </div>
            )}

            <div className="flex flex-wrap gap-2 pt-1">
              <button
                onClick={() => runPreview(false)}
                disabled={generating || (useDistribution ? distTotal < 1 : randomCount < 1)}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm rounded-lg font-medium flex items-center gap-2"
              >
                {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shuffle className="w-4 h-4" />}
                Generate Random Questions
              </button>
              {assigned.length > 0 && (
                <button
                  onClick={() => runPreview(true)}
                  disabled={generating}
                  className="px-4 py-2 border border-blue-300 text-blue-700 hover:bg-blue-100 disabled:opacity-50 text-sm rounded-lg font-medium"
                >
                  Regenerate (replace current)
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── Generation preview / shortfall ────────────────────────────────── */}
      {previewResult && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6 space-y-4">
            <div className="flex justify-between items-start">
              <h3 className="text-lg font-bold text-[#0B2545]">
                {previewResult.satisfied ? "Generate Random Questions?" : "Not enough questions"}
              </h3>
              <button onClick={() => setPreviewResult(null)} className="p-1.5 hover:bg-slate-100 rounded">
                <X className="w-4 h-4 text-slate-500" />
              </button>
            </div>

            {previewResult.satisfied ? (
              <>
                <p className="text-sm text-slate-600">
                  <strong>{previewResult.selected}</strong> question(s) will be selected from the
                  approved Master Question Bank
                  {replaceMode && ", replacing the current selection"}.
                </p>
                {useDistribution && (
                  <ul className="text-sm text-slate-600 list-disc list-inside">
                    <li>Easy: {dist.easy}</li>
                    <li>Medium: {dist.medium}</li>
                    <li>Hard: {dist.hard}</li>
                  </ul>
                )}
                {replaceMode && (
                  <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                    This replaces every question currently on the exam, including any you added by hand.
                  </p>
                )}
              </>
            ) : (
              <div className="space-y-2">
                <p className="text-sm text-slate-600">
                  Requested <strong>{previewResult.requested}</strong>, but only{" "}
                  <strong>{previewResult.selected}</strong> could be drawn.
                </p>
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 space-y-1">
                  {previewResult.warnings.map((w, i) => (
                    <p key={i} className="text-sm text-red-700 flex gap-2">
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" /> {w}
                    </p>
                  ))}
                </div>
                <p className="text-sm text-slate-600">
                  Reduce the count, adjust the difficulty split, widen the academic scope, or add
                  the remaining questions by hand.
                </p>
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setPreviewResult(null)}
                className="flex-1 py-2.5 border border-slate-200 rounded-lg font-medium text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              {previewResult.satisfied && (
                <button
                  onClick={commitGeneration}
                  disabled={generating}
                  className="flex-1 py-2.5 bg-[#0B2545] hover:bg-[#163E6C] disabled:opacity-50 text-white rounded-lg font-medium flex items-center justify-center gap-2"
                >
                  {generating && <Loader2 className="w-4 h-4 animate-spin" />}
                  {replaceMode ? "Regenerate" : "Generate Questions"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Two-column workspace ──────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* LEFT: Master Question Bank */}
        <div className="bg-white border border-slate-200 rounded-xl flex flex-col min-h-[520px]">
          <div className="p-4 border-b border-slate-200">
            <div className="flex items-center justify-between gap-2">
              <h3 className="font-bold text-[#0B2545]">Available Questions</h3>
              {bank && <span className="text-xs text-slate-500">{bank.count} in scope</span>}
            </div>
            <div className="flex items-center gap-2 mt-3">
              {collections.length > 0 && (
                <select
                  value={collectionId ?? ""}
                  onChange={(e) => { setCollectionId(e.target.value ? Number(e.target.value) : undefined); setPage(1); }}
                  className="px-2.5 py-2 border border-slate-200 rounded-lg text-sm bg-white text-slate-900 shrink-0"
                  title="Restrict the bank to one Collection"
                >
                  <option value="">Master Question Bank</option>
                  {collections.map(c => (
                    <option key={c.id} value={c.id}>Collection: {c.name}</option>
                  ))}
                </select>
              )}
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search text, subject, chapter, topic..."
                  className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm bg-white text-slate-900 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-[#0B2545]/20"
                />
              </div>
              <button
                onClick={() => setShowFilters(v => !v)}
                className={`p-2 border rounded-lg shrink-0 ${
                  showFilters ? "border-[#0B2545] bg-slate-50" : "border-slate-200 hover:bg-slate-50"
                }`}
                aria-label="Toggle filters"
              >
                <Filter className="w-4 h-4 text-slate-600" />
              </button>
            </div>

            {showFilters && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-3">
                <select
                  value={subjectId ?? ""}
                  onChange={(e) => { setSubjectId(e.target.value ? Number(e.target.value) : undefined); setChapterId(undefined); setTopicId(undefined); setPage(1); }}
                  disabled={!!defaultTopicId}
                  className="px-2.5 py-2 border border-slate-200 rounded-lg text-sm bg-white text-slate-900"
                >
                  <option value="">All subjects</option>
                  {subjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <select
                  value={chapterId ?? ""}
                  onChange={(e) => { setChapterId(e.target.value ? Number(e.target.value) : undefined); setTopicId(undefined); setPage(1); }}
                  disabled={!subjectId || !!defaultTopicId}
                  className="px-2.5 py-2 border border-slate-200 rounded-lg text-sm bg-white text-slate-900 disabled:bg-slate-50"
                >
                  <option value="">All chapters</option>
                  {chapters.map(c => <option key={c.id} value={c.id}>{c.title || c.name}</option>)}
                </select>
                <select
                  value={topicId ?? ""}
                  onChange={(e) => { setTopicId(e.target.value ? Number(e.target.value) : undefined); setPage(1); }}
                  disabled={!chapterId || !!defaultTopicId}
                  className="px-2.5 py-2 border border-slate-200 rounded-lg text-sm bg-white text-slate-900 disabled:bg-slate-50"
                >
                  <option value="">All topics</option>
                  {topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
                <select
                  value={difficulty}
                  onChange={(e) => { setDifficulty(e.target.value); setPage(1); }}
                  className="px-2.5 py-2 border border-slate-200 rounded-lg text-sm bg-white text-slate-900"
                >
                  <option value="">All difficulties</option>
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
                <select
                  value={questionType}
                  onChange={(e) => { setQuestionType(e.target.value); setPage(1); }}
                  className="px-2.5 py-2 border border-slate-200 rounded-lg text-sm bg-white text-slate-900 sm:col-span-2"
                >
                  <option value="">All question types</option>
                  <option value="mcq">MCQ</option>
                  <option value="true_false">True / False</option>
                  <option value="subjective">Subjective</option>
                </select>
              </div>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {bankLoading ? (
              <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-[#0B2545]" /></div>
            ) : bankError ? (
              <p className="text-center text-red-600 py-12 text-sm">{bankError}</p>
            ) : !bank || bank.results.length === 0 ? (
              <div className="text-center py-12">
                <p className="text-sm font-medium text-slate-700">
                  No approved questions are available for this configuration.
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Widen the filters, or add approved questions to the Master Question Bank.
                </p>
              </div>
            ) : (
              bank.results.map(q => (
                <div key={q.id} className="border border-slate-200 rounded-lg p-3 hover:border-blue-300 transition-colors">
                  <div className="flex justify-between items-start gap-2 mb-2">
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700 uppercase">
                      {q.question_type}
                    </span>
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded border capitalize ${DIFFICULTY_TONE[q.difficulty] || "text-slate-600 bg-slate-50 border-slate-200"}`}>
                      {q.difficulty}
                    </span>
                  </div>
                  <p className="text-sm font-medium text-slate-800 line-clamp-3">{q.text}</p>
                  <p className="text-xs text-slate-500 mt-2">
                    {[q.subject_name, q.chapter_name, q.topic_name].filter(Boolean).join(" • ") || "Unclassified"}
                  </p>
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-[11px] text-slate-400">{q.question_id} · {q.marks} mark(s)</span>
                  </div>
                  <button
                    onClick={() => addQuestion(q)}
                    disabled={busyIds.has(q.id)}
                    className="w-full mt-3 py-1.5 text-xs font-medium text-blue-700 border border-blue-200 bg-blue-50 hover:bg-blue-100 disabled:opacity-50 rounded-lg flex items-center justify-center gap-1"
                  >
                    {busyIds.has(q.id) ? <Loader2 className="w-3 h-3 animate-spin" /> : <PlusCircle className="w-3 h-3" />}
                    Add to Exam
                  </button>
                </div>
              ))
            )}
          </div>

          {bank && bank.total_pages > 1 && (
            <div className="p-3 border-t border-slate-200 flex items-center justify-between">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={!bank.has_previous}
                className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg disabled:opacity-40 flex items-center gap-1"
              >
                <ChevronLeft className="w-4 h-4" /> Prev
              </button>
              <span className="text-xs text-slate-500">Page {bank.page} of {bank.total_pages}</span>
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={!bank.has_next}
                className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg disabled:opacity-40 flex items-center gap-1"
              >
                Next <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>

        {/* RIGHT: Exam Questions */}
        <div className="bg-white border border-slate-200 rounded-xl flex flex-col min-h-[520px]">
          <div className="p-4 border-b border-slate-200 flex flex-wrap justify-between items-center gap-2">
            <div>
              <h3 className="font-bold text-[#0B2545]">Exam Questions</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                {assigned.length} selected · {assignedMarks} total marks
              </p>
            </div>
            {assigned.length > 0 && (
              <button
                onClick={removeAll}
                className="px-3 py-1.5 text-xs border border-red-200 text-red-600 hover:bg-red-50 rounded-lg"
              >
                Remove all
              </button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {assignedLoading ? (
              <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-[#0B2545]" /></div>
            ) : assigned.length === 0 ? (
              <div className="text-center py-12">
                <p className="text-sm font-medium text-slate-700">No questions on this exam yet.</p>
                <p className="text-xs text-slate-500 mt-1">
                  Add them from the bank, or tick &ldquo;Choose Questions Randomly&rdquo; above.
                </p>
              </div>
            ) : (
              assigned.map((q, i) => (
                <div key={q.id} className="border border-slate-200 rounded-lg p-3 bg-slate-50/50">
                  <div className="flex items-start gap-2">
                    <span className="w-6 h-6 rounded bg-[#0B2545] text-white text-xs font-bold flex items-center justify-center shrink-0">
                      {i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-800 line-clamp-2">{q.text}</p>
                      <p className="text-xs text-slate-500 mt-1">
                        {[q.subject_name, q.topic_name].filter(Boolean).join(" • ")} · {q.exam_marks} mark(s)
                      </p>
                    </div>
                    <div className="flex flex-col gap-1 shrink-0">
                      <button onClick={() => move(i, -1)} disabled={i === 0}
                        className="p-1 text-slate-400 hover:text-slate-700 disabled:opacity-30" aria-label="Move up">
                        <ArrowUp className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => move(i, 1)} disabled={i === assigned.length - 1}
                        className="p-1 text-slate-400 hover:text-slate-700 disabled:opacity-30" aria-label="Move down">
                        <ArrowDown className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    <button
                      onClick={() => removeQuestion(q)}
                      disabled={busyIds.has(q.id)}
                      className="p-1.5 text-slate-400 hover:text-red-500 disabled:opacity-40 shrink-0"
                      aria-label="Remove from exam"
                    >
                      {busyIds.has(q.id) ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
