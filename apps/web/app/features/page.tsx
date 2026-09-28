import { Metadata } from "next";
import { FeaturesContent } from "./FeaturesContent";

export const metadata: Metadata = {
  title: "LoksewaAI Features — Smart Loksewa Preparation",
  description:
    "Explore LoksewaAI's comprehensive suite of smart Loksewa preparation tools: syllabus-aligned courses, real-time practice, timed mock exams, AI Tutor, and student marketplace.",
};

export default function FeaturesPage() {
  return (
    <>
      <main className="flex-1 min-h-screen pt-[72px] sm:pt-[80px]">
        <FeaturesContent />
      </main>
    </>
  );
}
