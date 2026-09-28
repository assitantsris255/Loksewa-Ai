// @ts-nocheck
"use client";

import React, { useState, useEffect } from "react";
import { Search, SlidersHorizontal, ArrowRight, Download, Eye, FileText, CheckCircle2, Target, BrainCircuit, Activity, BookOpen, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { publicApi, type PublicSyllabusCategory, type PublicSyllabusExam } from "@/lib/api/public-api";
import { downloadPublicFile } from "@/lib/api/client";
import { toast } from "sonner";

export default function SyllabusPage() {
  // The hierarchy is Category -> Level (top-level Exam) -> nested
  // Preparation/Service (Exam.children), never flattened - see
  // PublicSyllabusTreeView. Papers/subjects/topics attach to whichever node
  // ends up being "selectedExam" below (the level itself if it has no
  // nested preparations, otherwise the selected preparation).
  const [categories, setCategories] = useState<PublicSyllabusCategory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | null>(null);
  const [selectedLevelId, setSelectedLevelId] = useState<number | null>(null);
  const [selectedPrepId, setSelectedPrepId] = useState<number | null>(null);

  useEffect(() => {
    let mounted = true;
    publicApi.getSyllabusTree().then((data) => {
      if (!mounted) return;
      const cats = data || [];
      setCategories(cats);
      const firstCat = cats[0];
      const firstLevel = firstCat?.exams?.[0];
      const firstPrep = firstLevel?.children?.[0];
      setSelectedCategoryId(firstCat?.id ?? null);
      setSelectedLevelId(firstLevel?.id ?? null);
      setSelectedPrepId(firstPrep?.id ?? null);
      setIsLoading(false);
    });
    return () => { mounted = false; };
  }, []);

  const selectedCategory = categories.find((c) => c.id === selectedCategoryId) || categories[0];
  const selectedLevel = selectedCategory?.exams?.find((e) => e.id === selectedLevelId) || selectedCategory?.exams?.[0];
  const selectedPrep = selectedLevel?.children?.find((c) => c.id === selectedPrepId) || selectedLevel?.children?.[0];
  // The actual leaf node whose papers/subjects/topics are shown: the
  // preparation under the level if one exists, otherwise the level itself.
  const selectedExam = selectedLevel?.children?.length ? selectedPrep : selectedLevel;
  // Official PDFs/notes an admin uploaded directly onto this exam node -
  // the official syllabus document is surfaced first/separately since it's
  // what the header's "Download" button links to.
  const examMaterials = selectedExam?.materials ?? [];
  const syllabusDoc = examMaterials.find((m) => m.contentCategory === "syllabus" && (m.fileUrl || m.externalUrl));
  const MATERIAL_CATEGORY_LABELS: Record<string, string> = {
    syllabus: "Official Syllabus",
    subjective_topicwise: "Subjective Notes",
    objective_topicwise: "Objective Notes",
    revision_notes: "Revision Notes",
  };

  // Actually saves the file instead of just opening the browser's PDF
  // viewer, which is what a plain <a target="_blank"> did before. Falls
  // back to opening the link directly if the fetch itself fails (e.g. no
  // file behind an external_url).
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const handleDownloadMaterial = async (mat: { id: number; title: string; fileUrl: string | null; externalUrl: string | null }) => {
    if (!mat.fileUrl) {
      if (mat.externalUrl) window.open(mat.externalUrl, "_blank", "noopener,noreferrer");
      return;
    }
    setDownloadingId(mat.id);
    try {
      await downloadPublicFile(mat.fileUrl, `${mat.title}.pdf`);
    } catch {
      toast.error("Couldn't download the file. Opening it instead.");
      window.open(mat.fileUrl, "_blank", "noopener,noreferrer");
    } finally {
      setDownloadingId(null);
    }
  };

  const handleCategoryChange = (categoryId: number) => {
    setSelectedCategoryId(categoryId);
    const newCat = categories.find((c) => c.id === categoryId);
    const newLevel = newCat?.exams?.[0];
    const newPrep = newLevel?.children?.[0];
    setSelectedLevelId(newLevel?.id ?? null);
    setSelectedPrepId(newPrep?.id ?? null);
  };

  const handleExamChange = (examId: number) => {
    setSelectedLevelId(examId);
    const newLevel = selectedCategory?.exams.find((e) => e.id === examId);
    const newPrep = newLevel?.children?.[0];
    setSelectedPrepId(newPrep?.id ?? null);
  };

  const handlePrepChange = (prepId: number) => {
    setSelectedPrepId(prepId);
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-[#0A1118]">
      {/* 1. HERO SECTION */}
      <section className="relative pt-32 pb-20 md:pt-40 md:pb-28 overflow-hidden">
        {/* Subtle premium background visual */}
        <div className="absolute inset-0 z-0 pointer-events-none">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,#163E6B_0%,transparent_70%)] opacity-20 dark:opacity-40"></div>
          <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-[#D4A72C]/10 rounded-full blur-[100px] mix-blend-screen hidden dark:block"></div>
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#00000003_1px,transparent_1px),linear-gradient(to_bottom,#00000003_1px,transparent_1px)] dark:bg-[linear-gradient(to_right,#ffffff03_1px,transparent_1px),linear-gradient(to_bottom,#ffffff03_1px,transparent_1px)] bg-[size:40px_40px]"></div>
        </div>

        <div className="container mx-auto px-4 relative z-10 max-w-[900px] text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#163E6B]/10 dark:bg-[#D4A72C]/10 border border-[#163E6B]/20 dark:border-[#D4A72C]/20 backdrop-blur-md mb-6 shadow-sm">
            <span className="text-[10px] font-bold uppercase tracking-widest text-[#163E6B] dark:text-[#D4A72C]">
              OFFICIAL PREPARATION STRUCTURE
            </span>
          </div>

          <h1 className="text-4xl md:text-5xl lg:text-6xl font-[900] tracking-tight text-slate-900 dark:text-white mb-6 leading-tight">
            Explore the Complete Loksewa <span className="text-[#D4A72C]">Syllabus</span>.
          </h1>

          <p className="text-lg md:text-xl text-slate-600 dark:text-slate-300 max-w-2xl mx-auto leading-relaxed mb-10 font-[500]">
            Explore every paper, subject, and topic in one organized preparation system. Know exactly what to study before you start practicing.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 max-w-2xl mx-auto">
            <div className="relative w-full">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
              <input 
                type="text" 
                placeholder="Search subjects, topics, papers..." 
                className="w-full h-14 pl-12 pr-16 rounded-[12px] border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-[#0A1118]/80 backdrop-blur-sm text-slate-900 dark:text-white placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-[#D4A72C]/50 shadow-sm transition-all"
              />
              <div className="absolute right-4 top-1/2 -translate-y-1/2 px-2 py-1 bg-slate-100 dark:bg-white/10 rounded-[6px] text-xs font-semibold text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-white/5">
                ⌘ K
              </div>
            </div>
            <Button variant="outline" className="h-14 px-6 rounded-[12px] border-slate-200 dark:border-white/10 bg-white/80 dark:bg-white/5 hover:bg-slate-50 dark:hover:bg-white/10 text-slate-700 dark:text-slate-200 backdrop-blur-sm gap-2 whitespace-nowrap">
              <SlidersHorizontal className="w-4 h-4" /> Filters
            </Button>
          </div>
        </div>
      </section>

      {/* 2. EXAM SELECTOR */}
      <section id="exam-selector" className="py-12 bg-white dark:bg-[#0B1521] border-y border-slate-200 dark:border-white/5">
        <div className="container mx-auto px-4 max-w-[1200px]">
          <h2 className="text-2xl font-[800] text-slate-900 dark:text-white mb-6 text-center">Choose Your Examination</h2>

          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
          ) : categories.length === 0 ? (
            <p className="text-center text-slate-500 font-[500]">No examinations have been published yet. Check back soon.</p>
          ) : (
          <>
          {/* Category tabs */}
          {categories.length > 1 && (
            <div className="flex flex-wrap justify-center gap-2 mb-8">
              {categories.map((cat) => {
                const isSelected = cat.id === selectedCategoryId;
                return (
                  <button
                    key={cat.id}
                    onClick={() => handleCategoryChange(cat.id)}
                    className={`px-5 py-2.5 rounded-full text-sm font-[700] transition-all border ${
                      isSelected
                        ? "bg-[#0B2545] dark:bg-[#D4A72C] text-white dark:text-[#0A1118] border-transparent"
                        : "bg-transparent text-slate-600 dark:text-slate-300 border-slate-200 dark:border-white/10 hover:border-[#163E6B]/40"
                    }`}
                  >
                    {cat.name}
                  </button>
                );
              })}
            </div>
          )}

          {/* Level cards */}
          {(!selectedCategory?.exams || selectedCategory.exams.length === 0) ? (
            <div className="text-center py-16 px-4 rounded-[20px] border border-dashed border-slate-200 dark:border-white/10 bg-slate-50/50 dark:bg-white/[0.02] max-w-xl mx-auto my-4">
              <div className="w-14 h-14 rounded-2xl bg-[#163E6B]/10 dark:bg-white/10 flex items-center justify-center mx-auto mb-4">
                <BookOpen className="w-7 h-7 text-[#163E6B] dark:text-[#D4A72C]" />
              </div>
              <h3 className="text-xl font-[800] text-slate-900 dark:text-white mb-2">
                {selectedCategory?.name} Syllabus Coming Soon
              </h3>
              <p className="text-sm font-[500] text-slate-500 dark:text-slate-400 max-w-md mx-auto leading-relaxed">
                Curriculum, papers, and subjects for {selectedCategory?.name} are being prepared. Check back soon for the updated syllabus.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {selectedCategory.exams.map((exam) => {
                const isSelected = exam.id === selectedLevelId;
                const hasPreparations = (exam.children?.length ?? 0) > 0;
                return (
                  <div
                    key={exam.id}
                    onClick={() => handleExamChange(exam.id)}
                    className={`relative p-6 rounded-[16px] cursor-pointer transition-all duration-300 border ${
                      isSelected
                        ? "bg-[#0B2545] dark:bg-[#163E6B]/40 border-[#D4A72C]/50 shadow-[0_8px_30px_rgba(212,167,44,0.15)]"
                        : "bg-slate-50 dark:bg-[#0A1118] border-slate-200 dark:border-white/10 hover:border-[#163E6B]/30 dark:hover:border-white/20 hover:shadow-md"
                    }`}
                  >
                    {isSelected && (
                      <div className="absolute top-0 right-0 p-4">
                        <CheckCircle2 className="w-6 h-6 text-[#D4A72C]" />
                      </div>
                    )}
                    <h3 className={`text-xl font-[800] mb-1 ${isSelected ? 'text-white' : 'text-slate-900 dark:text-white'}`}>
                      {exam.name}
                    </h3>
                    <div className={`text-sm font-[600] mb-4 ${isSelected ? 'text-[#D4A72C]' : 'text-[#163E6B] dark:text-slate-400'}`}>
                      {exam.level}
                    </div>
                    {hasPreparations && (
                      <div className={`flex gap-4 text-sm font-[500] mb-4 ${isSelected ? 'text-slate-300' : 'text-slate-500'}`}>
                        <span>{exam.children.length} Preparation{exam.children.length !== 1 ? 's' : ''}</span>
                      </div>
                    )}
                    <p className={`text-sm leading-relaxed ${isSelected ? 'text-slate-300' : 'text-slate-600 dark:text-slate-400'}`}>
                      {exam.description}
                    </p>
                  </div>
                );
              })}
            </div>
          )}

          {/* Preparation / Service selector — only when the selected Level nests them */}
          {(selectedLevel?.children?.length ?? 0) > 0 && (
            <div className="mt-8 pt-8 border-t border-slate-200 dark:border-white/10">
              <h3 className="text-sm font-[700] uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-4 text-center">
                Select Preparation / Service
              </h3>
              <div className="flex flex-wrap justify-center gap-2">
                {selectedLevel!.children.map((prep) => {
                  const isSelected = prep.id === selectedPrepId;
                  return (
                    <button
                      key={prep.id}
                      onClick={() => handlePrepChange(prep.id)}
                      className={`px-5 py-2.5 rounded-full text-sm font-[700] transition-all border ${
                        isSelected
                          ? "bg-[#D4A72C] text-[#0A1118] border-transparent shadow-[0_0_15px_rgba(212,167,44,0.3)]"
                          : "bg-transparent text-slate-600 dark:text-slate-300 border-slate-200 dark:border-white/10 hover:border-[#163E6B]/40"
                      }`}
                    >
                      {prep.name}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          </>
          )}
        </div>
      </section>

      {/* 3. SYLLABUS EXPLORER & 4. PAPER NAVIGATION */}
      {!isLoading && selectedExam && (
      <section className="py-16 md:py-24">
        <div className="container mx-auto px-4 max-w-[1200px]">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-10 gap-6">
            <div>
              <h2 className="text-3xl md:text-4xl font-[900] text-slate-900 dark:text-white mb-2">
                {selectedExam.name} Syllabus
              </h2>
              <p className="text-lg text-slate-600 dark:text-slate-400 font-[500]">
                Complete paper-wise and subject-wise syllabus
              </p>
            </div>
          </div>

          {/* Uploaded materials for this exam - the real PDFs/notes an admin
              attached in the Syllabus Builder, shown so a visitor doesn't
              have to dig through the paper/subject explorer to find the
              official document. Each one gets its own View (opens the PDF
              in a new tab) and Download (saves it) actions, instead of the
              whole card triggering a download on click. */}
          {examMaterials.length > 0 && (
            <div className="mb-10 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {/* Order comes straight from the backend, which sorts by the
                  admin-set StudyMaterial.order - never re-sorted here, so
                  the display sequence matches exactly what the admin chose
                  in the Syllabus Builder. */}
              {examMaterials.map((mat: any) => (
                <div
                  key={mat.id}
                  className="flex items-center gap-3 p-4 rounded-[12px] border border-slate-200 dark:border-white/10 bg-white dark:bg-[#0B1521]"
                >
                  <div className="w-10 h-10 rounded-[10px] bg-[#163E6B]/10 dark:bg-white/10 flex items-center justify-center shrink-0">
                    <FileText className="w-5 h-5 text-[#163E6B] dark:text-[#D4A72C]" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-[700] text-slate-900 dark:text-white truncate">{mat.title}</p>
                    <p className="text-xs font-[500] text-slate-500 dark:text-slate-400">
                      {MATERIAL_CATEGORY_LABELS[mat.contentCategory] || mat.contentCategory}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {(mat.fileUrl || mat.externalUrl) && (
                      <a
                        href={mat.fileUrl || mat.externalUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="p-2 rounded-md text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-white/10 hover:text-[#163E6B] dark:hover:text-[#D4A72C] transition-colors"
                        title="View"
                      >
                        <Eye className="w-4 h-4" />
                      </a>
                    )}
                    <button
                      type="button"
                      onClick={() => handleDownloadMaterial(mat)}
                      disabled={downloadingId === mat.id}
                      className="p-2 rounded-md text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-white/10 hover:text-[#163E6B] dark:hover:text-[#D4A72C] transition-colors disabled:opacity-50"
                      title="Download"
                    >
                      {downloadingId === mat.id
                        ? <Loader2 className="w-4 h-4 animate-spin" />
                        : <Download className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

        </div>
      </section>
      )}

      {/* 7. SMART SYLLABUS FLOW */}
      <section className="py-20 bg-slate-900 dark:bg-[#060A0F] text-white relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,#163E6B_0%,transparent_70%)] opacity-30"></div>
        
        <div className="container mx-auto px-4 max-w-[1200px] relative z-10 text-center">
          <h2 className="text-3xl md:text-4xl font-[900] mb-16 tracking-tight">From Syllabus to Success</h2>
          
          <div className="flex flex-col md:flex-row justify-center items-center gap-4 md:gap-8">
            <div className="flex flex-col items-center w-full md:w-[200px]">
              <div className="w-16 h-16 rounded-2xl bg-white/10 backdrop-blur-md flex items-center justify-center mb-4 border border-white/20">
                <FileText className="w-8 h-8 text-white" />
              </div>
              <h4 className="text-[18px] font-[700] mb-2">Syllabus</h4>
              <p className="text-[13px] text-slate-400 font-[500] leading-snug">Official curriculum breakdown</p>
            </div>
            
            <ArrowRight className="w-6 h-6 text-slate-600 rotate-90 md:rotate-0 flex-shrink-0 my-2 md:my-0" />
            
            <div className="flex flex-col items-center w-full md:w-[200px]">
              <div className="w-16 h-16 rounded-2xl bg-white/10 backdrop-blur-md flex items-center justify-center mb-4 border border-white/20">
                <Target className="w-8 h-8 text-white" />
              </div>
              <h4 className="text-[18px] font-[700] mb-2">Topics</h4>
              <p className="text-[13px] text-slate-400 font-[500] leading-snug">Granular subject concepts</p>
            </div>

            <ArrowRight className="w-6 h-6 text-slate-600 rotate-90 md:rotate-0 flex-shrink-0 my-2 md:my-0" />
            
            <div className="flex flex-col items-center w-full md:w-[200px]">
              <div className="w-16 h-16 rounded-2xl bg-[#D4A72C]/20 backdrop-blur-md flex items-center justify-center mb-4 border border-[#D4A72C]/50 shadow-[0_0_20px_rgba(212,167,44,0.3)]">
                <Activity className="w-8 h-8 text-[#D4A72C]" />
              </div>
              <h4 className="text-[18px] font-[700] mb-2 text-[#D4A72C]">Practice</h4>
              <p className="text-[13px] text-slate-300 font-[500] leading-snug">Topic-wise targeted questions</p>
            </div>

            <ArrowRight className="w-6 h-6 text-slate-600 rotate-90 md:rotate-0 flex-shrink-0 my-2 md:my-0" />
            
            <div className="flex flex-col items-center w-full md:w-[200px]">
              <div className="w-16 h-16 rounded-2xl bg-white/10 backdrop-blur-md flex items-center justify-center mb-4 border border-white/20">
                <BrainCircuit className="w-8 h-8 text-white" />
              </div>
              <h4 className="text-[18px] font-[700] mb-2">Mock Exams</h4>
              <p className="text-[13px] text-slate-400 font-[500] leading-snug">Full-length realistic tests</p>
            </div>
          </div>
        </div>
      </section>

      {/* 8. FEATURE HIGHLIGHTS */}
      <section className="py-20 bg-white dark:bg-[#0A1118]">
        <div className="container mx-auto px-4 max-w-[1200px]">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="p-8 rounded-[20px] bg-slate-50 dark:bg-white/5 border border-slate-200 dark:border-white/5">
              <div className="w-12 h-12 rounded-[12px] bg-[#163E6B]/10 dark:bg-white/10 flex items-center justify-center mb-6">
                <BookOpen className="w-6 h-6 text-[#163E6B] dark:text-[#D4A72C]" />
              </div>
              <h3 className="text-lg font-[800] text-slate-900 dark:text-white mb-3">Complete Coverage</h3>
              <p className="text-sm font-[500] text-slate-600 dark:text-slate-400 leading-relaxed">
                Every paper and topic organized in one place for comprehensive study.
              </p>
            </div>
            
            <div className="p-8 rounded-[20px] bg-slate-50 dark:bg-white/5 border border-slate-200 dark:border-white/5">
              <div className="w-12 h-12 rounded-[12px] bg-[#163E6B]/10 dark:bg-white/10 flex items-center justify-center mb-6">
                <Target className="w-6 h-6 text-[#163E6B] dark:text-[#D4A72C]" />
              </div>
              <h3 className="text-lg font-[800] text-slate-900 dark:text-white mb-3">Structured Preparation</h3>
              <p className="text-sm font-[500] text-slate-600 dark:text-slate-400 leading-relaxed">
                Know exactly what to study and in what order for maximum efficiency.
              </p>
            </div>

            <div className="p-8 rounded-[20px] bg-slate-50 dark:bg-white/5 border border-slate-200 dark:border-white/5">
              <div className="w-12 h-12 rounded-[12px] bg-[#163E6B]/10 dark:bg-white/10 flex items-center justify-center mb-6">
                <Activity className="w-6 h-6 text-[#163E6B] dark:text-[#D4A72C]" />
              </div>
              <h3 className="text-lg font-[800] text-slate-900 dark:text-white mb-3">Practice Integration</h3>
              <p className="text-sm font-[500] text-slate-600 dark:text-slate-400 leading-relaxed">
                Move directly from syllabus topics to highly relevant practice questions.
              </p>
            </div>

            <div className="p-8 rounded-[20px] bg-slate-50 dark:bg-white/5 border border-slate-200 dark:border-white/5">
              <div className="w-12 h-12 rounded-[12px] bg-[#163E6B]/10 dark:bg-white/10 flex items-center justify-center mb-6">
                <BrainCircuit className="w-6 h-6 text-[#163E6B] dark:text-[#D4A72C]" />
              </div>
              <h3 className="text-lg font-[800] text-slate-900 dark:text-white mb-3">AI-Powered Guidance</h3>
              <p className="text-sm font-[500] text-slate-600 dark:text-slate-400 leading-relaxed">
                Use our built-in AI Tutor to understand difficult or complex topics.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 9. DOWNLOAD / REFERENCE SECTION */}
      <section className="py-20 bg-[#0B2545] dark:bg-[#050C14] text-white">
        <div className="container mx-auto px-4 max-w-[900px] text-center">
          <h2 className="text-3xl md:text-4xl font-[900] mb-4">Keep Your Syllabus With You</h2>
          <p className="text-lg text-slate-300 font-[500] mb-10 max-w-2xl mx-auto">
            Download the complete syllabus and use it as your preparation reference anytime. Access it fully integrated within our app.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            {syllabusDoc && (
              <>
                {(syllabusDoc.fileUrl || syllabusDoc.externalUrl) && (
                  <a href={syllabusDoc.fileUrl || syllabusDoc.externalUrl} target="_blank" rel="noopener noreferrer">
                    <Button
                      variant="outline"
                      className="h-14 px-8 rounded-[12px] bg-transparent border-white/30 text-white hover:bg-white/10 font-[700] text-[16px]"
                    >
                      <Eye className="w-5 h-5 mr-2" /> View Syllabus PDF
                    </Button>
                  </a>
                )}
                <Button
                  onClick={() => handleDownloadMaterial(syllabusDoc)}
                  disabled={downloadingId === syllabusDoc.id}
                  className="h-14 px-8 rounded-[12px] bg-white text-[#0B2545] hover:bg-slate-100 font-[800] text-[16px] transition-all disabled:opacity-70"
                >
                  {downloadingId === syllabusDoc.id
                    ? <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    : <Download className="w-5 h-5 mr-2" />}
                  Download Syllabus PDF
                </Button>
              </>
            )}
          </div>
        </div>
      </section>

      {/* 10. FINAL CTA */}
      <section className="py-24 bg-white dark:bg-[#0B1521] border-t border-slate-200 dark:border-white/5 text-center">
        <div className="container mx-auto px-4 max-w-[800px]">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#163E6B]/10 dark:bg-[#D4A72C]/10 mb-6">
            <span className="text-[10px] font-bold uppercase tracking-widest text-[#163E6B] dark:text-[#D4A72C]">
              READY TO BEGIN?
            </span>
          </div>
          
          <h2 className="text-4xl md:text-5xl font-[900] text-slate-900 dark:text-white mb-6 tracking-tight">
            Know Every Examination&apos;s Syllabus, In One Place.
          </h2>

          <p className="text-lg md:text-xl text-slate-600 dark:text-slate-400 font-[500] mb-10 leading-relaxed">
            Switch between examinations, preparations, papers, and topics to see exactly what each one covers.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <a href="#exam-selector">
              <Button className="h-14 px-8 rounded-[12px] bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] font-[800] text-[16px] transition-all shadow-[0_0_20px_rgba(212,167,44,0.2)] hover:shadow-[0_0_30px_rgba(212,167,44,0.4)] flex items-center justify-center gap-2 group/btn">
                Browse All Examinations <ArrowRight className="w-5 h-5 group-hover/btn:translate-x-1 transition-transform" />
              </Button>
            </a>
          </div>
        </div>
      </section>

    </div>
  );
}
