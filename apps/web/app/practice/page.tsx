"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  Search, SlidersHorizontal, ArrowRight, BookOpen, Layers,
  Trophy, History, Target, Zap, Clock, BrainCircuit,
  BarChart2, CheckCircle2, TrendingUp, AlertCircle, FileText, Activity, Loader2
} from "lucide-react";
import { publicApi, type PublicPracticeSubject, type PublicPracticeSet } from "@/lib/api/public-api";

export default function PracticePage() {
  const [activeFilter, setActiveFilter] = useState("All");
  const [subjects, setSubjects] = useState<PublicPracticeSubject[]>([]);
  const [practiceSets, setPracticeSets] = useState<PublicPracticeSet[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    Promise.all([publicApi.getPracticeSubjects(), publicApi.getPracticeSets()]).then(([subjectsData, setsData]) => {
      if (!mounted) return;
      setSubjects(subjectsData || []);
      setPracticeSets(setsData || []);
      setIsLoading(false);
    });
    return () => { mounted = false; };
  }, []);

  const filteredSets = practiceSets.filter(
    (s) => activeFilter === "All" || s.difficulty.toLowerCase() === activeFilter.toLowerCase()
  );

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-[#0A1118]">
      {/* 1. HERO SECTION */}
      <section className="relative pt-32 pb-20 md:pt-40 md:pb-24 overflow-hidden">
        {/* Subtle premium background visual */}
        <div className="absolute inset-0 z-0 pointer-events-none">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,#163E6B_0%,transparent_70%)] opacity-20 dark:opacity-40"></div>
          <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-[#D4A72C]/10 rounded-full blur-[100px] mix-blend-screen hidden dark:block"></div>
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#00000003_1px,transparent_1px),linear-gradient(to_bottom,#00000003_1px,transparent_1px)] dark:bg-[linear-gradient(to_right,#ffffff03_1px,transparent_1px),linear-gradient(to_bottom,#ffffff03_1px,transparent_1px)] bg-[size:40px_40px]"></div>
        </div>

        <div className="container mx-auto px-4 relative z-10 max-w-[900px] text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#163E6B]/10 dark:bg-[#D4A72C]/10 border border-[#163E6B]/20 dark:border-[#D4A72C]/20 backdrop-blur-md mb-6 shadow-sm">
            <span className="text-[10px] font-bold uppercase tracking-widest text-[#163E6B] dark:text-[#D4A72C]">
              SMART PRACTICE · BETTER PREPARATION
            </span>
          </div>

          <h1 className="text-4xl md:text-5xl lg:text-6xl font-[900] tracking-tight text-slate-900 dark:text-white mb-6 leading-tight">
            Practice Smarter. <span className="text-[#D4A72C]">Prepare Better.</span>
          </h1>

          <p className="text-lg md:text-xl text-slate-600 dark:text-slate-300 max-w-2xl mx-auto leading-relaxed mb-10 font-[500]">
            Challenge yourself with topic-wise questions, practice sets, and exam-style tests designed around the Loksewa syllabus.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 max-w-2xl mx-auto mb-10">
            <div className="relative w-full">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
              <input 
                type="text" 
                placeholder="Search questions, subjects, topics, or practice sets..." 
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

          <div className="flex flex-wrap items-center justify-center gap-6 text-sm font-[600] text-slate-600 dark:text-slate-400">
            <div className="flex items-center gap-2">
              <Target className="w-4 h-4 text-[#163E6B] dark:text-[#D4A72C]" />
              <span>10K+ Questions</span>
            </div>
            <div className="hidden sm:block w-1 h-1 rounded-full bg-slate-300 dark:bg-white/20"></div>
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-[#163E6B] dark:text-[#D4A72C]" />
              <span>50+ Practice Sets</span>
            </div>
            <div className="hidden sm:block w-1 h-1 rounded-full bg-slate-300 dark:bg-white/20"></div>
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-[#163E6B] dark:text-[#D4A72C]" />
              <span>Multiple Difficulty Levels</span>
            </div>
          </div>
        </div>
      </section>

      {/* 2. PRACTICE TYPE SELECTOR */}
      <section className="py-16 border-y border-slate-200 dark:border-white/5 bg-white dark:bg-[#0B1521]">
        <div className="container mx-auto px-4 max-w-[1200px]">
          <h2 className="text-2xl md:text-3xl font-[900] text-slate-900 dark:text-white mb-10 text-center">Choose Your Practice Mode</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {/* Topic Practice */}
            <div className="group p-8 rounded-[20px] bg-slate-50 dark:bg-[#0A1118] border border-slate-200 dark:border-white/5 hover:border-[#163E6B]/30 dark:hover:border-white/20 hover:shadow-lg transition-all duration-300 relative overflow-hidden">
              <div className="w-14 h-14 rounded-[12px] bg-[#163E6B]/10 dark:bg-white/10 flex items-center justify-center mb-6 text-[#163E6B] dark:text-[#D4A72C]">
                <BookOpen className="w-7 h-7" />
              </div>
              <h3 className="text-xl font-[800] text-slate-900 dark:text-white mb-3">Topic Practice</h3>
              <p className="text-sm font-[500] text-slate-600 dark:text-slate-400 leading-relaxed mb-6">
                Practice specific topics from the Loksewa syllabus. Focus on what matters.
              </p>
              <div className="flex items-center justify-between mt-auto">
                <span className="text-xs font-[700] text-slate-500 uppercase tracking-wider">4.5K+ Qs</span>
                <span className="text-[14px] font-[700] flex items-center gap-1 text-[#163E6B] dark:text-[#D4A72C] group-hover:translate-x-1 transition-transform">
                  Practice Topics <ArrowRight className="w-4 h-4 ml-1" />
                </span>
              </div>
            </div>

            {/* Practice Sets */}
            <div className="group p-8 rounded-[20px] bg-slate-50 dark:bg-[#0A1118] border border-slate-200 dark:border-white/5 hover:border-[#163E6B]/30 dark:hover:border-white/20 hover:shadow-lg transition-all duration-300 relative overflow-hidden">
              <div className="w-14 h-14 rounded-[12px] bg-[#163E6B]/10 dark:bg-white/10 flex items-center justify-center mb-6 text-[#163E6B] dark:text-[#D4A72C]">
                <Layers className="w-7 h-7" />
              </div>
              <h3 className="text-xl font-[800] text-slate-900 dark:text-white mb-3">Practice Sets</h3>
              <p className="text-sm font-[500] text-slate-600 dark:text-slate-400 leading-relaxed mb-6">
                Solve curated sets of questions grouped by subject and difficulty.
              </p>
              <div className="flex items-center justify-between mt-auto">
                <span className="text-xs font-[700] text-slate-500 uppercase tracking-wider">50+ Sets</span>
                <span className="text-[14px] font-[700] flex items-center gap-1 text-[#163E6B] dark:text-[#D4A72C] group-hover:translate-x-1 transition-transform">
                  Explore Sets <ArrowRight className="w-4 h-4 ml-1" />
                </span>
              </div>
            </div>

            {/* Model Exams */}
            <div className="group p-8 rounded-[20px] bg-slate-50 dark:bg-[#0A1118] border border-slate-200 dark:border-white/5 hover:border-[#163E6B]/30 dark:hover:border-white/20 hover:shadow-lg transition-all duration-300 relative overflow-hidden">
              <div className="w-14 h-14 rounded-[12px] bg-[#163E6B]/10 dark:bg-white/10 flex items-center justify-center mb-6 text-[#163E6B] dark:text-[#D4A72C]">
                <Trophy className="w-7 h-7" />
              </div>
              <h3 className="text-xl font-[800] text-slate-900 dark:text-white mb-3">Model Exams</h3>
              <p className="text-sm font-[500] text-slate-600 dark:text-slate-400 leading-relaxed mb-6">
                Experience a complete exam-style environment with timer and full scoring.
              </p>
              <div className="flex items-center justify-between mt-auto">
                <span className="text-xs font-[700] text-slate-500 uppercase tracking-wider">Hard</span>
                <span className="text-[14px] font-[700] flex items-center gap-1 text-[#163E6B] dark:text-[#D4A72C] group-hover:translate-x-1 transition-transform">
                  Take Exam <ArrowRight className="w-4 h-4 ml-1" />
                </span>
              </div>
            </div>

            {/* Previous Questions */}
            <div className="group p-8 rounded-[20px] bg-slate-50 dark:bg-[#0A1118] border border-slate-200 dark:border-white/5 hover:border-[#163E6B]/30 dark:hover:border-white/20 hover:shadow-lg transition-all duration-300 relative overflow-hidden">
              <div className="w-14 h-14 rounded-[12px] bg-[#163E6B]/10 dark:bg-white/10 flex items-center justify-center mb-6 text-[#163E6B] dark:text-[#D4A72C]">
                <History className="w-7 h-7" />
              </div>
              <h3 className="text-xl font-[800] text-slate-900 dark:text-white mb-3">Previous Questions</h3>
              <p className="text-sm font-[500] text-slate-600 dark:text-slate-400 leading-relaxed mb-6">
                Practice questions based on previous Loksewa examination patterns.
              </p>
              <div className="flex items-center justify-between mt-auto">
                <span className="text-xs font-[700] text-slate-500 uppercase tracking-wider">Archive</span>
                <span className="text-[14px] font-[700] flex items-center gap-1 text-[#163E6B] dark:text-[#D4A72C] group-hover:translate-x-1 transition-transform">
                  Explore <ArrowRight className="w-4 h-4 ml-1" />
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 3. QUICK PRACTICE (Configuration Panel) */}
      <section className="py-20 relative overflow-hidden">
        <div className="container mx-auto px-4 max-w-[1000px]">
          <div className="bg-[#0B2545] dark:bg-[#0A1420] rounded-[24px] p-8 md:p-12 shadow-2xl relative overflow-hidden border border-[#163E6B]/30 dark:border-white/10">
            <div className="absolute top-0 right-0 w-64 h-64 bg-[#D4A72C]/10 rounded-full blur-[80px]"></div>
            
            <div className="relative z-10">
              <h2 className="text-2xl md:text-3xl font-[900] text-white mb-2">Start a Quick Practice</h2>
              <p className="text-[#D4A72C] font-[600] mb-8">Configure your ideal practice session in seconds.</p>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="flex flex-col gap-2">
                  <label className="text-xs font-[700] text-slate-300 uppercase tracking-wider">Exam</label>
                  <select className="h-12 px-4 rounded-[10px] bg-white/10 border border-white/20 text-white font-[500] focus:outline-none focus:ring-2 focus:ring-[#D4A72C] appearance-none cursor-pointer">
                    <option value="" className="text-slate-900">All Exams</option>
                    <option value="section-officer" className="text-slate-900">Section Officer</option>
                    <option value="nayab-subba" className="text-slate-900">Nayab Subba</option>
                    <option value="kharidar" className="text-slate-900">Kharidar</option>
                  </select>
                </div>

                <div className="flex flex-col gap-2">
                  <label className="text-xs font-[700] text-slate-300 uppercase tracking-wider">Subject</label>
                  <select className="h-12 px-4 rounded-[10px] bg-white/10 border border-white/20 text-white font-[500] focus:outline-none focus:ring-2 focus:ring-[#D4A72C] appearance-none cursor-pointer">
                    <option value="" className="text-slate-900">Select Subject</option>
                    <option value="gk" className="text-slate-900">General Knowledge</option>
                    <option value="constitution" className="text-slate-900">Constitution</option>
                    <option value="public-admin" className="text-slate-900">Public Administration</option>
                  </select>
                </div>

                <div className="flex flex-col gap-2">
                  <label className="text-xs font-[700] text-slate-300 uppercase tracking-wider">Difficulty</label>
                  <select className="h-12 px-4 rounded-[10px] bg-white/10 border border-white/20 text-white font-[500] focus:outline-none focus:ring-2 focus:ring-[#D4A72C] appearance-none cursor-pointer">
                    <option value="mixed" className="text-slate-900">Mixed</option>
                    <option value="easy" className="text-slate-900">Easy</option>
                    <option value="medium" className="text-slate-900">Medium</option>
                    <option value="hard" className="text-slate-900">Hard</option>
                  </select>
                </div>

                <div className="flex flex-col gap-2">
                  <label className="text-xs font-[700] text-slate-300 uppercase tracking-wider">Questions</label>
                  <select className="h-12 px-4 rounded-[10px] bg-white/10 border border-white/20 text-white font-[500] focus:outline-none focus:ring-2 focus:ring-[#D4A72C] appearance-none cursor-pointer">
                    <option value="10" className="text-slate-900">10 Questions</option>
                    <option value="20" className="text-slate-900">20 Questions</option>
                    <option value="30" className="text-slate-900">30 Questions</option>
                    <option value="50" className="text-slate-900">50 Questions</option>
                  </select>
                </div>
              </div>

              <div className="mt-8 flex justify-end">
                <Button className="h-14 px-8 rounded-[12px] bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] font-[800] text-[16px] shadow-[0_0_20px_rgba(212,167,44,0.3)] w-full md:w-auto">
                  Start Practice <ArrowRight className="w-5 h-5 ml-2" />
                </Button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 5. DIFFICULTY FILTER & 4. FEATURED PRACTICE SETS */}
      <section className="py-16 bg-white dark:bg-[#0A1118] border-t border-slate-200 dark:border-white/5">
        <div className="container mx-auto px-4 max-w-[1200px]">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-10 gap-6">
            <div>
              <h2 className="text-3xl font-[900] text-slate-900 dark:text-white mb-2">Popular Practice Sets</h2>
              <p className="text-slate-600 dark:text-slate-400 font-[500]">Challenge yourself with carefully organized question sets.</p>
            </div>
            
            <div className="flex flex-col sm:flex-row items-center gap-4 w-full md:w-auto">
              <div className="flex bg-slate-100 dark:bg-white/5 p-1 rounded-[10px] border border-slate-200 dark:border-white/10">
                {["All", "Easy", "Medium", "Hard"].map((filter) => (
                  <button
                    key={filter}
                    onClick={() => setActiveFilter(filter)}
                    className={`px-4 py-2 text-sm font-[600] rounded-[6px] transition-all ${
                      activeFilter === filter 
                        ? "bg-white dark:bg-[#163E6B] text-slate-900 dark:text-white shadow-sm border border-slate-200 dark:border-white/10" 
                        : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                    }`}
                  >
                    {filter}
                  </button>
                ))}
              </div>
              <select className="h-10 px-4 rounded-[10px] bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-200 text-sm font-[600] focus:outline-none">
                <option>Most Popular</option>
                <option>Newest</option>
                <option>Most Questions</option>
                <option>Highest Difficulty</option>
              </select>
            </div>
          </div>

          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
          ) : filteredSets.length === 0 ? (
            <p className="text-slate-500 font-[500]">No practice sets have been published yet. Check back soon.</p>
          ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {filteredSets.map((set) => (
              <div key={set.id} className="p-6 rounded-[16px] bg-slate-50 dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 hover:border-[#163E6B]/30 dark:hover:border-white/20 transition-all group">
                <h3 className="text-lg font-[800] text-slate-900 dark:text-white mb-1 group-hover:text-[#163E6B] dark:group-hover:text-[#D4A72C] transition-colors">
                  {set.name}
                </h3>
                <p className="text-sm font-[600] text-slate-500 dark:text-slate-400 mb-6">{set.exam || "General"} {set.subject ? `• ${set.subject}` : ""}</p>

                <div className="grid grid-cols-2 gap-4 mb-8">
                  <div className="bg-white dark:bg-[#0A1118] p-3 rounded-[8px] border border-slate-200 dark:border-white/5">
                    <div className="text-[11px] font-[700] text-slate-400 uppercase tracking-wider mb-1">Difficulty</div>
                    <div className={`text-sm font-[700] flex items-center gap-1 ${
                      set.difficulty === "Easy" ? "text-emerald-600 dark:text-emerald-400" :
                      set.difficulty === "Hard" ? "text-rose-600 dark:text-rose-400" :
                      "text-amber-600 dark:text-amber-400"
                    }`}>
                      {set.difficulty}
                    </div>
                  </div>
                  <div className="bg-white dark:bg-[#0A1118] p-3 rounded-[8px] border border-slate-200 dark:border-white/5">
                    <div className="text-[11px] font-[700] text-slate-400 uppercase tracking-wider mb-1">Estimated Time</div>
                    <div className="text-sm font-[700] text-slate-700 dark:text-slate-300 flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5" /> {set.estimatedMinutes} min
                    </div>
                  </div>
                  <div className="bg-white dark:bg-[#0A1118] p-3 rounded-[8px] border border-slate-200 dark:border-white/5 col-span-2">
                    <div className="text-[11px] font-[700] text-slate-400 uppercase tracking-wider mb-1">Questions</div>
                    <div className="text-sm font-[700] text-slate-700 dark:text-slate-300 flex items-center gap-1">
                      <FileText className="w-3.5 h-3.5" /> {set.questionsCount} Questions
                    </div>
                  </div>
                </div>

                <Link href="/login">
                  <Button className="w-full h-12 rounded-[10px] bg-slate-900 dark:bg-white text-white dark:text-[#0A1118] font-[700] hover:bg-slate-800 dark:hover:bg-slate-200 group-hover:bg-[#163E6B] dark:group-hover:bg-[#D4A72C] transition-colors">
                    Start Practice <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </Link>
              </div>
            ))}
          </div>
          )}
        </div>
      </section>

      {/* 6. SUBJECT PRACTICE & 7. DAILY CHALLENGE */}
      <section className="py-16 bg-slate-50 dark:bg-[#0A1118]">
        <div className="container mx-auto px-4 max-w-[1200px]">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            
            <div className="lg:col-span-2">
              <h2 className="text-2xl font-[900] text-slate-900 dark:text-white mb-8">Practice by Subject</h2>
              {isLoading ? (
                <div className="flex items-center justify-center py-10">
                  <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
                </div>
              ) : subjects.length === 0 ? (
                <p className="text-slate-500 font-[500]">No subjects with published questions yet.</p>
              ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {subjects.map((subject) => (
                  <div key={subject.id} className="flex items-center justify-between p-5 rounded-[16px] bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 hover:border-[#163E6B]/30 dark:hover:border-white/20 transition-all group cursor-pointer">
                    <div>
                      <h4 className="font-[800] text-slate-900 dark:text-white mb-1 group-hover:text-[#163E6B] dark:group-hover:text-[#D4A72C] transition-colors">{subject.name}</h4>
                      <p className="text-xs font-[600] text-slate-500">{subject.questionsCount} Questions</p>
                    </div>
                    <div className="w-8 h-8 rounded-full bg-slate-50 dark:bg-white/5 flex items-center justify-center text-slate-400 group-hover:text-[#163E6B] dark:group-hover:text-[#D4A72C] group-hover:bg-[#163E6B]/10 dark:group-hover:bg-[#D4A72C]/10 transition-all">
                      <ArrowRight className="w-4 h-4" />
                    </div>
                  </div>
                ))}
              </div>
              )}
            </div>

            <div className="lg:col-span-1">
              <div className="h-full bg-gradient-to-br from-[#0B2545] to-[#163E6B] dark:from-[#0A1420] dark:to-[#0A1118] rounded-[24px] p-8 border border-[#163E6B]/30 dark:border-white/10 relative overflow-hidden flex flex-col shadow-xl">
                <div className="absolute -top-10 -right-10 w-40 h-40 bg-[#D4A72C]/20 rounded-full blur-[40px]"></div>
                
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 border border-white/20 backdrop-blur-sm w-fit mb-6">
                  <Zap className="w-3.5 h-3.5 text-[#D4A72C]" />
                  <span className="text-[10px] font-bold uppercase tracking-widest text-white">Daily Challenge</span>
                </div>

                <h3 className="text-2xl font-[900] text-white mb-2 leading-tight">Can you solve today's challenge?</h3>
                <p className="text-slate-300 text-sm mb-8 font-[500]">Compete with thousands of aspirants and test your readiness.</p>

                <div className="bg-white/10 backdrop-blur-sm rounded-[16px] border border-white/10 p-4 mb-8">
                  <div className="flex justify-between items-center mb-4">
                    <span className="text-sm font-[600] text-slate-200">Questions</span>
                    <span className="text-sm font-[800] text-white">10</span>
                  </div>
                  <div className="flex justify-between items-center mb-4">
                    <span className="text-sm font-[600] text-slate-200">Time Limit</span>
                    <span className="text-sm font-[800] text-white">10 Minutes</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-[600] text-slate-200">Difficulty</span>
                    <span className="text-sm font-[800] text-[#D4A72C]">Mixed</span>
                  </div>
                </div>

                <Button className="w-full mt-auto h-14 rounded-[12px] bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] font-[800] shadow-[0_0_20px_rgba(212,167,44,0.3)]">
                  Start Today's Challenge <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* 8. AI PRACTICE SECTION */}
      <section className="py-20 border-y border-slate-200 dark:border-white/5 bg-white dark:bg-[#0B1521] overflow-hidden relative">
        <div className="absolute right-0 top-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blue-500/5 dark:bg-blue-500/10 rounded-full blur-[120px] pointer-events-none"></div>
        <div className="container mx-auto px-4 max-w-[1200px] relative z-10">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
            
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 mb-6">
                <BrainCircuit className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
                <span className="text-[10px] font-bold uppercase tracking-widest text-blue-700 dark:text-blue-400">
                  AI POWERED
                </span>
              </div>
              <h2 className="text-3xl md:text-4xl font-[900] text-slate-900 dark:text-white mb-6 leading-tight">
                Practice With Your Weak Areas
              </h2>
              <p className="text-lg text-slate-600 dark:text-slate-400 font-[500] leading-relaxed mb-10">
                LoksewaAI continuously analyzes your performance to identify the topics you struggle with, generating targeted practice sessions to strengthen them automatically.
              </p>
              
              <Button className="h-14 px-8 rounded-[12px] bg-[#0B2545] dark:bg-white text-white dark:text-[#0B2545] font-[800] hover:bg-[#163E6B] dark:hover:bg-slate-200 transition-colors">
                Try AI Practice <ArrowRight className="w-5 h-5 ml-2" />
              </Button>
            </div>

            <div className="bg-slate-50 dark:bg-[#0A1118] border border-slate-200 dark:border-white/10 rounded-[24px] p-8 shadow-sm">
              <div className="flex flex-col gap-6">
                
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-full bg-slate-200 dark:bg-white/10 flex items-center justify-center shrink-0">
                    <BarChart2 className="w-5 h-5 text-slate-600 dark:text-slate-300" />
                  </div>
                  <div>
                    <h4 className="font-[800] text-slate-900 dark:text-white">Your Performance</h4>
                    <p className="text-sm text-slate-500 dark:text-slate-400">System tracks your accuracy per topic.</p>
                  </div>
                </div>

                <div className="w-px h-6 bg-slate-200 dark:bg-white/10 ml-6"></div>

                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-full bg-rose-100 dark:bg-rose-500/10 flex items-center justify-center shrink-0 border border-rose-200 dark:border-rose-500/20">
                    <AlertCircle className="w-5 h-5 text-rose-600 dark:text-rose-400" />
                  </div>
                  <div>
                    <h4 className="font-[800] text-slate-900 dark:text-white">Weak Topics Identified</h4>
                    <p className="text-sm text-slate-500 dark:text-slate-400">E.g., Constitution, Federal Structure.</p>
                  </div>
                </div>

                <div className="w-px h-6 bg-slate-200 dark:bg-white/10 ml-6"></div>

                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-full bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center shrink-0 border border-blue-200 dark:border-blue-500/20">
                    <BrainCircuit className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  </div>
                  <div>
                    <h4 className="font-[800] text-slate-900 dark:text-white">AI-Generated Practice</h4>
                    <p className="text-sm text-slate-500 dark:text-slate-400">Custom set focusing only on weak areas.</p>
                  </div>
                </div>

                <div className="w-px h-6 bg-slate-200 dark:bg-white/10 ml-6"></div>

                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-full bg-emerald-100 dark:bg-emerald-500/10 flex items-center justify-center shrink-0 border border-emerald-200 dark:border-emerald-500/20">
                    <TrendingUp className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                  </div>
                  <div>
                    <h4 className="font-[800] text-slate-900 dark:text-white">Improved Performance</h4>
                    <p className="text-sm text-slate-500 dark:text-slate-400">Master the topic and increase overall score.</p>
                  </div>
                </div>

              </div>
            </div>

          </div>
        </div>
      </section>

      {/* 9. PRACTICE FLOW */}
      <section className="py-20 bg-slate-50 dark:bg-[#0A1118]">
        <div className="container mx-auto px-4 max-w-[1200px]">
          <h2 className="text-2xl md:text-3xl font-[900] text-slate-900 dark:text-white mb-12 text-center">How Practice Works</h2>
          
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center relative gap-8 md:gap-0">
            {/* Desktop connecting line */}
            <div className="hidden md:block absolute top-6 left-[10%] right-[10%] h-px bg-slate-300 dark:bg-white/10 z-0"></div>

            <div className="relative z-10 flex flex-row md:flex-col items-center gap-6 md:gap-4 md:w-1/4">
              <div className="w-12 h-12 rounded-full bg-white dark:bg-[#0B1521] border-2 border-[#163E6B] dark:border-[#D4A72C] flex items-center justify-center font-[900] text-[#163E6B] dark:text-[#D4A72C] text-lg shadow-sm shrink-0">
                01
              </div>
              <div className="md:text-center">
                <h4 className="text-lg font-[800] text-slate-900 dark:text-white mb-1">Choose</h4>
                <p className="text-sm text-slate-600 dark:text-slate-400 font-[500]">Select your exam, subject, or topic.</p>
              </div>
            </div>

            <div className="relative z-10 flex flex-row md:flex-col items-center gap-6 md:gap-4 md:w-1/4">
              <div className="w-12 h-12 rounded-full bg-white dark:bg-[#0B1521] border-2 border-slate-300 dark:border-white/20 flex items-center justify-center font-[900] text-slate-500 dark:text-slate-400 text-lg shadow-sm shrink-0">
                02
              </div>
              <div className="md:text-center">
                <h4 className="text-lg font-[800] text-slate-900 dark:text-white mb-1">Practice</h4>
                <p className="text-sm text-slate-600 dark:text-slate-400 font-[500]">Solve carefully selected questions.</p>
              </div>
            </div>

            <div className="relative z-10 flex flex-row md:flex-col items-center gap-6 md:gap-4 md:w-1/4">
              <div className="w-12 h-12 rounded-full bg-white dark:bg-[#0B1521] border-2 border-slate-300 dark:border-white/20 flex items-center justify-center font-[900] text-slate-500 dark:text-slate-400 text-lg shadow-sm shrink-0">
                03
              </div>
              <div className="md:text-center">
                <h4 className="text-lg font-[800] text-slate-900 dark:text-white mb-1">Analyze</h4>
                <p className="text-sm text-slate-600 dark:text-slate-400 font-[500]">Review your answers and explanations.</p>
              </div>
            </div>

            <div className="relative z-10 flex flex-row md:flex-col items-center gap-6 md:gap-4 md:w-1/4">
              <div className="w-12 h-12 rounded-full bg-white dark:bg-[#0B1521] border-2 border-slate-300 dark:border-white/20 flex items-center justify-center font-[900] text-slate-500 dark:text-slate-400 text-lg shadow-sm shrink-0">
                04
              </div>
              <div className="md:text-center">
                <h4 className="text-lg font-[800] text-slate-900 dark:text-white mb-1">Improve</h4>
                <p className="text-sm text-slate-600 dark:text-slate-400 font-[500]">Focus on weak areas and practice again.</p>
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* 10. QUESTION PREVIEW & 11. RESULTS PREVIEW */}
      <section className="py-20 bg-white dark:bg-[#0B1521] border-y border-slate-200 dark:border-white/5">
        <div className="container mx-auto px-4 max-w-[1200px]">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
            
            {/* Question Preview */}
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-[6px] bg-slate-100 dark:bg-white/10 text-xs font-[700] text-slate-600 dark:text-slate-300 mb-6 uppercase tracking-wider">
                Sample Question
              </div>
              <div className="bg-slate-50 dark:bg-[#0A1118] border border-slate-200 dark:border-white/10 rounded-[20px] p-6 md:p-8 shadow-sm">
                <div className="flex justify-between items-center mb-6">
                  <span className="text-sm font-[800] text-slate-900 dark:text-white">Question 01</span>
                  <span className="text-xs font-[700] text-emerald-600 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/10 px-2 py-1 rounded-[6px]">Difficulty: Easy</span>
                </div>
                
                <p className="text-lg text-slate-800 dark:text-slate-200 font-[500] leading-relaxed mb-8">
                  Which of the following is a fundamental right guaranteed by the Constitution of Nepal?
                </p>

                <div className="space-y-3 mb-8">
                  <div className="p-4 rounded-[12px] border border-slate-200 dark:border-white/10 bg-white dark:bg-[#0B1521] text-slate-700 dark:text-slate-300 font-[500] text-sm flex items-center gap-3">
                    <div className="w-6 h-6 rounded-[6px] bg-slate-100 dark:bg-white/5 flex items-center justify-center text-xs font-[700]">A</div>
                    Right to equality
                  </div>
                  <div className="p-4 rounded-[12px] border border-slate-200 dark:border-white/10 bg-white dark:bg-[#0B1521] text-slate-700 dark:text-slate-300 font-[500] text-sm flex items-center gap-3">
                    <div className="w-6 h-6 rounded-[6px] bg-slate-100 dark:bg-white/5 flex items-center justify-center text-xs font-[700]">B</div>
                    Right to taxation
                  </div>
                  <div className="p-4 rounded-[12px] border border-slate-200 dark:border-white/10 bg-white dark:bg-[#0B1521] text-slate-700 dark:text-slate-300 font-[500] text-sm flex items-center gap-3">
                    <div className="w-6 h-6 rounded-[6px] bg-slate-100 dark:bg-white/5 flex items-center justify-center text-xs font-[700]">C</div>
                    Right to government employment
                  </div>
                  <div className="p-4 rounded-[12px] border border-slate-200 dark:border-white/10 bg-white dark:bg-[#0B1521] text-slate-700 dark:text-slate-300 font-[500] text-sm flex items-center gap-3">
                    <div className="w-6 h-6 rounded-[6px] bg-slate-100 dark:bg-white/5 flex items-center justify-center text-xs font-[700]">D</div>
                    Right to government housing
                  </div>
                </div>

                <Button variant="outline" className="w-full h-12 rounded-[10px] border-slate-300 dark:border-white/20 text-slate-700 dark:text-slate-200 font-[700] hover:bg-slate-100 dark:hover:bg-white/10">
                  Try This Question <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </div>
            </div>

            {/* Results Preview */}
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-[6px] bg-slate-100 dark:bg-white/10 text-xs font-[700] text-slate-600 dark:text-slate-300 mb-6 uppercase tracking-wider">
                Actionable Insights
              </div>
              <div className="bg-slate-50 dark:bg-[#0A1118] border border-slate-200 dark:border-white/10 rounded-[20px] p-6 md:p-8 shadow-sm h-full flex flex-col">
                <h3 className="text-xl font-[900] text-slate-900 dark:text-white mb-8">Practice Performance</h3>
                
                <div className="grid grid-cols-3 gap-4 mb-8">
                  <div className="flex flex-col items-center justify-center p-4 bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 rounded-[12px]">
                    <div className="text-2xl font-[900] text-[#163E6B] dark:text-[#D4A72C] mb-1">82%</div>
                    <div className="text-xs font-[600] text-slate-500 uppercase">Accuracy</div>
                  </div>
                  <div className="flex flex-col items-center justify-center p-4 bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 rounded-[12px]">
                    <div className="text-2xl font-[900] text-emerald-600 dark:text-emerald-400 mb-1">16<span className="text-lg text-slate-400">/20</span></div>
                    <div className="text-xs font-[600] text-slate-500 uppercase">Correct</div>
                  </div>
                  <div className="flex flex-col items-center justify-center p-4 bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 rounded-[12px]">
                    <div className="text-xl font-[900] text-slate-800 dark:text-slate-200 mb-1 mt-1">12<span className="text-sm font-[600]">m</span> 42<span className="text-sm font-[600]">s</span></div>
                    <div className="text-xs font-[600] text-slate-500 uppercase mt-1">Time</div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-6 mt-auto">
                  <div>
                    <h5 className="text-sm font-[800] text-slate-900 dark:text-white mb-3 flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-500"/> Strong Topics</h5>
                    <ul className="space-y-2">
                      <li className="text-sm font-[500] text-slate-600 dark:text-slate-400 bg-emerald-50 dark:bg-emerald-500/10 px-3 py-1.5 rounded-[6px] border border-emerald-100 dark:border-emerald-500/20">General Knowledge</li>
                      <li className="text-sm font-[500] text-slate-600 dark:text-slate-400 bg-emerald-50 dark:bg-emerald-500/10 px-3 py-1.5 rounded-[6px] border border-emerald-100 dark:border-emerald-500/20">Constitution</li>
                    </ul>
                  </div>
                  <div>
                    <h5 className="text-sm font-[800] text-slate-900 dark:text-white mb-3 flex items-center gap-2"><AlertCircle className="w-4 h-4 text-rose-500"/> Needs Practice</h5>
                    <ul className="space-y-2">
                      <li className="text-sm font-[500] text-slate-600 dark:text-slate-400 bg-rose-50 dark:bg-rose-500/10 px-3 py-1.5 rounded-[6px] border border-rose-100 dark:border-rose-500/20">Current Affairs</li>
                    </ul>
                  </div>
                </div>

              </div>
            </div>

          </div>
        </div>
      </section>

      {/* 12. LOGIN / ACCESS HANDLING */}
      <section className="py-20 bg-slate-100 dark:bg-[#0A1118]">
        <div className="container mx-auto px-4 max-w-[600px] text-center">
          <div className="w-16 h-16 rounded-full bg-[#163E6B]/10 dark:bg-[#D4A72C]/10 flex items-center justify-center mx-auto mb-6">
            <Target className="w-8 h-8 text-[#163E6B] dark:text-[#D4A72C]" />
          </div>
          <h2 className="text-2xl md:text-3xl font-[900] text-slate-900 dark:text-white mb-4">Ready to start your practice?</h2>
          <p className="text-slate-600 dark:text-slate-400 font-[500] mb-8">
            Create your account or log in to track your progress, access full practice sets, and unlock personalized AI insights.
          </p>
          <div className="flex justify-center gap-4">
            <Link href="/login">
              <Button variant="outline" className="h-12 px-8 rounded-[10px] border-slate-300 dark:border-white/20 text-slate-700 dark:text-slate-200 font-[700] hover:bg-slate-200 dark:hover:bg-white/10">
                Log In
              </Button>
            </Link>
            <Link href="/register">
              <Button className="h-12 px-8 rounded-[10px] bg-[#0B2545] dark:bg-white text-white dark:text-[#0A1118] font-[800] hover:bg-[#163E6B] dark:hover:bg-slate-200">
                Create Account
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* 13. PREMIUM CTA */}
      <section className="py-24 bg-[#0B2545] dark:bg-[#050C14] text-center relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom,#163E6B_0%,transparent_70%)] opacity-40"></div>
        <div className="container mx-auto px-4 max-w-[800px] relative z-10">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/10 border border-white/20 mb-6 backdrop-blur-sm">
            <span className="text-[10px] font-bold uppercase tracking-widest text-[#D4A72C]">
              READY TO TEST YOURSELF?
            </span>
          </div>
          
          <h2 className="text-4xl md:text-5xl font-[900] text-white mb-6 tracking-tight">
            Turn Knowledge Into Performance.
          </h2>
          
          <p className="text-lg md:text-xl text-slate-300 font-[500] mb-10 leading-relaxed">
            Practice consistently, understand your mistakes, and prepare with confidence using our comprehensive testing platform.
          </p>
          
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/courses">
              <Button variant="outline" className="h-14 px-8 rounded-[12px] bg-transparent border-white/30 text-white hover:bg-white/10 font-[700] text-[16px]">
                Explore Courses <ArrowRight className="w-5 h-5 ml-2" />
              </Button>
            </Link>
            <Link href="/practice">
              <Button className="h-14 px-8 rounded-[12px] bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] font-[800] text-[16px] shadow-[0_0_20px_rgba(212,167,44,0.3)]">
                Start Practicing
              </Button>
            </Link>
          </div>
        </div>
      </section>

    </div>
  );
}
