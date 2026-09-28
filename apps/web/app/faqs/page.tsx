import { Metadata } from "next";
import { FaqsContent } from "./FaqsContent";

export const metadata: Metadata = {
  title: "LoksewaAI FAQs",
  description:
    "Find answers to frequently asked questions about LoksewaAI courses, syllabus, practice MCQs, timed mock exams, negative marking, payments, and account security.",
};

export default function FaqsPage() {
  return (
    <>
      <main className="flex-1 min-h-screen pt-[72px] sm:pt-[80px]">
        <FaqsContent />
      </main>
    </>
  );
}
