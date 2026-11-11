export interface Item {
  name?: string;
  itemId?: number;
  quantity?: number;
  slot?: number;
}
export interface Offer extends Item {
  state?: string;
  quantitySold?: number;
  totalQuantity?: number;
  price?: number;
}
export interface Activity {
  patch?: string;
  region?: string;
  crop?: string;
  space?: string;
  house?: string;
  state?: string;
  readyAt?: string;
  stage?: number;
  stages?: number;
}
export interface Daily {
  unlocked?: boolean;
  claimed?: boolean;
  claimedCount?: number;
  max?: number;
}
export interface Stats {
  ok?: boolean;
  player?: { username?: string; combatLevel?: number; world?: number };
  questPoints?: number;
  skills?: Record<string, number | { level?: number }>;
  timers?: {
    farming?: Activity[] | { entries?: Activity[]; active_count?: number };
    birdhouses?: Activity[] | { entries?: Activity[] };
  };
  dailies?: Record<string, Daily | unknown>;
  slayer?: {
    masterName?: string;
    points?: number;
    streak?: number;
    amount?: number;
    creatureName?: string;
    taskName?: string;
    creatureId?: number;
  };
  killCounts?: Record<string, number>;
}
export interface Items {
  ok?: boolean;
  bank?: {
    items?: Item[];
    total_matches?: number;
    bank_total_items?: number;
    truncated?: boolean;
  };
  inventory?: Item[];
  equipment?: Record<string, Item>;
  grandExchange?: Offer[];
  currency?: {
    bank?: { gp_equivalent: number } | null;
    inventory?: { gp_equivalent: number } | null;
  };
}
export interface Quest {
  name?: string;
  displayName?: string;
  state?: string;
}
export interface Task {
  name?: string;
  tier?: string;
  monster?: string;
  completed?: boolean;
  id?: number;
}
export interface Diary {
  tiers?: Record<string, boolean>;
  tasks?: Task[];
  total_matches?: number;
  truncated?: boolean;
}
export interface Progress {
  ok?: boolean;
  lastUpdated?: string;
  quests?: Quest[];
  total_matches?: number;
  truncated?: boolean;
  finished_count?: number;
  in_progress_count?: number;
  not_started_count?: number;
  achievementDiaries?: Record<string, Diary>;
  combatAchievements?: {
    available?: boolean;
    tiers?: Record<string, { completed?: number; total?: number }>;
    tasks?: Task[];
    total_matches?: number;
    truncated?: boolean;
  };
  cached?: boolean;
}
export interface Status {
  stats: Stats;
  items: Items;
  quests: Progress;
  model: string;
  state_file: string;
  lastUpdated?: string;
  freshness?: string;
  busy?: boolean;
  active_tools?: ToolUse[];
}
export interface ToolUse {
  name: string;
  ok: boolean;
}
export interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  tools_used?: ToolUse[];
  lastUpdated?: string;
  freshness?: string;
}
export interface ChatReply {
  reply: string;
  tools_used: ToolUse[];
  lastUpdated?: string;
  freshness?: string;
}
export interface Memory {
  id: number;
  tema: string;
  contenido: string;
  created_at?: string;
}
export interface GEItem {
  name: string;
  high?: number | null;
  low?: number | null;
  highTime?: number | null;
  lowTime?: number | null;
  limit?: number | null;
  highalch?: number | null;
}
export interface GE {
  ok?: boolean;
  matches: GEItem[];
  truncated?: boolean;
}
export interface Wiki {
  ok?: boolean;
  extract?: string;
  results: { title: string; url: string }[];
  truncated?: boolean;
}
export interface Model {
  slug: string;
  display_name: string;
}
export type Section = "chat" | "state" | "gear" | "oracle" | "memory";
