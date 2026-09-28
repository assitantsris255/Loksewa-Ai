"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Search, SlidersHorizontal, ArrowRight, Clock, Calendar,
  Target, Zap, BrainCircuit, BarChart2, CheckCircle2, AlertCircle,
  FileText, ShieldCheck, Trophy, Layers, PlayCircle, BookOpen, User, Sparkles, Activity, Loader2
} from "lucide-react";
import { publicApi, type PublicExamination } from "@/lib/api/public-api";

const STATUS_LABELS: Record<PublicExamination["status"], string> = {
  DRAFT: "Draft",
  UPCOMING: "Upcoming",
  LIVE: "Live",
  COMPLETED: "Completed",
};

export default function ExamsPage() {
  const [exams, setExams] = useState<PublicExamination[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedExam, setSelectedExam] = useState<PublicExamination | null>(null);

  useEffect(() => {
    let mounted = true;
    publicApi.getExaminations().then((data) => {
      if (!mounted) return;
      setExams(data || []);
      setIsLoading(false);
    });
    return () => { mounted = false; };
  }, []);

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-[#0A1118]">
      {/* 1. HERO SECTION */}
      <section className="relative pt-32 pb-20 md:pt-40 md:pb-24 overflow-hidden">
        {/* Subtle premium background visual */}
        <div className="absolute inset-0 z-0 pointer-events-none">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,#163E6B_0%,transparent_70%)] opacity-20 dark:opacity-50"></div>
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-slate-50/80 to-slate-50 dark:via-[#020611]/80 dark:to-[#0A1118]"></div>
          {/* Subtle grid */}
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#00000003_1px,transparent_1px),linear-gradient(to_bottom,#00000003_1px,transparent_1px)] dark:bg-[linear-gradient(to_right,#ffffff03_1px,transparent_1px),linear-gradient(to_bottom,#ffffff03_1px,transparent_1px)] bg-[size:40px_40px]"></div>
          <div className="absolute top-1/4 right-1/4 w-[400px] h-[400px] bg-[#D4A72C]/10 rounded-full blur-[120px] mix-blend-screen hidden dark:block"></div>
        </div>

        <div className="container mx-auto px-4 relative z-10 max-w-[900px] text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#163E6B]/10 dark:bg-white/10 border border-[#163E6B]/20 dark:border-white/20 backdrop-blur-md mb-6 shadow-sm">
            <span className="text-[10px] font-bold uppercase tracking-widest text-[#163E6B] dark:text-[#D4A72C]">
              EXAM SIMULATION · REAL PREPARATION
            </span>
          </div>

          <h1 className="text-4xl md:text-5xl lg:text-6xl font-[900] tracking-tight text-slate-900 dark:text-white mb-6 leading-tight">
            Test Yourself Like the <span className="text-[#D4A72C]">Real Exam.</span>
          </h1>

          <p className="text-lg md:text-xl text-slate-600 dark:text-slate-300 max-w-2xl mx-auto leading-relaxed mb-10 font-[500]">
            Experience structured Loksewa examinations with realistic timing, question patterns, instant results, and detailed performance analysis.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 max-w-2xl mx-auto mb-12">
            <Button className="h-14 px-8 rounded-[12px] bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] font-[800] text-[16px] shadow-[0_0_20px_rgba(212,167,44,0.3)] w-full sm:w-auto">
              Explore Exams <ArrowRight className="w-5 h-5 ml-2" />
            </Button>
            <Link href="/syllabus" className="w-full sm:w-auto">
              <Button variant="outline" className="h-14 px-8 rounded-[12px] border-slate-300 dark:border-white/20 bg-white/50 dark:bg-white/5 hover:bg-slate-100 dark:hover:bg-white/10 text-slate-700 dark:text-white font-[700] text-[16px] backdrop-blur-sm w-full">
                View Syllabus
              </Button>
            </Link>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-6 text-sm font-[600] text-slate-600 dark:text-slate-300">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-[#163E6B] dark:text-[#D4A72C]" />
              <span>50+ Model Exams</span>
            </div>
            <div className="hidden sm:block w-1 h-1 rounded-full bg-slate-300 dark:bg-white/20"></div>
            <div className="flex items-center gap-2">
              <Target className="w-4 h-4 text-[#163E6B] dark:text-[#D4A72C]" />
              <span>1,000+ Questions</span>
            </div>
            <div className="hidden sm:block w-1 h-1 rounded-full bg-slate-300 dark:bg-white/20"></div>
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-[#163E6B] dark:text-[#D4A72C]" />
              <span>Multiple Exam Levels</span>
            </div>
          </div>
        </div>
      </section>

      {/* 2. EXAM TYPE SELECTOR */}
      <section className="py-16 bg-white dark:bg-[#0B1521] border-y border-slate-200 dark:border-white/5 relative z-20">
        <div className="container mx-auto px-4 max-w-[1200px]">
          <h2 className="text-2xl md:text-3xl font-[900] text-slate-900 dark:text-white mb-10 text-center">Choose Your Exam Experience</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Practice Exam */}
            <div className="group p-8 rounded-[20px] bg-slate-50 dark:bg-[#0A1118] border border-slate-200 dark:border-white/5 hover:border-[#163E6B]/30 dark:hover:border-white/20 hover:shadow-xl transition-all duration-300 relative overflow-hidden flex flex-col h-full">
              <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 rounded-bl-[100px] pointer-events-none transition-all group-hover:bg-blue-500/10"></div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-[6px] bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 text-xs font-[800] uppercase tracking-wider mb-6 w-fit border border-blue-200 dark:border-blue-500/20">
                Flexible Timing
              </div>
              <h3 className="text-2xl font-[900] text-slate-900 dark:text-white mb-3 flex items-center gap-3">
                <BookOpen className="w-6 h-6 text-[#163E6B] dark:text-[#D4A72C]" /> Practice Exam
              </h3>
              <p className="text-sm font-[500] text-slate-600 dark:text-slate-400 leading-relaxed mb-6">
                Practice at your own pace and focus on learning. Receive instant feedback after each question.
              </p>
              <ul className="space-y-3 mb-8">
                <li className="flex items-center gap-2 text-sm font-[600] text-slate-700 dark:text-slate-300"><CheckCircle2 className="w-4 h-4 text-emerald-500" /> Flexible timing</li>
                <li className="flex items-center gap-2 text-sm font-[600] text-slate-700 dark:text-slate-300"><CheckCircle2 className="w-4 h-4 text-emerald-500" /> Instant feedback</li>
                <li className="flex items-center gap-2 text-sm font-[600] text-slate-700 dark:text-slate-300"><CheckCircle2 className="w-4 h-4 text-emerald-500" /> Detailed explanations</li>
              </ul>
              <Button className="w-full mt-auto h-12 rounded-[10px] bg-slate-900 dark:bg-white text-white dark:text-[#0A1118] font-[700] hover:bg-slate-800 dark:hover:bg-slate-200 group-hover:bg-[#163E6B] dark:group-hover:bg-[#D4A72C] transition-colors">
                Explore Practice Exams <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </div>

            {/* Model Exam */}
            <div className="group p-8 rounded-[20px] bg-gradient-to-b from-[#0B2545] to-[#163E6B] dark:from-[#0A1420] dark:to-[#0B1521] border border-[#163E6B]/40 dark:border-white/10 hover:shadow-xl transition-all duration-300 relative overflow-hidden flex flex-col h-full transform md:-translate-y-4">
              <div className="absolute top-0 right-0 w-32 h-32 bg-[#D4A72C]/10 rounded-bl-[100px] pointer-events-none transition-all group-hover:bg-[#D4A72C]/20"></div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-[6px] bg-white/10 text-white text-xs font-[800] uppercase tracking-wider mb-6 w-fit border border-white/20 backdrop-blur-sm">
                Fixed Exam Environment
              </div>
              <h3 className="text-2xl font-[900] text-white mb-3 flex items-center gap-3">
                <ShieldCheck className="w-6 h-6 text-[#D4A72C]" /> Model Exam
              </h3>
              <p className="text-sm font-[500] text-slate-300 leading-relaxed mb-6">
                Experience a realistic examination environment with fixed timing and strict simulation rules.
              </p>
              <ul className="space-y-3 mb-8">
                <li className="flex items-center gap-2 text-sm font-[600] text-slate-200"><CheckCircle2 className="w-4 h-4 text-[#D4A72C]" /> Fixed duration</li>
                <li className="flex items-center gap-2 text-sm font-[600] text-slate-200"><CheckCircle2 className="w-4 h-4 text-[#D4A72C]" /> Exam-style interface</li>
                <li className="flex items-center gap-2 text-sm font-[600] text-slate-200"><CheckCircle2 className="w-4 h-4 text-[#D4A72C]" /> Result after submission</li>
              </ul>
              <Button className="w-full mt-auto h-12 rounded-[10px] bg-[#D4A72C] text-[#0A1118] font-[800] hover:bg-[#D4A72C]/90 transition-colors shadow-[0_0_15px_rgba(212,167,44,0.3)] group-hover:shadow-[0_0_25px_rgba(212,167,44,0.5)]">
                Take Model Exam <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </div>

            {/* Topic-wise Exam */}
            <div className="group p-8 rounded-[20px] bg-slate-50 dark:bg-[#0A1118] border border-slate-200 dark:border-white/5 hover:border-[#163E6B]/30 dark:hover:border-white/20 hover:shadow-xl transition-all duration-300 relative overflow-hidden flex flex-col h-full">
              <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-bl-[100px] pointer-events-none transition-all group-hover:bg-emerald-500/10"></div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-[6px] bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 text-xs font-[800] uppercase tracking-wider mb-6 w-fit border border-emerald-200 dark:border-emerald-500/20">
                Target Your Weak Areas
              </div>
              <h3 className="text-2xl font-[900] text-slate-900 dark:text-white mb-3 flex items-center gap-3">
                <Target className="w-6 h-6 text-[#163E6B] dark:text-[#D4A72C]" /> Topic-wise Exam
              </h3>
              <p className="text-sm font-[500] text-slate-600 dark:text-slate-400 leading-relaxed mb-6">
                Select a specific subject or topic and test your understanding deeply.
              </p>
              <ul className="space-y-3 mb-8">
                <li className="flex items-center gap-2 text-sm font-[600] text-slate-700 dark:text-slate-300"><CheckCircle2 className="w-4 h-4 text-emerald-500" /> Subject selection</li>
                <li className="flex items-center gap-2 text-sm font-[600] text-slate-700 dark:text-slate-300"><CheckCircle2 className="w-4 h-4 text-emerald-500" /> Topic selection</li>
                <li className="flex items-center gap-2 text-sm font-[600] text-slate-700 dark:text-slate-300"><CheckCircle2 className="w-4 h-4 text-emerald-500" /> Difficulty control</li>
              </ul>
              <Button className="w-full mt-auto h-12 rounded-[10px] bg-slate-900 dark:bg-white text-white dark:text-[#0A1118] font-[700] hover:bg-slate-800 dark:hover:bg-slate-200 group-hover:bg-[#163E6B] dark:group-hover:bg-[#D4A72C] transition-colors">
                Explore Topic Exams <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* 3. EXAM SEARCH + FILTER */}
      <section className="py-12 bg-slate-50 dark:bg-[#0A1118]">
        <div className="container mx-auto px-4 max-w-[1200px]">
          <div className="bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/10 rounded-[20px] p-4 shadow-sm">
            
            <div className="relative mb-4">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
              <input 
                type="text" 
                placeholder="Search exams, subjects, papers..." 
                className="w-full h-14 pl-12 pr-4 rounded-[12px] border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-[#0A1118] text-slate-900 dark:text-white placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-[#D4A72C]/50 transition-all font-[500]"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3">
              <select className="h-12 px-4 rounded-[10px] bg-slate-50 dark:bg-[#0A1118] border border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-300 text-sm font-[600] focus:outline-none focus:ring-1 focus:ring-[#D4A72C] appearance-none cursor-pointer">
                <option value="">Exam Level</option>
                <option value="section-officer">Section Officer</option>
                <option value="nayab-subba">Nayab Subba</option>
                <option value="kharidar">Kharidar</option>
                <option value="other">Other</option>
              </select>

              <select className="h-12 px-4 rounded-[10px] bg-slate-50 dark:bg-[#0A1118] border border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-300 text-sm font-[600] focus:outline-none focus:ring-1 focus:ring-[#D4A72C] appearance-none cursor-pointer">
                <option value="">Exam Type</option>
                <option value="practice">Practice</option>
                <option value="model">Model</option>
                <option value="topic">Topic-wise</option>
              </select>

              <select className="h-12 px-4 rounded-[10px] bg-slate-50 dark:bg-[#0A1118] border border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-300 text-sm font-[600] focus:outline-none focus:ring-1 focus:ring-[#D4A72C] appearance-none cursor-pointer">
                <option value="">Difficulty</option>
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
                <option value="mixed">Mixed</option>
              </select>

              <select className="h-12 px-4 rounded-[10px] bg-slate-50 dark:bg-[#0A1118] border border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-300 text-sm font-[600] focus:outline-none focus:ring-1 focus:ring-[#D4A72C] appearance-none cursor-pointer">
                <option value="">Paper</option>
                <option value="paper-1">Paper I</option>
                <option value="paper-2">Paper II</option>
                <option value="paper-3">Paper III</option>
              </select>

              <select className="h-12 px-4 rounded-[10px] bg-slate-100 dark:bg-white/5 border border-slate-200 dark:border-white/10 text-slate-900 dark:text-white text-sm font-[700] focus:outline-none appearance-none cursor-pointer">
                <option>Most Popular</option>
                <option>Newest</option>
                <option>Highest Rated</option>
                <option>Most Questions</option>
              </select>
            </div>
            
          </div>
        </div>
      </section>

      {/* 4. FEATURED EXAM */}
      <section className="py-8 bg-slate-50 dark:bg-[#0A1118]">
        <div className="container mx-auto px-4 max-w-[1200px]">
          <div className="bg-[#0B2545] dark:bg-[#0A1420] rounded-[24px] overflow-hidden relative shadow-2xl border border-[#163E6B]/30 dark:border-white/10">
            {/* Background design */}
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_right_bottom,#163E6B_0%,transparent_60%)]"></div>
            <div className="absolute right-0 top-0 h-full w-1/2 bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] opacity-5 mix-blend-overlay"></div>
            <div className="absolute -right-20 -top-20 w-80 h-80 bg-[#D4A72C]/20 rounded-full blur-[80px]"></div>

            <div className="relative z-10 p-8 md:p-12 lg:flex justify-between items-center gap-12">
              <div className="lg:w-2/3">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-[6px] bg-[#D4A72C]/20 text-[#D4A72C] text-xs font-[800] uppercase tracking-wider mb-6 border border-[#D4A72C]/30">
                  <Sparkles className="w-3.5 h-3.5" /> FEATURED
                </div>
                
                <h2 className="text-3xl md:text-4xl font-[900] text-white mb-4">
                  Section Officer — Full Model Examination
                </h2>
                
                <p className="text-slate-300 font-[500] text-lg mb-8 max-w-2xl">
                  Experience a complete exam-style assessment covering multiple subjects based on the latest Loksewa syllabus. Test your readiness under real time constraints.
                </p>

                <div className="flex flex-wrap items-center gap-4 mb-8">
                  <div className="bg-white/10 backdrop-blur-sm border border-white/10 rounded-[10px] px-4 py-2 flex items-center gap-2">
                    <FileText className="w-4 h-4 text-[#D4A72C]" />
                    <span className="text-white font-[700] text-sm">100 Questions</span>
                  </div>
                  <div className="bg-white/10 backdrop-blur-sm border border-white/10 rounded-[10px] px-4 py-2 flex items-center gap-2">
                    <Clock className="w-4 h-4 text-[#D4A72C]" />
                    <span className="text-white font-[700] text-sm">90 Minutes</span>
                  </div>
                  <div className="bg-white/10 backdrop-blur-sm border border-white/10 rounded-[10px] px-4 py-2 flex items-center gap-2">
                    <Activity className="w-4 h-4 text-[#D4A72C]" />
                    <span className="text-white font-[700] text-sm">Mixed Difficulty</span>
                  </div>
                  <div className="bg-white/10 backdrop-blur-sm border border-white/10 rounded-[10px] px-4 py-2 flex items-center gap-2">
                    <Layers className="w-4 h-4 text-[#D4A72C]" />
                    <span className="text-white font-[700] text-sm">Paper I</span>
                  </div>
                </div>
              </div>

              <div className="lg:w-1/3 flex flex-col gap-4 mt-8 lg:mt-0">
                <Button className="w-full h-14 rounded-[12px] bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] font-[900] text-[16px] shadow-[0_0_20px_rgba(212,167,44,0.3)]">
                  Start Exam <PlayCircle className="w-5 h-5 ml-2" />
                </Button>
                <Button variant="outline" className="w-full h-14 rounded-[12px] bg-transparent border-white/30 text-white hover:bg-white/10 font-[700]">
                  View Details
                </Button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 5. AVAILABLE EXAMS */}
      <section className="py-16 bg-slate-50 dark:bg-[#0A1118]">
        <div className="container mx-auto px-4 max-w-[1200px]">
          <h2 className="text-2xl md:text-3xl font-[900] text-slate-900 dark:text-white mb-2">Available Examinations</h2>
          <p className="text-slate-600 dark:text-slate-400 font-[500] mb-10">Choose an assessment based on your target exam and preparation level.</p>
          
          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
          ) : exams.length === 0 ? (
            <p className="text-slate-500 font-[500]">No examinations have been published yet. Check back soon.</p>
          ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {exams.map((exam) => (
              <Dialog key={exam.id}>
                <DialogTrigger asChild>
                  {/* 6. EXAM CARD DESIGN */}
                  <div className="p-6 rounded-[20px] bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 hover:border-[#163E6B]/40 dark:hover:border-white/20 hover:shadow-lg transition-all group cursor-pointer flex flex-col h-full relative overflow-hidden">

                    <div className="flex justify-between items-start mb-4">
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-[6px] bg-slate-100 dark:bg-white/5 text-slate-700 dark:text-slate-300 text-[10px] font-[800] uppercase tracking-wider">
                        {exam.type}
                      </div>
                      {exam.status === "LIVE" || exam.status === "UPCOMING" ? (
                        <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
                      ) : (
                        <div className="w-2 h-2 rounded-full bg-slate-400"></div>
                      )}
                    </div>

                    <h3 className="text-lg font-[800] text-slate-900 dark:text-white mb-1 group-hover:text-[#163E6B] dark:group-hover:text-[#D4A72C] transition-colors leading-tight">
                      {exam.title}
                    </h3>
                    <p className="text-sm font-[600] text-slate-500 dark:text-slate-400 mb-6">{exam.level || "General"} • {exam.paper}</p>

                    <div className="grid grid-cols-2 gap-3 mb-6 mt-auto">
                      <div className="bg-slate-50 dark:bg-[#0A1118] p-3 rounded-[10px] border border-slate-100 dark:border-white/5">
                        <div className="text-[10px] font-[800] text-slate-400 uppercase tracking-wider mb-1">Questions</div>
                        <div className="text-sm font-[800] text-slate-700 dark:text-slate-200 flex items-center gap-1.5">
                          <FileText className="w-3.5 h-3.5" /> {exam.questions}
                        </div>
                      </div>
                      <div className="bg-slate-50 dark:bg-[#0A1118] p-3 rounded-[10px] border border-slate-100 dark:border-white/5">
                        <div className="text-[10px] font-[800] text-slate-400 uppercase tracking-wider mb-1">Duration</div>
                        <div className="text-sm font-[800] text-slate-700 dark:text-slate-200 flex items-center gap-1.5">
                          <Clock className="w-3.5 h-3.5" /> {exam.duration}m
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center justify-between mt-2 pt-4 border-t border-slate-100 dark:border-white/5">
                      <span className={`text-xs font-[800] px-2 py-1 rounded-[4px]
                        ${exam.status === 'LIVE' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400' :
                          exam.status === 'UPCOMING' ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400' :
                          'bg-slate-100 text-slate-600 dark:bg-white/5 dark:text-slate-400'}`}>
                        {STATUS_LABELS[exam.status]}
                      </span>

                      <span className="text-sm font-[800] text-[#163E6B] dark:text-[#D4A72C] flex items-center gap-1 group-hover:translate-x-1 transition-transform">
                        {exam.status === "COMPLETED" ? "View Details" : "Start Exam"} <ArrowRight className="w-4 h-4 ml-1" />
                      </span>
                    </div>
                  </div>
                </DialogTrigger>

                {/* 7. EXAM DETAIL PREVIEW (Modal) */}
                <DialogContent className="max-w-2xl bg-white dark:bg-[#0B1521] border-slate-200 dark:border-white/10 rounded-[24px] p-0 overflow-hidden">
                  <div className="bg-slate-50 dark:bg-[#0A1420] p-6 md:p-8 border-b border-slate-200 dark:border-white/10 relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-32 h-32 bg-[#D4A72C]/10 rounded-bl-full pointer-events-none"></div>
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-[6px] bg-[#163E6B]/10 dark:bg-white/10 text-[#163E6B] dark:text-white text-xs font-[800] uppercase tracking-wider mb-4 border border-[#163E6B]/20 dark:border-white/20">
                      Exam Overview
                    </div>
                    <DialogTitle className="text-2xl md:text-3xl font-[900] text-slate-900 dark:text-white mb-2">{exam.title}</DialogTitle>
                    <DialogDescription className="text-slate-600 dark:text-slate-400 font-[500]">
                      {exam.level || "General"} • {exam.type} • {exam.paper}
                    </DialogDescription>
                  </div>

                  <div className="p-6 md:p-8">
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-8">
                      <div className="bg-slate-50 dark:bg-[#0A1118] p-4 rounded-[12px] border border-slate-100 dark:border-white/5 text-center">
                        <div className="text-xs font-[800] text-slate-500 uppercase mb-1">Questions</div>
                        <div className="text-xl font-[900] text-slate-900 dark:text-white">{exam.questions}</div>
                      </div>
                      <div className="bg-slate-50 dark:bg-[#0A1118] p-4 rounded-[12px] border border-slate-100 dark:border-white/5 text-center">
                        <div className="text-xs font-[800] text-slate-500 uppercase mb-1">Duration</div>
                        <div className="text-xl font-[900] text-slate-900 dark:text-white">{exam.duration}m</div>
                      </div>
                      <div className="bg-slate-50 dark:bg-[#0A1118] p-4 rounded-[12px] border border-slate-100 dark:border-white/5 text-center">
                        <div className="text-xs font-[800] text-slate-500 uppercase mb-1">Status</div>
                        <div className="text-xl font-[900] text-slate-900 dark:text-white">{STATUS_LABELS[exam.status]}</div>
                      </div>
                    </div>

                    {exam.subjects.length > 0 && (
                    <div className="mb-8">
                      <h4 className="text-sm font-[800] text-slate-900 dark:text-white mb-3 uppercase tracking-wider">Subjects Covered</h4>
                      <div className="flex flex-wrap gap-2">
                        {exam.subjects.map((sub, i) => (
                          <span key={i} className="px-3 py-1.5 bg-slate-100 dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-[8px] text-sm font-[600] text-slate-700 dark:text-slate-300">
                            {sub}
                          </span>
                        ))}
                      </div>
                    </div>
                    )}

                    <div className="mb-8 bg-amber-50 dark:bg-amber-500/5 border border-amber-200 dark:border-amber-500/20 rounded-[12px] p-5">
                      <h4 className="text-sm font-[800] text-amber-900 dark:text-amber-500 mb-3 uppercase tracking-wider flex items-center gap-2">
                        <AlertCircle className="w-4 h-4" /> Instructions
                      </h4>
                      <ul className="space-y-2">
                        <li className="text-sm font-[500] text-amber-800 dark:text-amber-200/70 flex items-start gap-2">
                          <span className="mt-1.5 w-1 h-1 rounded-full bg-amber-500 shrink-0"></span> Read each question carefully before answering.
                        </li>
                        <li className="text-sm font-[500] text-amber-800 dark:text-amber-200/70 flex items-start gap-2">
                          <span className="mt-1.5 w-1 h-1 rounded-full bg-amber-500 shrink-0"></span> You can navigate freely between questions.
                        </li>
                        <li className="text-sm font-[500] text-amber-800 dark:text-amber-200/70 flex items-start gap-2">
                          <span className="mt-1.5 w-1 h-1 rounded-full bg-amber-500 shrink-0"></span> Review all your answers before final submission.
                        </li>
                        <li className="text-sm font-[500] text-amber-800 dark:text-amber-200/70 flex items-start gap-2">
                          <span className="mt-1.5 w-1 h-1 rounded-full bg-amber-500 shrink-0"></span> The exam will automatically submit when the timer expires.
                        </li>
                      </ul>
                    </div>

                    <div className="flex flex-col sm:flex-row gap-3">
                      <Link href="/login" className="flex-1">
                        <Button className="w-full h-14 rounded-[12px] bg-[#163E6B] dark:bg-[#D4A72C] hover:bg-[#163E6B]/90 dark:hover:bg-[#D4A72C]/90 text-white dark:text-[#0A1118] font-[800] text-[16px]">
                          Start Examination <ArrowRight className="w-5 h-5 ml-2" />
                        </Button>
                      </Link>
                      <DialogTrigger asChild>
                        <Button variant="outline" className="h-14 px-8 rounded-[12px] border-slate-300 dark:border-white/20 text-slate-700 dark:text-slate-300 font-[700]">
                          Cancel
                        </Button>
                      </DialogTrigger>
                    </div>
                  </div>
                </DialogContent>
              </Dialog>
            ))}
          </div>
          )}
        </div>
      </section>

      {/* 8. EXAM SIMULATION PREVIEW & 10. RESULT PREVIEW */}
      <section className="py-20 border-y border-slate-200 dark:border-white/5 bg-white dark:bg-[#0B1521] overflow-hidden relative">
        <div className="container mx-auto px-4 max-w-[1200px]">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-[900] text-slate-900 dark:text-white mb-4">Built For Real Exam Conditions</h2>
            <p className="text-lg text-slate-600 dark:text-slate-400 font-[500] max-w-2xl mx-auto">
              Our interface mirrors actual computer-based testing environments to ensure you are comfortable on exam day.
            </p>
          </div>
          
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
            
            {/* Exam Interface Mockup */}
            <div className="bg-slate-100 dark:bg-[#0A1118] border border-slate-200 dark:border-white/10 rounded-[20px] shadow-xl overflow-hidden flex flex-col">
              {/* Mock Header */}
              <div className="bg-white dark:bg-[#0B1521] border-b border-slate-200 dark:border-white/10 px-6 py-4 flex justify-between items-center">
                <span className="font-[800] text-slate-900 dark:text-white">Question 24 <span className="text-slate-400">/ 100</span></span>
                <div className="flex items-center gap-2 px-3 py-1 bg-rose-50 dark:bg-rose-500/10 rounded-[6px] border border-rose-200 dark:border-rose-500/20">
                  <Clock className="w-4 h-4 text-rose-600 dark:text-rose-400" />
                  <span className="font-[900] text-rose-600 dark:text-rose-400 font-mono">01:12:48</span>
                </div>
              </div>
              
              {/* Mock Body */}
              <div className="p-6 flex-1 bg-white/50 dark:bg-transparent">
                <p className="text-lg font-[600] text-slate-800 dark:text-slate-200 mb-8 leading-relaxed">
                  According to the Constitution of Nepal, which of the following commissions is responsible for conducting examinations for the selection of civil service employees?
                </p>
                <div className="space-y-3">
                  {["Election Commission", "Public Service Commission", "National Human Rights Commission", "Commission for the Investigation of Abuse of Authority"].map((opt, i) => (
                    <div key={i} className={`p-4 rounded-[12px] border ${i === 1 ? 'border-[#163E6B] bg-blue-50 dark:border-[#D4A72C] dark:bg-[#D4A72C]/10' : 'border-slate-200 dark:border-white/10 bg-white dark:bg-[#0B1521]'} text-slate-700 dark:text-slate-300 font-[500] text-sm flex items-center gap-3 cursor-not-allowed`}>
                      <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${i === 1 ? 'border-[#163E6B] dark:border-[#D4A72C]' : 'border-slate-300 dark:border-slate-600'}`}>
                        {i === 1 && <div className="w-2.5 h-2.5 rounded-full bg-[#163E6B] dark:bg-[#D4A72C]"></div>}
                      </div>
                      {opt}
                    </div>
                  ))}
                </div>
              </div>

              {/* Mock Footer */}
              <div className="bg-white dark:bg-[#0B1521] border-t border-slate-200 dark:border-white/10 px-6 py-4">
                <div className="flex justify-between items-center mb-6">
                  <Button variant="outline" className="h-10 text-xs font-[700] cursor-not-allowed">Previous</Button>
                  <Button variant="outline" className="h-10 text-xs font-[700] border-amber-200 text-amber-700 dark:border-amber-500/30 dark:text-amber-500 bg-amber-50 dark:bg-amber-500/10 cursor-not-allowed">Mark for Review</Button>
                  <Button className="h-10 text-xs font-[700] bg-[#163E6B] dark:bg-white text-white dark:text-[#0A1118] cursor-not-allowed">Next Question</Button>
                </div>
                
                <div className="border-t border-slate-100 dark:border-white/5 pt-4">
                  <div className="text-[10px] font-[800] text-slate-400 uppercase tracking-wider mb-2">Question Palette</div>
                  <div className="flex flex-wrap gap-1.5">
                    {[...Array(10)].map((_, i) => (
                      <div key={i} className={`w-7 h-7 rounded-[4px] flex items-center justify-center text-[10px] font-[800] 
                        ${i < 3 ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400' : 
                          i === 3 ? 'bg-[#163E6B] text-white dark:bg-[#D4A72C] dark:text-[#0A1118]' : 
                          i === 7 ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400' : 
                          'bg-slate-100 text-slate-500 dark:bg-white/10 dark:text-slate-400'}`}>
                        {i + 21}
                      </div>
                    ))}
                    <div className="w-7 h-7 flex items-center justify-center text-slate-400 font-[800]">...</div>
                    <div className="w-7 h-7 rounded-[4px] bg-slate-100 dark:bg-white/10 flex items-center justify-center text-[10px] font-[800] text-slate-500 dark:text-slate-400">100</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Results Mockup */}
            <div className="flex flex-col gap-6">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-[6px] bg-slate-100 dark:bg-white/5 text-xs font-[800] text-slate-600 dark:text-slate-400 uppercase tracking-wider w-fit border border-slate-200 dark:border-white/10">
                Sample Performance View
              </div>
              
              <div className="bg-slate-50 dark:bg-[#0A1118] border border-slate-200 dark:border-white/10 rounded-[20px] p-8 shadow-sm flex-1 flex flex-col">
                <h3 className="text-xl font-[900] text-slate-900 dark:text-white mb-8">Know Your Performance</h3>
                
                <div className="grid grid-cols-2 gap-4 mb-8">
                  <div className="p-5 bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 rounded-[16px] flex flex-col items-center justify-center text-center">
                    <div className="text-3xl font-[900] text-[#163E6B] dark:text-[#D4A72C] mb-1">82<span className="text-lg text-slate-400">/100</span></div>
                    <div className="text-xs font-[700] text-slate-500 uppercase tracking-wider">Score</div>
                  </div>
                  <div className="p-5 bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 rounded-[16px] flex flex-col items-center justify-center text-center">
                    <div className="text-3xl font-[900] text-emerald-600 dark:text-emerald-400 mb-1">84%</div>
                    <div className="text-xs font-[700] text-slate-500 uppercase tracking-wider">Accuracy</div>
                  </div>
                  <div className="p-5 bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 rounded-[16px] flex flex-col items-center justify-center text-center">
                    <div className="flex items-end gap-3 mb-1">
                      <div className="text-xl font-[900] text-emerald-600 dark:text-emerald-400"><span className="text-xs text-slate-500 block mb-1">Correct</span>82</div>
                      <div className="text-xl font-[900] text-rose-600 dark:text-rose-400"><span className="text-xs text-slate-500 block mb-1">Incorrect</span>18</div>
                    </div>
                  </div>
                  <div className="p-5 bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 rounded-[16px] flex flex-col items-center justify-center text-center">
                    <div className="text-2xl font-[900] text-slate-800 dark:text-slate-200 mb-1">78<span className="text-sm font-[600]"> min</span></div>
                    <div className="text-xs font-[700] text-slate-500 uppercase tracking-wider">Time Used</div>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mt-auto">
                  <div className="bg-white dark:bg-[#0B1521] p-5 border border-slate-200 dark:border-white/5 rounded-[16px]">
                    <h5 className="text-sm font-[800] text-slate-900 dark:text-white mb-3 flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-500"/> Strong</h5>
                    <ul className="space-y-2">
                      <li className="text-sm font-[600] text-slate-600 dark:text-slate-300">General Knowledge</li>
                      <li className="text-sm font-[600] text-slate-600 dark:text-slate-300">Constitution</li>
                    </ul>
                  </div>
                  <div className="bg-white dark:bg-[#0B1521] p-5 border border-slate-200 dark:border-white/5 rounded-[16px]">
                    <h5 className="text-sm font-[800] text-slate-900 dark:text-white mb-3 flex items-center gap-2"><AlertCircle className="w-4 h-4 text-rose-500"/> Needs Improvement</h5>
                    <ul className="space-y-2">
                      <li className="text-sm font-[600] text-slate-600 dark:text-slate-300">Current Affairs</li>
                      <li className="text-sm font-[600] text-slate-600 dark:text-slate-300">Public Admin.</li>
                    </ul>
                  </div>
                </div>

              </div>
            </div>

          </div>
        </div>
      </section>

      {/* 9. EXAM FEATURES */}
      <section className="py-16 bg-slate-50 dark:bg-[#0A1118]">
        <div className="container mx-auto px-4 max-w-[1200px]">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="p-6 bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 rounded-[16px]">
              <Clock className="w-8 h-8 text-[#163E6B] dark:text-[#D4A72C] mb-4" />
              <h4 className="text-lg font-[800] text-slate-900 dark:text-white mb-2">Realistic Timing</h4>
              <p className="text-sm text-slate-600 dark:text-slate-400 font-[500]">Experience fixed-duration exams designed around actual examination patterns.</p>
            </div>
            <div className="p-6 bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 rounded-[16px]">
              <Layers className="w-8 h-8 text-[#163E6B] dark:text-[#D4A72C] mb-4" />
              <h4 className="text-lg font-[800] text-slate-900 dark:text-white mb-2">Smart Navigation</h4>
              <p className="text-sm text-slate-600 dark:text-slate-400 font-[500]">Move between questions, review answers, and mark questions for later easily.</p>
            </div>
            <div className="p-6 bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 rounded-[16px]">
              <Trophy className="w-8 h-8 text-[#163E6B] dark:text-[#D4A72C] mb-4" />
              <h4 className="text-lg font-[800] text-slate-900 dark:text-white mb-2">Instant Results</h4>
              <p className="text-sm text-slate-600 dark:text-slate-400 font-[500]">Get your total score and detailed performance summary immediately after submission.</p>
            </div>
            <div className="p-6 bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 rounded-[16px]">
              <BarChart2 className="w-8 h-8 text-[#163E6B] dark:text-[#D4A72C] mb-4" />
              <h4 className="text-lg font-[800] text-slate-900 dark:text-white mb-2">Detailed Analysis</h4>
              <p className="text-sm text-slate-600 dark:text-slate-400 font-[500]">Understand your strengths, weak subjects, accuracy percentage, and time usage.</p>
            </div>
          </div>
        </div>
      </section>

      {/* 11. EXAM FLOW */}
      <section className="py-20 bg-white dark:bg-[#0B1521] border-y border-slate-200 dark:border-white/5">
        <div className="container mx-auto px-4 max-w-[1200px]">
          <h2 className="text-2xl md:text-3xl font-[900] text-slate-900 dark:text-white mb-16 text-center">How Exams Work</h2>
          
          <div className="flex flex-col md:flex-row justify-between items-start md:items-start relative gap-8 md:gap-4">
            {/* Desktop connecting line */}
            <div className="hidden md:block absolute top-6 left-[8%] right-[8%] h-px bg-slate-200 dark:bg-white/10 z-0"></div>

            {[
              { step: "01", title: "Choose Exam", desc: "Select level and paper." },
              { step: "02", title: "Read Instructions", desc: "Review rules and format." },
              { step: "03", title: "Start Timer", desc: "Begin fixed-duration test." },
              { step: "04", title: "Answer Questions", desc: "Navigate and solve." },
              { step: "05", title: "Submit Exam", desc: "Finish before time ends." },
              { step: "06", title: "Get Results", desc: "Analyze performance." }
            ].map((item, idx) => (
              <div key={idx} className="relative z-10 flex flex-row md:flex-col items-center gap-6 md:gap-4 flex-1">
                <div className="w-12 h-12 rounded-full bg-slate-50 dark:bg-[#0A1118] border-2 border-slate-300 dark:border-white/20 flex items-center justify-center font-[900] text-slate-500 dark:text-slate-400 text-sm shadow-sm shrink-0">
                  {item.step}
                </div>
                <div className="md:text-center">
                  <h4 className="text-sm font-[800] text-slate-900 dark:text-white mb-1">{item.title}</h4>
                  <p className="text-xs text-slate-600 dark:text-slate-400 font-[500]">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 12. EXAM INFORMATION SECTION */}
      <section className="py-20 bg-slate-50 dark:bg-[#0A1118]">
        <div className="container mx-auto px-4 max-w-[1000px] text-center">
          <h2 className="text-3xl font-[900] text-slate-900 dark:text-white mb-10">Find the Right Exam For You</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12 text-left">
            <div className="p-8 bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 rounded-[20px] hover:border-[#163E6B]/30 dark:hover:border-white/20 transition-all">
              <div className="w-10 h-10 rounded-full bg-emerald-100 dark:bg-emerald-500/10 flex items-center justify-center mb-4 text-emerald-600 dark:text-emerald-400">
                <BookOpen className="w-5 h-5" />
              </div>
              <h3 className="text-xl font-[800] text-slate-900 dark:text-white mb-2">Beginner</h3>
              <p className="text-sm font-[500] text-slate-600 dark:text-slate-400">Start with flexible practice exams and topic-wise tests to build confidence.</p>
            </div>
            <div className="p-8 bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 rounded-[20px] hover:border-[#163E6B]/30 dark:hover:border-white/20 transition-all">
              <div className="w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-500/10 flex items-center justify-center mb-4 text-amber-600 dark:text-amber-400">
                <Target className="w-5 h-5" />
              </div>
              <h3 className="text-xl font-[800] text-slate-900 dark:text-white mb-2">Intermediate</h3>
              <p className="text-sm font-[500] text-slate-600 dark:text-slate-400">Challenge yourself with mixed-subject exams and strict timing.</p>
            </div>
            <div className="p-8 bg-white dark:bg-[#0B1521] border border-slate-200 dark:border-white/5 rounded-[20px] hover:border-[#163E6B]/30 dark:hover:border-white/20 transition-all">
              <div className="w-10 h-10 rounded-full bg-rose-100 dark:bg-rose-500/10 flex items-center justify-center mb-4 text-rose-600 dark:text-rose-400">
                <Trophy className="w-5 h-5" />
              </div>
              <h3 className="text-xl font-[800] text-slate-900 dark:text-white mb-2">Advanced</h3>
              <p className="text-sm font-[500] text-slate-600 dark:text-slate-400">Attempt full-length timed model examinations to simulate the real test.</p>
            </div>
          </div>

          <Button className="h-14 px-10 rounded-[12px] bg-[#163E6B] dark:bg-white text-white dark:text-[#0A1118] font-[800] text-[16px] shadow-lg">
            Find My Exam <ArrowRight className="w-5 h-5 ml-2" />
          </Button>
        </div>
      </section>

      {/* 13. LOGIN / ACCESS HANDLING */}
      <section className="py-20 bg-slate-200 dark:bg-[#050A10] border-t border-slate-300 dark:border-white/5">
        <div className="container mx-auto px-4 max-w-[600px] text-center">
          <div className="w-16 h-16 rounded-full bg-white dark:bg-white/5 flex items-center justify-center mx-auto mb-6 shadow-sm border border-slate-200 dark:border-white/10">
            <User className="w-8 h-8 text-slate-700 dark:text-slate-300" />
          </div>
          <h2 className="text-2xl md:text-3xl font-[900] text-slate-900 dark:text-white mb-4">Ready to take the exam?</h2>
          <p className="text-slate-600 dark:text-slate-400 font-[500] mb-8">
            Log in or create your account to begin your examination, save your progress, and access detailed analytics.
          </p>
          <div className="flex justify-center gap-4">
            <Link href="/login">
              <Button variant="outline" className="h-12 px-8 rounded-[10px] bg-white dark:bg-transparent border-slate-300 dark:border-white/20 text-slate-700 dark:text-slate-200 font-[700] hover:bg-slate-50 dark:hover:bg-white/10 shadow-sm">
                Log In
              </Button>
            </Link>
            <Link href="/register">
              <Button className="h-12 px-8 rounded-[10px] bg-[#0B2545] dark:bg-white text-white dark:text-[#0A1118] font-[800] hover:bg-[#163E6B] dark:hover:bg-slate-200 shadow-sm">
                Create Account
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* 14. PREMIUM CTA */}
      <section className="py-24 bg-[#0B2545] dark:bg-[#020611] text-center relative overflow-hidden border-t border-[#163E6B]/30 dark:border-white/5">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom,#163E6B_0%,transparent_60%)] opacity-30 dark:opacity-50"></div>
        <div className="container mx-auto px-4 max-w-[800px] relative z-10">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/10 border border-white/20 mb-6 backdrop-blur-sm">
            <span className="text-[10px] font-bold uppercase tracking-widest text-[#D4A72C]">
              READY FOR THE REAL TEST?
            </span>
          </div>
          
          <h2 className="text-4xl md:text-5xl font-[900] text-white mb-6 tracking-tight">
            Turn Preparation Into Performance.
          </h2>
          
          <p className="text-lg md:text-xl text-slate-300 font-[500] mb-10 leading-relaxed">
            Take structured examinations, discover your weak areas, and prepare with confidence.
          </p>
          
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/courses">
              <Button variant="outline" className="h-14 px-8 rounded-[12px] bg-transparent border-white/30 text-white hover:bg-white/10 font-[700] text-[16px]">
                Explore Courses <ArrowRight className="w-5 h-5 ml-2" />
              </Button>
            </Link>
            <Link href="/exams">
              <Button className="h-14 px-8 rounded-[12px] bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] font-[800] text-[16px] shadow-[0_0_20px_rgba(212,167,44,0.3)]">
                Start an Exam
              </Button>
            </Link>
          </div>
        </div>
      </section>

    </div>
  );
}
