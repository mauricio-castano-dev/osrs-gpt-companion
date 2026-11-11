import type { Progress } from "@/types/osrs";
import { questStatus } from "@/lib/format";
export function cachedProgress(
  snapshot: Progress | undefined,
  q: string,
  category: string,
  status: string,
): Progress | null {
  if (!snapshot?.ok) return null;
  const term = q.toLowerCase();
  const includes = (v: unknown) =>
    String(v ?? "")
      .toLowerCase()
      .includes(term);
  const result: Progress = {
    ok: true,
    cached: true,
    lastUpdated: snapshot.lastUpdated,
  };
  if (category === "all" || category === "quests") {
    result.quests = (snapshot.quests || []).filter(
      (quest) =>
        (!term || includes(quest.name) || includes(quest.displayName)) &&
        (status === "all" || questStatus(quest.state) === status),
    );
    result.total_matches = result.quests.length;
  }
  if (category === "all" || category === "diaries") {
    result.achievementDiaries = Object.create(null);
    for (const [region, diary] of Object.entries(
      snapshot.achievementDiaries || {},
    )) {
      if (term && !includes(region)) continue;
      const tiers = Object.values(diary.tiers || {});
      if (
        status !== "all" &&
        !tiers.some(
          (done) =>
            (status === "completed" && done) ||
            (status === "incomplete" && !done),
        )
      )
        continue;
      result.achievementDiaries![region] = { tiers: diary.tiers };
    }
  }
  return result;
}
