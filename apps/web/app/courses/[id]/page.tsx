"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { BookOpen, Target, FileText, Bookmark, PlayCircle, Clock, ChevronLeft, GraduationCap, Trophy, ArrowRight, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { RetryImage } from "@/components/ui/retry-image";
import Link from "next/link";
import { courseEnrollmentApi } from "@/lib/api/enrollment";
import { useAuth } from "@/contexts/AuthContext";
import { Badge } from "@/components/ui/badge";

export default function PublicCourseDetail() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const isAuthenticated = !!user;
  const idOrSlug = params.id as string;
  
  const [course, setCourse] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [isApplying, setIsApplying] = useState(false);
  const [applySuccess, setApplySuccess] = useState(false);

  useEffect(() => {
    async function loadCourse() {
      if (!idOrSlug) return;
      try {
        const data = await courseEnrollmentApi.getCourseDetails(idOrSlug);
        setCourse(data);
      } catch (err: any) {
        console.error("Failed to load course details:", err);
        setError("Failed to load course details. Please try again later.");
      } finally {
        setIsLoading(false);
      }
    }
    loadCourse();
  }, [idOrSlug]);

  const handleApply = async () => {
    const targetCourseId = course?.id || (!isNaN(Number(idOrSlug)) ? Number(idOrSlug) : undefined);

    if (!isAuthenticated) {
      router.push(`/register?course=${targetCourseId || idOrSlug}`);
      return;
    }

    if (course?.is_enrolled) {
      router.push(`/student/courses/${course?.slug || targetCourseId || idOrSlug}`);
      return;
    }

    if (!targetCourseId) {
      alert("Unable to process application for this course.");
      return;
    }

    setIsApplying(true);
    try {
      await courseEnrollmentApi.applyToCourse(targetCourseId);
      setApplySuccess(true);
    } catch (err) {
      console.error("Application failed:", err);
      alert("Failed to submit application. Please try again.");
    } finally {
      setIsApplying(false);
    }
  };

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-NP', { style: 'currency', currency: 'NPR', maximumFractionDigits: 0 }).format(price);
  };

  if (isLoading) {
    return (
      <>
        <main className="flex-1 bg-slate-50 dark:bg-[#040B14] min-h-screen pt-[80px]">
          <div className="p-4 lg:p-8 max-w-5xl mx-auto space-y-8 animate-pulse pt-16">
            <div className="h-64 bg-slate-200 dark:bg-white/5 rounded-[24px]"></div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8">
              {[1, 2, 3].map(i => <div key={i} className="h-32 bg-slate-200 dark:bg-white/5 rounded-[16px]"></div>)}
            </div>
          </div>
        </main>
      </>
    );
  }

  if (error || !course) {
    return (
      <>
        <main className="flex-1 bg-slate-50 dark:bg-[#040B14] min-h-screen pt-[80px]">
          <div className="p-8 text-center flex flex-col items-center justify-center min-h-[60vh]">
            <Trophy className="w-16 h-16 text-red-200 mb-4" />
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">Course Not Found</h2>
            <p className="text-slate-500 mb-6">{error || "The course you are looking for does not exist."}</p>
            <Button onClick={() => router.push('/courses')} className="bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118]">
              Browse Other Courses
            </Button>
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <main className="flex-1 bg-slate-50 dark:bg-[#040B14] min-h-screen pt-[80px]">
        <div className="p-4 lg:p-8 max-w-6xl mx-auto space-y-8 pb-20">
          <Button 
            variant="ghost" 
            onClick={() => router.push('/courses')}
            className="text-slate-500 dark:text-slate-400 hover:text-[#0B2545] dark:hover:text-white p-0 h-auto hover:bg-transparent font-semibold flex items-center gap-1 mb-4"
          >
            <ChevronLeft className="w-4 h-4" /> Back to Courses
          </Button>

          {/* Hero Section */}
          <div className="bg-white dark:bg-[#0B1521] rounded-[24px] border border-slate-200 dark:border-white/10 shadow-sm overflow-hidden flex flex-col md:flex-row relative">
            {course.thumbnail ? (
              <div className="md:w-1/3 h-64 md:h-auto bg-slate-100 relative">
                <RetryImage src={course.thumbnail} alt={course.title} className="w-full h-full object-cover" />
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent flex items-end p-6">
                  {course.exam && (
                    <span className="bg-[#D4A72C] text-[#0A1118] text-xs font-bold px-3 py-1.5 rounded-full uppercase tracking-wider shadow-lg">
                      {course.exam.title}
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <div className="md:w-1/3 h-64 md:h-auto bg-gradient-to-br from-[#0B2545] to-[#163E6B] flex flex-col items-center justify-center text-white relative">
                <div className="absolute inset-0 bg-[url('/grid-pattern.svg')] opacity-20 z-10"></div>
                <GraduationCap className="w-20 h-20 mb-2 opacity-50 z-20" />
                {course.exam && (
                  <span className="absolute bottom-6 left-6 z-20 bg-[#D4A72C] text-[#0A1118] text-xs font-bold px-3 py-1.5 rounded-full uppercase tracking-wider shadow-lg">
                    {course.exam.title}
                  </span>
                )}
              </div>
            )}
            
            <div className="p-8 md:p-10 md:w-2/3 flex flex-col">
              <div className="flex flex-wrap gap-2 mb-4">
                {course.category && (
                  <Badge className="bg-[#163E6B]/10 text-[#163E6B] dark:bg-blue-500/10 dark:text-blue-400 border-none font-bold uppercase tracking-wider text-[10px] px-2.5 py-1">
                    {course.category}
                  </Badge>
                )}
                {course.featured && (
                  <Badge className="bg-[#D4A72C] text-[#0A1118] font-bold border-none uppercase tracking-wider text-[10px] px-2.5 py-1">
                    Featured
                  </Badge>
                )}
              </div>

              <h1 className="text-3xl md:text-4xl font-[900] text-slate-900 dark:text-white tracking-tight mb-4 leading-tight">
                {course.title}
              </h1>
              
              <p className="text-slate-600 dark:text-slate-400 mb-8 leading-relaxed text-[15px] md:text-base line-clamp-3">
                {course.description || course.short_description || "Detailed preparation module designed for maximum success."}
              </p>
              
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
                <div className="flex flex-col gap-1">
                  <span className="text-xl font-[800] text-slate-900 dark:text-white">{course.duration_months || 0}</span>
                  <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Months</span>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-xl font-[800] text-slate-900 dark:text-white">{course.metadata?.subject_count || 0}</span>
                  <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Subjects</span>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-xl font-[800] text-slate-900 dark:text-white">{course.is_open_for_enrollment ? 'Yes' : 'No'}</span>
                  <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Enrollment</span>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-xl font-[800] text-slate-900 dark:text-white">{course.students || 'New'}</span>
                  <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Students</span>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6 mt-auto pt-6 border-t border-slate-100 dark:border-white/5">
                <div>
                  <div className="text-sm font-semibold text-slate-500 dark:text-slate-400 mb-1">Course Investment</div>
                  <div className="flex items-center gap-3">
                    <span className="text-3xl font-[900] text-slate-900 dark:text-white tracking-tight leading-none">
                      {course.price ? formatPrice(course.price) : "Free"}
                    </span>
                    {course.originalPrice && (
                      <span className="text-sm font-semibold text-slate-400 line-through">
                        {formatPrice(course.originalPrice)}
                      </span>
                    )}
                  </div>
                </div>
                
                <div className="flex gap-3">
                  {applySuccess ? (
                    <div className="h-[48px] px-8 rounded-[12px] bg-green-50 dark:bg-green-500/10 border border-green-200 dark:border-green-500/20 text-green-700 dark:text-green-400 font-[700] text-[15px] flex items-center justify-center gap-2">
                      <CheckCircle2 className="w-5 h-5" /> Application Submitted
                    </div>
                  ) : (
                    <Button 
                      onClick={handleApply}
                      disabled={isApplying || (!course.is_open_for_enrollment && !course.is_enrolled)}
                      className={`h-[48px] px-8 rounded-[12px] font-[700] text-[15px] transition-all shadow-md flex items-center justify-center gap-2 group/btn ${
                        course.is_enrolled 
                          ? "bg-green-600 hover:bg-green-700 text-white" 
                          : "bg-[#0B2545] dark:bg-[#D4A72C] hover:bg-[#163E6B] dark:hover:bg-[#D4A72C]/90 text-white dark:text-[#0A1118]"
                      }`}
                    >
                      {isApplying ? (
                        "Processing..."
                      ) : course.is_enrolled ? (
                        <>Go to Course <ArrowRight className="w-4 h-4 group-hover/btn:translate-x-1 transition-transform" /></>
                      ) : course.is_open_for_enrollment ? (
                        isAuthenticated ? "Apply Now" : "Register to Apply"
                      ) : (
                        "Enrollment Closed"
                      )}
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Features / Details Section */}
          <div className="mt-12 grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="lg:col-span-2 space-y-8">
              <div className="bg-white dark:bg-[#0B1521] rounded-[24px] border border-slate-200 dark:border-white/10 p-8">
                <h3 className="text-2xl font-[800] text-slate-900 dark:text-white mb-6">About this course</h3>
                <div className="prose dark:prose-invert max-w-none text-slate-600 dark:text-slate-400">
                  <p>{course.description}</p>
                </div>
              </div>
              
              <div className="bg-white dark:bg-[#0B1521] rounded-[24px] border border-slate-200 dark:border-white/10 p-8">
                <h3 className="text-2xl font-[800] text-slate-900 dark:text-white mb-6">Course Syllabus</h3>
                <div className="space-y-4">
                  {course.subjects ? course.subjects.map((subject: any, idx: number) => (
                    <div key={idx} className="flex items-start gap-4 p-4 rounded-[12px] border border-slate-100 dark:border-white/5 bg-slate-50 dark:bg-white/5">
                      <div className="w-8 h-8 rounded-full bg-[#163E6B]/10 dark:bg-[#D4A72C]/10 flex items-center justify-center shrink-0">
                        <span className="text-sm font-bold text-[#163E6B] dark:text-[#D4A72C]">{idx + 1}</span>
                      </div>
                      <div>
                        <h4 className="font-bold text-slate-900 dark:text-white">{subject.title || `Subject ${idx + 1}`}</h4>
                        {subject.description && <p className="text-sm text-slate-500 mt-1">{subject.description}</p>}
                      </div>
                    </div>
                  )) : (
                    <div className="text-center py-8 text-slate-500 border border-dashed border-slate-200 dark:border-white/10 rounded-[12px]">
                      Syllabus details will be available upon enrollment.
                    </div>
                  )}
                </div>
              </div>
            </div>
            
            <div className="space-y-6">
              <div className="bg-white dark:bg-[#0B1521] rounded-[24px] border border-slate-200 dark:border-white/10 p-6">
                <h3 className="text-lg font-[800] text-slate-900 dark:text-white mb-4">What's Included</h3>
                <ul className="space-y-4">
                  <li className="flex items-start gap-3 text-slate-600 dark:text-slate-400">
                    <CheckCircle2 className="w-5 h-5 text-green-500 shrink-0" />
                    <span className="text-[15px]">Full syllabus coverage</span>
                  </li>
                  <li className="flex items-start gap-3 text-slate-600 dark:text-slate-400">
                    <CheckCircle2 className="w-5 h-5 text-green-500 shrink-0" />
                    <span className="text-[15px]">Downloadable PDF study materials</span>
                  </li>
                  <li className="flex items-start gap-3 text-slate-600 dark:text-slate-400">
                    <CheckCircle2 className="w-5 h-5 text-green-500 shrink-0" />
                    <span className="text-[15px]">Topic-wise practice questions</span>
                  </li>
                  <li className="flex items-start gap-3 text-slate-600 dark:text-slate-400">
                    <CheckCircle2 className="w-5 h-5 text-green-500 shrink-0" />
                    <span className="text-[15px]">Full-length mock exams</span>
                  </li>
                  <li className="flex items-start gap-3 text-slate-600 dark:text-slate-400">
                    <CheckCircle2 className="w-5 h-5 text-green-500 shrink-0" />
                    <span className="text-[15px]">Personalized study planner</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
