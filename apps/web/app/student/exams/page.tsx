"use client";

import { useState } from "react";
import Link from "next/link";
import { FileText, Clock, Target, Play, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useQuery } from "@tanstack/react-query";
import { studentExamsApi, StudentExam } from "@/lib/api/student-exams";
import { LoksewaExamCountdown } from "@/components/student/countdown/LoksewaExamCountdown";
import { MockExamCountdown } from "@/components/student/countdown/MockExamCountdown";
import { useOptionalStudentContext } from "@/contexts/StudentContext";

const ExamSkeletonGrid = () => (
  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
    {[1, 2, 3, 4, 5, 6].map((i) => (
      <Card key={i} className="border-border/60 flex flex-col animate-pulse">
        <CardHeader className="space-y-3">
          <div className="flex justify-between items-start">
            <div className="h-5 w-16 bg-muted/60 rounded" />
            <div className="h-5 w-20 bg-muted/40 rounded" />
          </div>
          <div className="h-6 w-3/4 bg-muted/70 rounded" />
          <div className="h-4 w-1/2 bg-muted/50 rounded" />
        </CardHeader>
        <CardContent className="flex-1">
          <div className="h-11 bg-muted/40 rounded-lg" />
        </CardContent>
        <CardFooter className="pt-4 border-t border-border/50">
          <div className="h-10 w-full bg-muted/60 rounded" />
        </CardFooter>
      </Card>
    ))}
  </div>
);

export default function ExamsListingPage() {
  const [activeTab, setActiveTab] = useState("past_year");
  const studentCtx = useOptionalStudentContext();
  const effectiveCourseId = studentCtx?.activeCourse?.id;
  const isCtxLoading = studentCtx?.isLoading ?? false;

  const { data: exams, isLoading: isLoadingExams } = useQuery({
    queryKey: ['student-exams', effectiveCourseId ?? null],
    queryFn: () => studentExamsApi.getExams(effectiveCourseId),
    enabled: !isCtxLoading,
    staleTime: 60 * 1000,
  });

  const activeExams: StudentExam[] = exams || [];

  // Group by effective_category — a Live Exam auto-promotes into the Model
  // Exams tab 48h after its scheduled start, so this reads the promoted
  // value rather than the raw admin-set category.
  const oldPastExams = activeExams.filter(e => e.effective_category === "past_year");
  const modelExams = activeExams.filter(e => e.effective_category === "model");
  const liveExams = activeExams.filter(e => e.effective_category === "live");
  const topicwiseExams = activeExams.filter(e => e.effective_category === "topicwise" || (e.exam_type === "subject" && !!e.topic_id));

  const ExamGrid = ({ list, emptyTitle, emptyBody }: { list: StudentExam[]; emptyTitle: string; emptyBody: string }) => {
    if (isLoadingExams && !exams) {
      return <ExamSkeletonGrid />;
    }

    if (list.length === 0) {
      return (
        <Card className="border-border/60 border-dashed flex flex-col items-center justify-center p-12 text-center text-muted-foreground">
          <FileText className="h-10 w-10 mb-4 opacity-50 text-muted-foreground" />
          <h3 className="font-medium text-lg mb-1 text-foreground">
            {activeExams.length === 0 ? "No exams available for your course yet." : emptyTitle}
          </h3>
          <p className="text-sm text-muted-foreground">
            {activeExams.length === 0 ? "New examinations will appear here when they are published." : emptyBody}
          </p>
        </Card>
      );
    }

    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {list.map((exam) => (
          <Card key={exam.id} className="border-border/60 flex flex-col hover:border-primary/30 transition-colors">
            <CardHeader>
              <div className="flex justify-between items-start mb-2">
                <Badge variant={exam.exam_type === "mock" ? "default" : "secondary"}>
                  {exam.exam_type.toUpperCase()}
                </Badge>
                {exam.has_attempted && (
                  <Badge variant="outline" className="text-primary border-primary/30">
                    Attempted
                  </Badge>
                )}
              </div>
              <CardTitle className="text-xl line-clamp-2">{exam.title}</CardTitle>
              <CardDescription className="text-primary font-medium mt-1">
                {exam.category_name} - {exam.exam_name}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex-1">
              <div className="flex items-center justify-between text-sm text-muted-foreground bg-muted/30 p-3 rounded-lg">
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4" />
                  <span>{exam.time_limit} min</span>
                </div>
                <div className="flex items-center gap-2">
                  <Target className="h-4 w-4" />
                  <span>{exam.total_questions} Qs</span>
                </div>
              </div>
            </CardContent>
            <CardFooter className="pt-4 border-t border-border/50">
              <Link href={`/student/exams/${exam.id}`} className="w-full">
                <Button
                  className="w-full gap-2"
                  variant={exam.has_attempted ? "secondary" : "default"}
                >
                  {exam.has_attempted ? (
                    <>
                      <CheckCircle className="h-4 w-4 text-emerald-500" />
                      Already Taken — Details
                    </>
                  ) : (
                    <>
                      <Play className="h-4 w-4" />
                      Take Exam
                    </>
                  )}
                </Button>
              </Link>
            </CardFooter>
          </Card>
        ))}
      </div>
    );
  };

  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto space-y-8 animate-in fade-in-50 duration-500">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">Mock Exams</h1>
          <p className="text-muted-foreground mt-1">Simulate the real examination environment.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href="/student/exams/request-subjective"><Button variant="outline">Request Subjective Live Exam</Button></Link>
          <Link href="/student/results"><Button variant="outline">Past Results</Button></Link>
          <Link href="/student/exams/custom-builder"><Button variant="outline">Create Your Own</Button></Link>
          <Link href="/student/subjective"><Button variant="outline">Subjective Practice</Button></Link>
        </div>
      </div>

      {/* Live & Upcoming Countdowns */}
      <div className="space-y-4">
        <LoksewaExamCountdown />
        <MockExamCountdown />
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="mb-6 flex-wrap h-auto">
          <TabsTrigger value="past_year">Past Year Paper</TabsTrigger>
          <TabsTrigger value="model">Model Exams</TabsTrigger>
          <TabsTrigger value="live">Live Exams</TabsTrigger>
          <TabsTrigger value="topicwise">Topicwise Exam</TabsTrigger>
        </TabsList>

        <TabsContent value="past_year" className="space-y-6">
          <ExamGrid
            list={oldPastExams}
            emptyTitle="No Past Year Papers"
            emptyBody="Original past papers will show up here once published."
          />
        </TabsContent>

        <TabsContent value="model" className="space-y-6">
          <ExamGrid
            list={modelExams}
            emptyTitle="No Model Exams"
            emptyBody="Start-anytime, fixed-duration mock exams will show up here once published."
          />
        </TabsContent>

        <TabsContent value="live" className="space-y-6">
          <ExamGrid
            list={liveExams}
            emptyTitle="No Live Exams Right Now"
            emptyBody="Live Exams run in a fixed shared window — a completed one moves to Model Exams after 48 hours."
          />
        </TabsContent>

        <TabsContent value="topicwise" className="space-y-6">
          <ExamGrid
            list={topicwiseExams}
            emptyTitle="No Topicwise Exams"
            emptyBody="Published topic-focused examinations will appear here."
          />
        </TabsContent>

      </Tabs>
    </div>
  );
}
