import { Metadata } from "next";
import { PlayAndEarnContent } from "./PlayAndEarnContent";

export const metadata: Metadata = {
  title: "LoksewaAI Play & Earn — Learn, Play & Earn XP",
  description:
    "Learn, play, earn XP, maintain your streak, and climb the leaderboard. Discover LoksewaAI's gamification system designed to keep your exam preparation consistent.",
};

export default function PlayAndEarnPage() {
  return (
    <>
      <main className="flex-1 min-h-screen pt-[72px] sm:pt-[80px]">
        <PlayAndEarnContent />
      </main>
    </>
  );
}
