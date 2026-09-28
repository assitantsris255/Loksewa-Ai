"use client";

import React, { useState, useMemo, useEffect } from 'react';
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import {
  Search, BookOpen, Zap, Globe, FileText, Bookmark, BookmarkCheck,
  Clock, CheckCircle2, ChevronRight, SlidersHorizontal, Lock, Unlock,
  PlayCircle, BrainCircuit, Sparkles, AlertCircle, MessageSquare,
  ArrowRight, Target, BarChart2, Loader2
} from "lucide-react";
import Link from "next/link";
import { publicApi, type PublicNote } from "@/lib/api/public-api";

// Real material_type values (see notes/models.py) grouped into the four
// discovery cards shown below the hero.
const CATEGORIES = [
  { id: "notes", types: ["notes", "study_guide"], label: "Subject Notes", icon: BookOpen, desc: "Detailed notes organized by subject" },
  { id: "revision", types: ["presentation"], label: "Revision Notes", icon: Zap, desc: "Concise materials for quick review" },
  { id: "external", types: ["external_link", "video"], label: "Current Affairs & Media", icon: Globe, desc: "Important updates and video resources" },
  { id: "resources", types: ["pdf", "document", "reference"], label: "Exam Resources", icon: FileText, desc: "Guides and reference materials" }
];

const MATERIAL_TYPE_LABELS: Record<string, string> = {
  notes: "Notes",
  pdf: "PDF",
  video: "Video",
  document: "Document",
  presentation: "Presentation",
  external_link: "External Link",
  study_guide: "Study Guide",
  reference: "Reference Material",
};

const DIFFICULTY_LABELS: Record<string, "Beginner" | "Intermediate" | "Advanced"> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
};

type Note = {
  id: string;
  title: string;
  description: string;
  subject: string;
  type: string;
  materialType: string;
  exam: string;
  readingTime: number; // in minutes
  difficulty: "Beginner" | "Intermediate" | "Advanced";
  updatedAt: string;
};

function timeAgo(iso: string | null): string {
  if (!iso) return "Recently";
  const diffMs = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diffMs / 86400000);
  if (days <= 0) return "Today";
  if (days === 1) return "1 day ago";
  if (days < 7) return `${days} days ago`;
  if (days < 30) return `${Math.floor(days / 7)} week${Math.floor(days / 7) > 1 ? "s" : ""} ago`;
  return `${Math.floor(days / 30)} month${Math.floor(days / 30) > 1 ? "s" : ""} ago`;
}

function mapNote(m: PublicNote): Note {
  return {
    id: String(m.id),
    title: m.title,
    description: m.description,
    subject: m.subject_name || "General",
    type: MATERIAL_TYPE_LABELS[m.material_type] || m.material_type,
    materialType: m.material_type,
    exam: m.exam_name || "All Exams",
    readingTime: m.estimated_reading_time,
    difficulty: DIFFICULTY_LABELS[m.difficulty] || "Beginner",
    updatedAt: timeAgo(m.created_at),
  };
}

export default function NotesPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedExam, setSelectedExam] = useState("All Exams");
  const [selectedSubject, setSelectedSubject] = useState("All Subjects");
  const [selectedType, setSelectedType] = useState("All Types");
  const [selectedDifficulty, setSelectedDifficulty] = useState("All Levels");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [previewNote, setPreviewNote] = useState<Note | null>(null);
  const [savedNotes, setSavedNotes] = useState<Set<string>>(new Set());
  const [showAuthPrompt, setShowAuthPrompt] = useState(false);
  const [notes, setNotes] = useState<Note[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    publicApi.getNotesMaterials(24).then((data) => {
      if (!mounted) return;
      setNotes((data || []).map(mapNote));
      setIsLoading(false);
    });
    return () => { mounted = false; };
  }, []);

  const EXAMS = useMemo(() => ["All Exams", ...Array.from(new Set(notes.map(n => n.exam))).filter(e => e !== "All Exams")], [notes]);
  const SUBJECTS = useMemo(() => ["All Subjects", ...Array.from(new Set(notes.map(n => n.subject)))], [notes]);
  const TYPES = useMemo(() => ["All Types", ...Array.from(new Set(notes.map(n => n.type)))], [notes]);
  const DIFFICULTIES = ["All Levels", "Beginner", "Intermediate", "Advanced"];

  const toggleSave = (e: React.MouseEvent, noteId: string) => {
    e.stopPropagation();
    // Simulate auth check - prompt if they try to save
    setShowAuthPrompt(true);
    /* In real app:
    if (!user) setShowAuthPrompt(true);
    else setSavedNotes(prev => { ... })
    */
  };

  const openPreview = (note: Note) => {
    setPreviewNote(note);
  };

  const featuredNotes = useMemo(() => notes.slice(0, 3), [notes]);

  const filteredNotes = useMemo(() => {
    return notes.filter(note => {
      const matchesSearch = note.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                            note.subject.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesExam = selectedExam === "All Exams" || note.exam === selectedExam || note.exam === "All Exams";
      const matchesSubject = selectedSubject === "All Subjects" || note.subject === selectedSubject;
      const matchesType = selectedType === "All Types" || note.type === selectedType;
      const matchesDiff = selectedDifficulty === "All Levels" || note.difficulty === selectedDifficulty;
      const cat = CATEGORIES.find(c => c.id === selectedCategory);
      const matchesCat = !cat || cat.types.includes(note.materialType);

      return matchesSearch && matchesExam && matchesSubject && matchesType && matchesDiff && matchesCat;
    });
  }, [notes, searchQuery, selectedExam, selectedSubject, selectedType, selectedDifficulty, selectedCategory]);

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-[#0A1118]">
      <main className="flex-grow pt-0 pb-20">
        
        {/* 1. HERO SECTION */}
        <section className="relative pt-32 pb-20 md:pt-40 md:pb-24 overflow-hidden">
          {/* Subtle premium background visual */}
          <div className="absolute inset-0 z-0 pointer-events-none">
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,#163E6B_0%,transparent_70%)] opacity-20 dark:opacity-40"></div>
            <div className="absolute inset-0 bg-gradient-to-b from-transparent via-slate-50/80 to-slate-50 dark:via-[#0A1118]/80 dark:to-[#0A1118]"></div>
            {/* Subtle grid */}
            <div className="absolute inset-0 bg-[linear-gradient(to_right,#00000003_1px,transparent_1px),linear-gradient(to_bottom,#00000003_1px,transparent_1px)] dark:bg-[linear-gradient(to_right,#ffffff03_1px,transparent_1px),linear-gradient(to_bottom,#ffffff03_1px,transparent_1px)] bg-[size:40px_40px]"></div>
          </div>

          <div className="container mx-auto px-4 relative z-10 max-w-[900px] text-center">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#163E6B]/10 dark:bg-[#D4A72C]/10 border border-[#163E6B]/20 dark:border-[#D4A72C]/20 backdrop-blur-md mb-6 shadow-sm">
              <span className="text-[10px] font-bold uppercase tracking-widest text-[#163E6B] dark:text-[#D4A72C]">
                SMART STUDY · BETTER PREPARATION
              </span>
            </div>

            <h1 className="text-4xl md:text-5xl lg:text-6xl font-[900] tracking-tight text-slate-900 dark:text-white mb-6 leading-tight">
              Study Smarter With <span className="text-[#163E6B] dark:text-[#D4A72C]">Organized Notes.</span>
            </h1>

            <p className="text-lg md:text-xl text-slate-600 dark:text-slate-300 max-w-2xl mx-auto leading-relaxed mb-10 font-[500]">
              Explore structured study materials, revision notes, subject guides, and exam-focused resources designed around the Loksewa syllabus.
            </p>

            {/* Large Search Interface */}
            <div className="max-w-2xl mx-auto relative group">
              <div className="absolute inset-0 bg-gradient-to-r from-[#163E6B] to-[#D4A72C] rounded-[16px] blur-md opacity-20 group-hover:opacity-40 transition-opacity duration-500"></div>
              <div className="relative flex items-center bg-white dark:bg-[#0A1118] border border-slate-200 dark:border-white/10 rounded-[16px] p-2 shadow-lg transition-all focus-within:ring-2 focus-within:ring-[#D4A72C] focus-within:border-transparent">
                <div className="pl-4 pr-2 text-slate-400">
                  <Search className="w-6 h-6" />
                </div>
                <input 
                  type="text"
                  placeholder="Search notes, subjects, topics, or keywords..."
                  className="w-full bg-transparent border-none text-slate-900 dark:text-white placeholder:text-slate-600 focus:outline-none focus:ring-0 text-lg py-3"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                <div className="hidden sm:flex items-center px-3 border-r border-slate-200 dark:border-white/10">
                  <span className="text-xs text-slate-400 font-medium bg-slate-100 dark:bg-white/5 px-2 py-1 rounded-md border border-slate-200 dark:border-white/10">Ctrl+K</span>
                </div>
                <Button 
                  variant="ghost" 
                  className="ml-2 h-12 px-4 rounded-[12px] text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/5"
                  onClick={() => setIsFilterOpen(!isFilterOpen)}
                >
                  <SlidersHorizontal className="w-5 h-5 mr-2" />
                  <span className="font-semibold">Filters</span>
                </Button>
              </div>
            </div>

            {/* Discovery Indicators */}
            <div className="flex flex-wrap items-center justify-center gap-4 mt-8 text-sm font-[600] text-slate-500 dark:text-slate-400">
              <div className="flex items-center gap-1.5 hover:text-slate-800 dark:hover:text-slate-200 cursor-pointer transition-colors" onClick={() => setSelectedCategory('subject')}>
                <BookOpen className="w-4 h-4 text-[#163E6B] dark:text-[#D4A72C]" />
                <span>Subject Notes</span>
              </div>
              <div className="hidden sm:block w-1 h-1 rounded-full bg-slate-300 dark:bg-slate-700"></div>
              <div className="flex items-center gap-1.5 hover:text-slate-800 dark:hover:text-slate-200 cursor-pointer transition-colors" onClick={() => setSelectedCategory('revision')}>
                <Zap className="w-4 h-4 text-[#163E6B] dark:text-[#D4A72C]" />
                <span>Revision Materials</span>
              </div>
              <div className="hidden sm:block w-1 h-1 rounded-full bg-slate-300 dark:bg-slate-700"></div>
              <div className="flex items-center gap-1.5 hover:text-slate-800 dark:hover:text-slate-200 cursor-pointer transition-colors" onClick={() => setSelectedCategory('resources')}>
                <FileText className="w-4 h-4 text-[#163E6B] dark:text-[#D4A72C]" />
                <span>Exam Resources</span>
              </div>
            </div>
          </div>
        </section>

        {/* 2. NOTE CATEGORY SELECTOR */}
        <section className="py-16 bg-white dark:bg-[#060B11] border-y border-slate-200 dark:border-white/5">
          <div className="container mx-auto px-4">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-[800] text-slate-900 dark:text-white tracking-tight">Explore Study Materials</h2>
              <p className="text-slate-500 mt-2 font-[500]">Find exactly what you need for your preparation stage.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 max-w-6xl mx-auto">
              {CATEGORIES.map((cat) => {
                const Icon = cat.icon;
                const isActive = selectedCategory === cat.id;
                return (
                  <div 
                    key={cat.id}
                    className={`group relative overflow-hidden rounded-[20px] border transition-all duration-300 cursor-pointer
                      ${isActive 
                        ? 'border-[#163E6B] dark:border-[#D4A72C] shadow-lg shadow-[#163E6B]/10 dark:shadow-[#D4A72C]/10 bg-[#163E6B]/5 dark:bg-[#D4A72C]/5' 
                        : 'border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-white/5 hover:border-slate-300 dark:hover:border-white/20 hover:bg-white dark:hover:bg-white/10 hover:shadow-md'
                      }
                    `}
                    onClick={() => setSelectedCategory(isActive ? null : cat.id)}
                  >
                    <div className="p-6">
                      <div className={`w-12 h-12 rounded-xl flex items-center justify-center mb-6 transition-colors
                        ${isActive 
                          ? 'bg-[#163E6B] text-white dark:bg-[#D4A72C] dark:text-[#0A1118]' 
                          : 'bg-white dark:bg-white/10 text-slate-600 dark:text-slate-300 shadow-sm'
                        }
                      `}>
                        <Icon className="w-6 h-6" strokeWidth={2} />
                      </div>
                      <h3 className="text-xl font-[700] text-slate-900 dark:text-white mb-2">{cat.label}</h3>
                      <p className="text-slate-500 dark:text-slate-400 text-sm font-[500] mb-6 leading-relaxed">
                        {cat.desc}
                      </p>
                      
                      <div className="flex items-center text-[13px] font-[700] uppercase tracking-wider text-[#163E6B] dark:text-[#D4A72C] group-hover:gap-2 transition-all">
                        <span>Explore {cat.label}</span>
                        <ChevronRight className="w-4 h-4 ml-1 opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* 3. FEATURED NOTES */}
        <section className="py-16">
          <div className="container mx-auto px-4 max-w-7xl">
            <div className="mb-10">
              <h2 className="text-2xl font-[800] text-slate-900 dark:text-white tracking-tight">Featured Study Materials</h2>
              <p className="text-slate-500 mt-1 font-[500]">Start with the most useful materials for your preparation.</p>
            </div>

            {isLoading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
              </div>
            ) : featuredNotes.length === 0 ? (
              <p className="text-slate-500 font-[500]">No study materials published yet. Check back soon.</p>
            ) : (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {featuredNotes.map((note) => (
                <div key={note.id} className="group relative bg-white dark:bg-[#0A1118] rounded-[20px] border border-slate-200 dark:border-white/10 overflow-hidden hover:border-[#163E6B]/50 dark:hover:border-[#D4A72C]/50 transition-all hover:shadow-xl hover:-translate-y-1 flex flex-col h-full">

                  {/* Card Header Pattern */}
                  <div className={`h-24 relative overflow-hidden ${
                    note.materialType === "notes" || note.materialType === "study_guide" ? "bg-gradient-to-br from-[#163E6B] to-[#0A1118]" :
                    note.materialType === "presentation" ? "bg-gradient-to-br from-[#D4A72C] to-[#8C6D1D]" :
                    "bg-gradient-to-br from-slate-700 to-slate-900"
                  }`}>
                    <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff1a_1px,transparent_1px),linear-gradient(to_bottom,#ffffff1a_1px,transparent_1px)] bg-[size:16px_16px]"></div>
                  </div>

                  <div className="p-6 flex-grow flex flex-col">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-xs font-bold px-2.5 py-1 rounded-md bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-300">
                        {note.subject}
                      </span>
                      <span className="text-xs font-bold px-2.5 py-1 rounded-md bg-[#163E6B]/10 dark:bg-[#D4A72C]/10 text-[#163E6B] dark:text-[#D4A72C]">
                        {note.type}
                      </span>
                    </div>

                    <h3 className="text-lg font-[800] text-slate-900 dark:text-white leading-snug mb-4 group-hover:text-[#163E6B] dark:group-hover:text-[#D4A72C] transition-colors">
                      {note.title}
                    </h3>

                    <div className="mt-auto grid grid-cols-2 gap-y-3 gap-x-2 text-sm text-slate-500 dark:text-slate-400 font-[500]">
                      <div className="flex items-center gap-2">
                        <BookOpen className="w-4 h-4" />
                        <span>{note.exam}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Clock className="w-4 h-4" />
                        <span>{note.readingTime} min read</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4" />
                        <span>{note.difficulty}</span>
                      </div>
                    </div>
                  </div>

                  <div className="p-4 border-t border-slate-100 dark:border-white/5 bg-slate-50 dark:bg-white/5 flex items-center justify-between">
                    <button
                      className="text-slate-400 hover:text-[#D4A72C] transition-colors p-2 rounded-full hover:bg-white dark:hover:bg-[#0A1118]"
                      onClick={(e) => toggleSave(e, note.id)}
                    >
                      {savedNotes.has(note.id) ? <BookmarkCheck className="w-5 h-5 text-[#D4A72C]" /> : <Bookmark className="w-5 h-5" />}
                    </button>
                    <Button
                      variant="ghost"
                      className="font-[700] text-[#163E6B] dark:text-white hover:bg-[#163E6B]/10 dark:hover:bg-white/10"
                      onClick={() => openPreview(note)}
                    >
                      View Notes <ChevronRight className="w-4 h-4 ml-1" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
            )}
          </div>
        </section>

        {/* 4 & 5. FILTER SYSTEM & LIBRARY */}
        <section className="py-16 bg-white dark:bg-[#060B11] border-t border-slate-200 dark:border-white/5">
          <div className="container mx-auto px-4 max-w-7xl">
            <div className="flex flex-col lg:flex-row gap-8">
              
              {/* Sidebar Filters */}
              <div className={`lg:w-64 shrink-0 space-y-8 ${isFilterOpen ? 'block' : 'hidden lg:block'}`}>
                <div>
                  <h3 className="text-sm font-[800] text-slate-900 dark:text-white uppercase tracking-wider mb-4">Exam</h3>
                  <div className="space-y-2">
                    {EXAMS.map(exam => (
                      <label key={exam} className="flex items-center gap-3 cursor-pointer group">
                        <input 
                          type="radio" 
                          name="exam" 
                          className="w-4 h-4 text-[#D4A72C] bg-transparent border-slate-300 dark:border-slate-600 focus:ring-[#D4A72C]" 
                          checked={selectedExam === exam}
                          onChange={() => setSelectedExam(exam)}
                        />
                        <span className={`text-sm font-[500] group-hover:text-slate-900 dark:group-hover:text-white transition-colors ${selectedExam === exam ? 'text-slate-900 dark:text-white' : 'text-slate-600 dark:text-slate-400'}`}>
                          {exam}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-[800] text-slate-900 dark:text-white uppercase tracking-wider mb-4">Subject</h3>
                  <div className="space-y-2 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                    {SUBJECTS.map(subject => (
                      <label key={subject} className="flex items-center gap-3 cursor-pointer group">
                        <input 
                          type="radio" 
                          name="subject" 
                          className="w-4 h-4 text-[#D4A72C] bg-transparent border-slate-300 dark:border-slate-600 focus:ring-[#D4A72C]" 
                          checked={selectedSubject === subject}
                          onChange={() => setSelectedSubject(subject)}
                        />
                        <span className={`text-sm font-[500] group-hover:text-slate-900 dark:group-hover:text-white transition-colors ${selectedSubject === subject ? 'text-slate-900 dark:text-white' : 'text-slate-600 dark:text-slate-400'}`}>
                          {subject}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-[800] text-slate-900 dark:text-white uppercase tracking-wider mb-4">Material Type</h3>
                  <div className="space-y-2">
                    {TYPES.map(type => (
                      <label key={type} className="flex items-center gap-3 cursor-pointer group">
                        <input 
                          type="radio" 
                          name="type" 
                          className="w-4 h-4 text-[#D4A72C] bg-transparent border-slate-300 dark:border-slate-600 focus:ring-[#D4A72C]" 
                          checked={selectedType === type}
                          onChange={() => setSelectedType(type)}
                        />
                        <span className={`text-sm font-[500] group-hover:text-slate-900 dark:group-hover:text-white transition-colors ${selectedType === type ? 'text-slate-900 dark:text-white' : 'text-slate-600 dark:text-slate-400'}`}>
                          {type}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-[800] text-slate-900 dark:text-white uppercase tracking-wider mb-4">Difficulty</h3>
                  <div className="space-y-2">
                    {DIFFICULTIES.map(diff => (
                      <label key={diff} className="flex items-center gap-3 cursor-pointer group">
                        <input 
                          type="radio" 
                          name="diff" 
                          className="w-4 h-4 text-[#D4A72C] bg-transparent border-slate-300 dark:border-slate-600 focus:ring-[#D4A72C]" 
                          checked={selectedDifficulty === diff}
                          onChange={() => setSelectedDifficulty(diff)}
                        />
                        <span className={`text-sm font-[500] group-hover:text-slate-900 dark:group-hover:text-white transition-colors ${selectedDifficulty === diff ? 'text-slate-900 dark:text-white' : 'text-slate-600 dark:text-slate-400'}`}>
                          {diff}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>

              {/* Main Library Grid */}
              <div className="flex-1">
                <div className="flex items-center justify-between mb-8">
                  <h2 className="text-2xl font-[800] text-slate-900 dark:text-white tracking-tight">Study Material Library</h2>
                  <div className="text-sm font-[600] text-slate-500">
                    {isLoading ? "Loading…" : `Showing ${filteredNotes.length} notes`}
                  </div>
                </div>

                {isLoading ? (
                  <div className="flex items-center justify-center py-20">
                    <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
                  </div>
                ) : filteredNotes.length > 0 ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                    {filteredNotes.map((note) => (
                      <div key={note.id} className="group flex flex-col bg-slate-50 dark:bg-[#0A1118] rounded-[16px] border border-slate-200 dark:border-white/10 hover:border-[#163E6B]/30 dark:hover:border-white/20 transition-all hover:shadow-lg cursor-pointer" onClick={() => openPreview(note)}>
                        <div className="p-5 flex-grow">
                          <div className="flex items-start justify-between mb-3">
                            <span className="text-[11px] font-bold uppercase tracking-wider px-2 py-1 rounded bg-[#163E6B]/10 dark:bg-white/5 text-[#163E6B] dark:text-slate-300">
                              {note.subject}
                            </span>
                          </div>
                          <h3 className="text-lg font-[700] text-slate-900 dark:text-white leading-snug mb-2 group-hover:text-[#163E6B] dark:group-hover:text-[#D4A72C] transition-colors">
                            {note.title}
                          </h3>
                          <p className="text-sm text-slate-500 dark:text-slate-400 font-[500] mb-4">
                            {note.type}
                          </p>
                          <div className="flex flex-wrap items-center gap-4 text-xs font-[600] text-slate-500 dark:text-slate-500">
                            <div className="flex items-center gap-1.5"><BookOpen className="w-3.5 h-3.5" />{note.exam}</div>
                            <div className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" />{note.readingTime}m read</div>
                          </div>
                        </div>
                        <div className="p-4 border-t border-slate-200 dark:border-white/5 flex items-center justify-between bg-white dark:bg-transparent rounded-b-[16px]">
                          <span className="text-xs font-[500] text-slate-400">Updated {note.updatedAt}</span>
                          <span className="text-sm font-[700] text-[#163E6B] dark:text-white group-hover:text-[#D4A72C] flex items-center transition-colors">
                            View <ChevronRight className="w-4 h-4 ml-0.5 opacity-50 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-20 px-4 text-center border border-dashed border-slate-300 dark:border-white/10 rounded-[20px] bg-slate-50 dark:bg-white/5">
                    <div className="w-16 h-16 rounded-full bg-slate-200 dark:bg-white/10 flex items-center justify-center mb-4">
                      <Search className="w-8 h-8 text-slate-400" />
                    </div>
                    <h3 className="text-xl font-[800] text-slate-900 dark:text-white mb-2">No study materials found</h3>
                    <p className="text-slate-500 font-[500] mb-6 max-w-md">
                      Try adjusting your search query, or clear your filters to see more results.
                    </p>
                    <Button 
                      variant="outline" 
                      onClick={() => {
                        setSearchQuery("");
                        setSelectedExam("All Exams");
                        setSelectedSubject("All Subjects");
                        setSelectedType("All Types");
                        setSelectedDifficulty("All Levels");
                        setSelectedCategory(null);
                      }}
                      className="font-[700]"
                    >
                      Clear All Filters
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>

        {/* 8. NOTE READING EXPERIENCE PREVIEW */}
        <section className="py-20 overflow-hidden bg-slate-50 dark:bg-[#0A1118]">
          <div className="container mx-auto px-4 max-w-7xl">
            <div className="text-center mb-16">
              <h2 className="text-3xl font-[800] text-slate-900 dark:text-white tracking-tight mb-4">A Better Way To Study</h2>
              <p className="text-lg text-slate-500 font-[500] max-w-2xl mx-auto">Experience a distraction-free, powerful reading interface designed specifically for Loksewa preparation.</p>
            </div>

            <div className="relative mx-auto max-w-6xl rounded-[24px] border border-slate-200 dark:border-white/10 bg-white dark:bg-[#060B11] shadow-2xl overflow-hidden flex flex-col md:flex-row h-[600px]">
              {/* Left Sidebar */}
              <div className="hidden md:block w-64 border-r border-slate-200 dark:border-white/5 bg-slate-50/50 dark:bg-white/5 p-6 overflow-y-auto">
                <h3 className="text-xs font-[800] uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-6">Contents</h3>
                <div className="space-y-4 text-sm font-[600] text-slate-600 dark:text-slate-300">
                  <div className="text-[#163E6B] dark:text-[#D4A72C]">1. Introduction</div>
                  <div className="pl-4">2. Constitutional Development</div>
                  <div className="pl-4">3. Fundamental Rights</div>
                  <div className="pl-4">4. Constitutional Bodies</div>
                  <div className="pl-4">5. Federal Structure</div>
                  <div className="pl-4">6. Judiciary</div>
                  <div className="pl-4">7. Local Government</div>
                </div>
              </div>
              
              {/* Center Content */}
              <div className="flex-1 p-8 md:p-12 overflow-y-auto relative bg-[linear-gradient(to_bottom,transparent_39px,#f1f5f9_40px)] dark:bg-[linear-gradient(to_bottom,transparent_39px,#ffffff05_40px)] bg-[size:100%_40px]">
                <div className="max-w-2xl mx-auto">
                  <h1 className="text-3xl font-[800] text-slate-900 dark:text-white mb-6">1. Introduction to the Constitution</h1>
                  <p className="text-lg leading-relaxed text-slate-700 dark:text-slate-300 mb-8">
                    The Constitution of Nepal is the fundamental law of the land. It establishes Nepal as a federal democratic republican state and guarantees various fundamental rights to its citizens.
                  </p>
                  <div className="bg-yellow-100 dark:bg-yellow-900/30 p-4 rounded-[12px] border-l-4 border-yellow-400 dark:border-yellow-600 mb-8 text-slate-800 dark:text-slate-200">
                    <strong className="block mb-1 text-yellow-800 dark:text-yellow-500">Key Concept</strong>
                    A constitution is not just a legal document but a political one that reflects the aspirations of the people.
                  </div>
                  <h2 className="text-2xl font-[700] text-slate-900 dark:text-white mb-4">Historical Context</h2>
                  <p className="text-lg leading-relaxed text-slate-700 dark:text-slate-300">
                    Nepal's constitutional history is marked by several transitions. The current constitution, promulgated in 2015, is the first to be drafted by elected representatives through a Constituent Assembly.
                  </p>
                </div>
              </div>

              {/* Right Sidebar (Study Tools) */}
              <div className="hidden lg:flex w-20 flex-col items-center py-8 border-l border-slate-200 dark:border-white/5 bg-slate-50/50 dark:bg-white/5 space-y-6">
                <button className="w-10 h-10 rounded-full bg-white dark:bg-white/10 shadow-sm border border-slate-200 dark:border-white/10 flex items-center justify-center text-slate-500 hover:text-[#163E6B] dark:hover:text-white transition-colors" title="Highlight">
                  <div className="w-4 h-4 bg-yellow-400 rounded-sm"></div>
                </button>
                <button className="w-10 h-10 rounded-full bg-white dark:bg-white/10 shadow-sm border border-slate-200 dark:border-white/10 flex items-center justify-center text-slate-500 hover:text-[#163E6B] dark:hover:text-white transition-colors" title="Bookmark">
                  <Bookmark className="w-5 h-5" />
                </button>
                <div className="w-6 h-px bg-slate-200 dark:bg-white/10"></div>
                <button className="w-10 h-10 rounded-full bg-gradient-to-r from-[#163E6B] to-[#1e528d] dark:from-[#D4A72C] dark:to-[#e5b93d] shadow-sm flex items-center justify-center text-white dark:text-[#0A1118] transition-transform hover:scale-110" title="Ask AI">
                  <Sparkles className="w-5 h-5" />
                </button>
                <div className="w-6 h-px bg-slate-200 dark:bg-white/10"></div>
                <button className="text-xl font-serif text-slate-500 hover:text-[#163E6B] dark:hover:text-white transition-colors" title="Font Size">
                  Aa
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* 9. AI NOTE ASSISTANT */}
        <section className="py-20 relative overflow-hidden bg-white dark:bg-[#060B11]">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,#163E6B_0%,transparent_50%)] opacity-5 dark:opacity-20 pointer-events-none"></div>
          <div className="container mx-auto px-4 max-w-7xl relative z-10">
            <div className="flex flex-col lg:flex-row items-center gap-16">
              <div className="lg:w-1/2">
                <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#163E6B]/10 dark:bg-[#D4A72C]/10 border border-[#163E6B]/20 dark:border-[#D4A72C]/20 mb-6">
                  <Sparkles className="w-4 h-4 text-[#163E6B] dark:text-[#D4A72C]" />
                  <span className="text-[10px] font-bold uppercase tracking-widest text-[#163E6B] dark:text-[#D4A72C]">
                    AI POWERED
                  </span>
                </div>
                <h2 className="text-3xl md:text-4xl font-[900] text-slate-900 dark:text-white tracking-tight mb-6">Don't Just Read. <span className="text-[#163E6B] dark:text-[#D4A72C]">Understand.</span></h2>
                <p className="text-lg text-slate-600 dark:text-slate-300 font-[500] mb-10 leading-relaxed">
                  Use AI assistance to simplify difficult concepts, explain unfamiliar topics, and connect your notes with your preparation.
                </p>
                
                <div className="flex flex-col sm:flex-row gap-4 items-center sm:items-start text-sm font-[700] text-slate-800 dark:text-slate-200">
                  <div className="flex items-center gap-3 bg-slate-50 dark:bg-white/5 px-4 py-3 rounded-[12px] border border-slate-200 dark:border-white/10 w-full sm:w-auto justify-center">
                    Read Note <ChevronRight className="w-4 h-4 text-slate-400" />
                  </div>
                  <div className="flex items-center gap-3 bg-[#163E6B]/5 dark:bg-[#D4A72C]/10 px-4 py-3 rounded-[12px] border border-[#163E6B]/20 dark:border-[#D4A72C]/30 w-full sm:w-auto justify-center">
                    <Sparkles className="w-4 h-4 text-[#163E6B] dark:text-[#D4A72C]" /> Ask AI <ChevronRight className="w-4 h-4 text-slate-400" />
                  </div>
                  <div className="flex items-center gap-3 bg-slate-50 dark:bg-white/5 px-4 py-3 rounded-[12px] border border-slate-200 dark:border-white/10 w-full sm:w-auto justify-center">
                    Understand
                  </div>
                </div>

                <div className="mt-10">
                  <Button className="h-12 px-8 rounded-[10px] bg-[#163E6B] hover:bg-[#163E6B]/90 text-white font-[700] dark:bg-[#D4A72C] dark:hover:bg-[#D4A72C]/90 dark:text-[#0A1118]">
                    Explore AI Learning <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </div>
              </div>
              
              <div className="lg:w-1/2 w-full">
                <div className="bg-slate-50 dark:bg-[#0A1118] border border-slate-200 dark:border-white/10 rounded-[20px] p-6 shadow-xl relative">
                  <div className="absolute -top-4 -right-4 w-12 h-12 bg-gradient-to-br from-[#163E6B] to-[#0A1118] dark:from-[#D4A72C] dark:to-[#8C6D1D] rounded-full flex items-center justify-center shadow-lg border-2 border-white dark:border-[#0A1118]">
                    <BrainCircuit className="w-6 h-6 text-white" />
                  </div>
                  
                  <div className="space-y-4">
                    <div className="bg-white dark:bg-white/5 border border-slate-100 dark:border-white/5 rounded-[12px] p-4 text-sm text-slate-700 dark:text-slate-300">
                      <p className="font-[600] text-slate-900 dark:text-white mb-1">You highlighted:</p>
                      <p className="italic border-l-2 border-yellow-400 pl-3">"The constitution establishes a federal structure with three tiers of government."</p>
                    </div>
                    
                    <div className="flex gap-3 justify-end">
                      <div className="bg-[#163E6B] dark:bg-[#D4A72C] text-white dark:text-[#0A1118] px-4 py-2.5 rounded-[16px] rounded-tr-[4px] text-sm font-[500] max-w-[80%] shadow-sm">
                        Explain this concept with an example related to Section Officer exams.
                      </div>
                    </div>
                    
                    <div className="flex gap-3">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#163E6B] to-[#0A1118] flex items-center justify-center shrink-0">
                        <Sparkles className="w-4 h-4 text-white" />
                      </div>
                      <div className="bg-white dark:bg-white/10 border border-slate-200 dark:border-white/5 text-slate-700 dark:text-slate-300 px-4 py-3 rounded-[16px] rounded-tl-[4px] text-sm leading-relaxed max-w-[90%] shadow-sm">
                        Certainly! In Nepal's three-tier federal structure, power is divided between the Federal, Provincial, and Local governments. <br/><br/>
                        For a Section Officer, you might deal with policy coordination between these levels. For example, health policy might be directed centrally (Federal), but implementation and staffing are managed by Provincial or Local bodies depending on the scale of the facility.
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* 10. QUICK REVISION SECTION & 11. RECENTLY UPDATED */}
        <section className="py-16 bg-slate-50 dark:bg-[#0A1118]">
          <div className="container mx-auto px-4 max-w-7xl">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
              
              {/* Quick Revision */}
              <div>
                <div className="flex items-center gap-3 mb-8">
                  <div className="w-10 h-10 rounded-full bg-orange-100 dark:bg-orange-500/20 flex items-center justify-center">
                    <Zap className="w-5 h-5 text-orange-600 dark:text-orange-400" />
                  </div>
                  <h2 className="text-2xl font-[800] text-slate-900 dark:text-white tracking-tight">Need A Quick Revision?</h2>
                </div>
                
                <div className="space-y-4">
                  {notes.filter(n => n.readingTime < 20).slice(0, 4).map(note => (
                    <div key={`qr-${note.id}`} className="group flex items-center justify-between p-4 bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-[16px] hover:border-[#163E6B]/30 dark:hover:border-white/30 transition-colors cursor-pointer" onClick={() => openPreview(note)}>
                      <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-[10px] bg-slate-100 dark:bg-white/10 flex items-center justify-center shrink-0 group-hover:bg-[#163E6B] dark:group-hover:bg-[#D4A72C] transition-colors">
                          <BookOpen className="w-5 h-5 text-slate-400 group-hover:text-white dark:group-hover:text-[#0A1118] transition-colors" />
                        </div>
                        <div>
                          <h4 className="text-sm font-[700] text-slate-900 dark:text-white line-clamp-1">{note.title}</h4>
                          <span className="text-xs text-slate-500 font-[500]">{note.subject}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 shrink-0">
                        <span className="text-xs font-[700] text-[#163E6B] dark:text-[#D4A72C] bg-[#163E6B]/10 dark:bg-[#D4A72C]/10 px-2 py-1 rounded-md">{note.readingTime} min</span>
                        <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-slate-900 dark:group-hover:text-white transition-colors" />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Recently Updated */}
              <div>
                <div className="flex items-center gap-3 mb-8">
                  <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-500/20 flex items-center justify-center">
                    <Clock className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  </div>
                  <h2 className="text-2xl font-[800] text-slate-900 dark:text-white tracking-tight">Recently Updated</h2>
                </div>
                
                <div className="space-y-4">
                  {notes.slice(0, 4).map(note => (
                    <div key={`ru-${note.id}`} className="group flex flex-col p-4 bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-[16px] hover:border-slate-300 dark:hover:border-white/30 transition-colors cursor-pointer" onClick={() => openPreview(note)}>
                      <div className="flex justify-between items-start mb-2">
                        <h4 className="text-sm font-[700] text-slate-900 dark:text-white line-clamp-1 group-hover:text-[#163E6B] dark:group-hover:text-[#D4A72C] transition-colors">{note.title}</h4>
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider shrink-0">{note.updatedAt}</span>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-slate-500 font-[500]">
                        <span>{note.subject}</span>
                        <div className="w-1 h-1 rounded-full bg-slate-300 dark:bg-white/20"></div>
                        <span>{note.type}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              
            </div>
          </div>
        </section>

        {/* 12. STUDY PATH CONNECTION */}
        <section className="py-20 border-t border-slate-200 dark:border-white/5 bg-white dark:bg-[#060B11]">
          <div className="container mx-auto px-4 text-center">
            <h2 className="text-3xl font-[800] text-slate-900 dark:text-white tracking-tight mb-16">From Notes To Practice</h2>
            
            <div className="flex flex-col md:flex-row items-center justify-center gap-4 md:gap-2 max-w-5xl mx-auto mb-12">
              {[
                { label: "Read Notes", icon: BookOpen, desc: "Build foundation" },
                { label: "Understand", icon: BrainCircuit, desc: "Internalize concepts" },
                { label: "Practice Questions", icon: Target, desc: "Test knowledge" },
                { label: "Take Mock Exam", icon: FileText, desc: "Simulate test" },
                { label: "Analyze Results", icon: BarChart2, desc: "Identify gaps" }
              ].map((step, idx, arr) => (
                <React.Fragment key={idx}>
                  <div className="flex flex-col items-center group w-40">
                    <div className="w-16 h-16 rounded-full bg-slate-50 dark:bg-white/5 border border-slate-200 dark:border-white/10 flex items-center justify-center mb-4 group-hover:border-[#163E6B] dark:group-hover:border-[#D4A72C] transition-colors">
                      <step.icon className="w-6 h-6 text-slate-600 dark:text-slate-400 group-hover:text-[#163E6B] dark:group-hover:text-[#D4A72C] transition-colors" />
                    </div>
                    <div className="text-sm font-[700] text-slate-900 dark:text-white mb-1">{step.label}</div>
                    <div className="text-xs text-slate-500">{step.desc}</div>
                  </div>
                  {idx < arr.length - 1 && (
                    <div className="hidden md:block w-8 h-px bg-slate-300 dark:bg-white/20 -mt-10"></div>
                  )}
                  {idx < arr.length - 1 && (
                    <ChevronRight className="md:hidden w-5 h-5 text-slate-300 dark:text-white/20 my-2" />
                  )}
                </React.Fragment>
              ))}
            </div>

            <Link href="/practice">
              <Button className="h-12 px-8 rounded-[12px] bg-[#163E6B] hover:bg-[#163E6B]/90 text-white font-[700] dark:bg-white dark:hover:bg-slate-200 dark:text-[#0A1118]">
                Start Practicing <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </Link>
          </div>
        </section>

        {/* 16. FINAL CTA */}
        <section className="py-24 relative overflow-hidden bg-[#163E6B] dark:bg-transparent dark:border-t dark:border-white/10">
          <div className="absolute inset-0 z-0 pointer-events-none hidden dark:block">
            <div className="absolute inset-0 bg-gradient-to-b from-[#0A1118] to-[#060B11]"></div>
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom,#D4A72C_0%,transparent_60%)] opacity-10"></div>
          </div>
          
          <div className="container mx-auto px-4 relative z-10 text-center max-w-3xl">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/10 border border-white/20 backdrop-blur-md mb-6 shadow-sm">
              <span className="text-[10px] font-bold uppercase tracking-widest text-white dark:text-[#D4A72C]">
                BUILD YOUR KNOWLEDGE
              </span>
            </div>
            <h2 className="text-3xl md:text-5xl font-[900] text-white tracking-tight mb-6 leading-tight">
              Read Less Randomly.<br/>Prepare More Strategically.
            </h2>
            <p className="text-lg md:text-xl text-white/80 font-[500] mb-10 leading-relaxed max-w-2xl mx-auto">
              Organize your preparation with structured notes, practice questions, examinations, and AI-powered learning tools.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href="/courses" className="w-full sm:w-auto">
                <Button className="w-full h-14 px-8 rounded-[12px] bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] font-[800] text-[16px] shadow-[0_0_20px_rgba(212,167,44,0.3)]">
                  Explore Courses <ArrowRight className="w-5 h-5 ml-2" />
                </Button>
              </Link>
              <Link href="/practice" className="w-full sm:w-auto">
                <Button variant="outline" className="w-full h-14 px-8 rounded-[12px] border-white/20 bg-white/5 hover:bg-white/10 text-white font-[700] text-[16px] backdrop-blur-sm">
                  Start Practicing
                </Button>
              </Link>
            </div>
          </div>
        </section>

      </main>

      {/* NOTE PREVIEW DIALOG */}
      <Dialog open={!!previewNote} onOpenChange={(open) => !open && setPreviewNote(null)}>
        <DialogContent className="sm:max-w-xl bg-white dark:bg-[#0A1118] border border-slate-200 dark:border-white/10 p-0 overflow-hidden rounded-[20px]">
          {previewNote && (
            <>
              <div className={`h-24 w-full relative ${
                previewNote.materialType === "notes" || previewNote.materialType === "study_guide" ? "bg-gradient-to-br from-[#163E6B] to-[#0A1118]" :
                previewNote.materialType === "presentation" ? "bg-gradient-to-br from-[#D4A72C] to-[#8C6D1D]" :
                "bg-gradient-to-br from-slate-700 to-slate-900"
              }`}>
                <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff1a_1px,transparent_1px),linear-gradient(to_bottom,#ffffff1a_1px,transparent_1px)] bg-[size:16px_16px]"></div>
              </div>

              <div className="px-6 py-6 sm:px-8">
                <DialogHeader className="mb-6 text-left">
                  <DialogTitle className="text-2xl font-[800] text-slate-900 dark:text-white leading-tight mb-2">
                    {previewNote.title}
                  </DialogTitle>
                  <DialogDescription className="text-slate-500 font-[500] text-[15px]">
                    {previewNote.description || `Access structured materials and prepare effectively for your ${previewNote.exam} examinations.`}
                  </DialogDescription>
                </DialogHeader>

                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div className="bg-slate-50 dark:bg-white/5 rounded-[12px] p-3 border border-slate-100 dark:border-white/5">
                    <div className="text-xs text-slate-500 font-[500] mb-1">Subject</div>
                    <div className="text-sm font-[700] text-slate-900 dark:text-white">{previewNote.subject}</div>
                  </div>
                  <div className="bg-slate-50 dark:bg-white/5 rounded-[12px] p-3 border border-slate-100 dark:border-white/5">
                    <div className="text-xs text-slate-500 font-[500] mb-1">Material Type</div>
                    <div className="text-sm font-[700] text-slate-900 dark:text-white">{previewNote.type}</div>
                  </div>
                  <div className="bg-slate-50 dark:bg-white/5 rounded-[12px] p-3 border border-slate-100 dark:border-white/5">
                    <div className="text-xs text-slate-500 font-[500] mb-1">Difficulty</div>
                    <div className="text-sm font-[700] text-slate-900 dark:text-white">{previewNote.difficulty}</div>
                  </div>
                  <div className="bg-slate-50 dark:bg-white/5 rounded-[12px] p-3 border border-slate-100 dark:border-white/5">
                    <div className="text-xs text-slate-500 font-[500] mb-1">Reading Time</div>
                    <div className="text-sm font-[700] text-slate-900 dark:text-white">{previewNote.readingTime} minutes</div>
                  </div>
                </div>

                <div className="mb-8">
                  <div className="text-xs font-[500] text-slate-400">
                    Published: {previewNote.updatedAt}
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row gap-3">
                  <Link href="/login" className="flex-1">
                    <Button className="w-full h-12 rounded-[10px] font-[700] text-[15px] bg-[#163E6B] hover:bg-[#163E6B]/90 text-white dark:bg-white dark:hover:bg-slate-200 dark:text-[#0A1118]">
                      <BookOpen className="w-4 h-4 mr-2" /> Read Notes
                    </Button>
                  </Link>
                  <Button
                    variant="outline"
                    className="h-12 px-6 rounded-[10px] border-slate-200 dark:border-white/10 bg-transparent hover:bg-slate-50 dark:hover:bg-white/5 text-slate-700 dark:text-white font-[600]"
                    onClick={(e) => toggleSave(e, previewNote.id)}
                  >
                    <Bookmark className="w-4 h-4 mr-2 text-slate-500" /> Save For Later
                  </Button>
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* AUTH/PREMIUM PROMPT DIALOG */}
      <Dialog open={showAuthPrompt} onOpenChange={setShowAuthPrompt}>
        <DialogContent className="sm:max-w-md bg-white dark:bg-[#0A1118] border border-slate-200 dark:border-white/10 rounded-[20px] text-center p-8">
          <div className="w-16 h-16 rounded-full bg-gradient-to-br from-[#163E6B] to-[#0A1118] dark:from-[#D4A72C] dark:to-[#8C6D1D] mx-auto flex items-center justify-center shadow-lg mb-6">
            <Lock className="w-8 h-8 text-white" />
          </div>
          <DialogTitle className="text-2xl font-[800] text-slate-900 dark:text-white mb-2">
            Unlock This Study Material
          </DialogTitle>
          <DialogDescription className="text-slate-500 font-[500] text-base mb-8">
            Access premium study materials, expert notes, and continue your structured preparation with LoksewaAI.
          </DialogDescription>
          <div className="flex flex-col gap-3">
            <Link href="/courses" className="w-full">
              <Button className="w-full h-12 rounded-[10px] font-[700] bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118]">
                View Plans <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </Link>
            <Link href="/login" className="w-full">
              <Button variant="outline" className="w-full h-12 rounded-[10px] font-[600] border-slate-200 dark:border-white/10">
                Log In
              </Button>
            </Link>
          </div>
        </DialogContent>
      </Dialog>

    </div>
  );
}
