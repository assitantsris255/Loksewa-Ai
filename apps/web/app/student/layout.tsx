"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { DashboardHeader } from "@/components/layout/dashboard-header";
import { FocusAwareToaster } from "@/components/student/focus/FocusAwareToaster";
import { useFocusMode } from "@/contexts/FocusModeContext";
import { StudentContextProvider, useStudentContext } from "@/contexts/StudentContext";

function StudentLayoutContent({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { examFocus, examSession } = useFocusMode();
  const pathname = usePathname();
  const router = useRouter();
  const { subscription } = useStudentContext();

  const attemptPath = examSession
    ? `/student/exams/${examSession.examinationId ?? ""}/attempt/${examSession.attemptId}`
    : null;
  const onAttemptPage = !!attemptPath && pathname === attemptPath;

  const isLocked =
    !!subscription &&
    subscription.enforcementEnabled &&
    !subscription.hasActivePackage &&
    subscription.latestPayment?.status !== "PENDING";

  const isExemptPath =
    pathname === "/student" ||
    pathname.startsWith("/student/settings") ||
    pathname.startsWith("/student/help-support") ||
    pathname.startsWith("/student/purchases") ||
    pathname.startsWith("/student/packages") ||
    pathname.startsWith("/student/plans") ||
    pathname.startsWith("/student/checkout") ||
    pathname.startsWith("/student/onboarding");

  useEffect(() => {
    if (isExemptPath) {
      return;
    }

    if (isLocked) {
      router.replace("/student");
    }
  }, [pathname, isLocked, isExemptPath, router]);

  if (isLocked && !isExemptPath) {
    return <div className="min-h-screen bg-muted/20" />;
  }

  return (
    <div className={examFocus ? "flex min-h-screen flex-col bg-muted" : "flex min-h-screen bg-muted/20"}>
      {!examFocus && <Sidebar isOpen={sidebarOpen} setIsOpen={setSidebarOpen} role="student" />}

      <div className={examFocus ? "flex min-w-0 flex-1 flex-col" : "flex min-w-0 flex-1 flex-col lg:pl-72 transition-all duration-300"}>
        {examFocus && !onAttemptPage && attemptPath ? (
          <div className="flex items-center justify-center gap-3 bg-amber-500 px-4 py-2.5 text-sm font-semibold text-white">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>You have an exam in progress. Navigation is hidden until you submit it.</span>
            <Link
              href={attemptPath}
              className="rounded-md bg-card/20 px-3 py-1 hover:bg-card/30 transition-colors"
            >
              Resume Exam
            </Link>
          </div>
        ) : null}
        {!examFocus && (
          <DashboardHeader
            onMenuClick={() => setSidebarOpen(true)}
            role="student"
          />
        )}
        <main className={examFocus ? "flex-1" : "flex-1 overflow-y-auto"}>
          {children}
        </main>
      </div>

      <FocusAwareToaster />
    </div>
  );
}

export default function StudentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <StudentContextProvider>
      <StudentLayoutContent>{children}</StudentLayoutContent>
    </StudentContextProvider>
  );
}

