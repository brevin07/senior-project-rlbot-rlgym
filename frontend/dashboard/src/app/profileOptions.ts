export const rankGroups = [
  { label: "Bronze", values: ["bronze_1", "bronze_2", "bronze_3"] },
  { label: "Silver", values: ["silver_1", "silver_2", "silver_3"] },
  { label: "Gold", values: ["gold_1", "gold_2", "gold_3"] },
  { label: "Platinum", values: ["platinum_1", "platinum_2", "platinum_3"] },
  { label: "Diamond", values: ["diamond_1", "diamond_2", "diamond_3"] },
  { label: "Champion", values: ["champion_1", "champion_2", "champion_3"] },
  { label: "Grand Champion", values: ["grand_champion_1", "grand_champion_2", "grand_champion_3"] },
  { label: "Supersonic Legend", values: ["ssl"] },
] as const;

export const rankOptions = rankGroups.flatMap((group) => group.values);

export function rankTierDivisionLabel(tier: string) {
  const clean = String(tier || "").trim().toLowerCase();
  if (!clean) return "";
  if (clean === "ssl") return "SSL";
  const parts = clean.split("_");
  const last = parts[parts.length - 1] || "";
  return /^\d+$/.test(last) ? last : clean.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

export function rankTierLabel(tier: string) {
  const clean = String(tier || "").trim().toLowerCase();
  if (!clean) return "";
  if (clean === "ssl") return "Supersonic Legend";
  const parts = clean.split("_");
  const last = parts[parts.length - 1] || "";
  const hasDivision = /^\d+$/.test(last);
  const base = (hasDivision ? parts.slice(0, -1) : parts)
    .join(" ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
  return hasDivision ? `${base} ${last}` : base;
}

export const platformOptions = [
  {
    value: "epic",
    label: "Epic Games",
    shortLabel: "Epic",
    hint: "Best for the DemosEpic replay folder flow.",
    icon: "fa-gamepad",
  },
  {
    value: "steam",
    label: "Steam",
    shortLabel: "Steam",
    hint: "Uses the standard Rocket League Demos folder.",
    icon: "fa-desktop",
  },
] as const;
