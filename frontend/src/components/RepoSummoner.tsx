import { useState, type FormEvent } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  Cpu,
  ExternalLink,
  Flame,
  GitBranch,
  Loader2,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import type { HealthResponse, PresetRepoInfo, RepoSummary } from "../types";

interface RepoSummonerProps {
  presets: PresetRepoInfo[];
  activeRepo: RepoSummary | null;
  health: HealthResponse | null;
  isSummoning: boolean;
  summonError: string | null;
  onClearError: () => void;
  onSummonPreset: (presetId: string) => void;
  onSummonUrl: (repoUrl: string) => void;
}

const GAUGE_RADIUS = 44;
const GAUGE_CIRCUMFERENCE = 2 * Math.PI * GAUGE_RADIUS;

function getDriftColors(score: number): {
  stroke: string;
  badgeClass: string;
  textClass: string;
} {
  if (score < 20) {
    return {
      stroke: "#2dd4bf",
      badgeClass: "border-ectoplasm/40 bg-ectoplasm/10 text-ectoplasm",
      textClass: "text-ectoplasm",
    };
  }
  if (score < 50) {
    return {
      stroke: "#38bdf8",
      badgeClass: "border-sky-400/40 bg-sky-400/10 text-sky-300",
      textClass: "text-sky-300",
    };
  }
  if (score < 80) {
    return {
      stroke: "#f59e0b",
      badgeClass: "border-parchment/40 bg-parchment/10 text-parchment",
      textClass: "text-parchment",
    };
  }
  return {
    stroke: "#f43f5e",
    badgeClass: "border-crimson/40 bg-crimson/10 text-crimson",
    textClass: "text-crimson",
  };
}

function formatShortDate(iso: string): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

export function RepoSummoner({
  presets,
  activeRepo,
  health,
  isSummoning,
  summonError,
  onClearError,
  onSummonPreset,
  onSummonUrl,
}: RepoSummonerProps) {
  const [urlInput, setUrlInput] = useState("");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cleaned = urlInput.trim();
    if (!cleaned || isSummoning) return;
    onSummonUrl(cleaned);
  };

  const driftScore = activeRepo ? activeRepo.theseus_drift_score : 0;
  const clampedDrift = Math.max(0, Math.min(100, driftScore));
  const strokeDashoffset =
    GAUGE_CIRCUMFERENCE * (1 - clampedDrift / 100);
  const colors = getDriftColors(clampedDrift);

  const topLanguages = activeRepo
    ? Object.entries(activeRepo.languages).slice(0, 3)
    : [];

  return (
    <header className="border-b border-slate-800/80 bg-crypt/90 backdrop-blur-md">
      <div className="mx-auto max-w-[1600px] px-4 py-4 sm:px-6 lg:px-8">
        {/* Top Masthead + Status */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-ectoplasm/40 bg-ectoplasm/10 shadow-spectral">
              <Sparkles className="h-5 w-5 text-ectoplasm" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="font-display text-xl font-bold tracking-wider text-slate-50 sm:text-2xl">
                  CodeSéance
                </h1>
                <span className="rounded-full border border-parchment/30 bg-parchment/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-parchment">
                  Frankenstein Archive
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Summoning the ghosts of past commits to explain why legacy code exists
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-xs ${
                health
                  ? health.llm_configured
                    ? "border-ectoplasm/40 bg-ectoplasm/10 text-ectoplasm"
                    : "border-parchment/35 bg-parchment/10 text-parchment"
                  : "border-slate-700 bg-slate-900 text-slate-400"
              }`}
            >
              <Cpu className="h-3.5 w-3.5" />
              {health
                ? health.llm_configured
                  ? `LLM Mode (${health.llm_provider.toUpperCase()})`
                  : "Zero-Key Extractive Mode"
                : "Connecting to Archive..."}
            </span>
          </div>
        </div>

        {/* Controls + Ship of Theseus Drift Gauge */}
        <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-12">
          {/* Left: URL Input + 3 Demo Presets */}
          <div className="flex flex-col gap-3 xl:col-span-8">
            <form
              onSubmit={handleSubmit}
              className="flex flex-col gap-2 sm:flex-row"
            >
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                <input
                  type="url"
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  placeholder="https://github.com/fastapi/fastapi (public GitHub repo, shallow cap 60 commits)"
                  aria-label="Public GitHub Repository URL"
                  className="w-full rounded-xl border border-slate-700/80 bg-void/90 py-2.5 pl-10 pr-4 font-mono text-xs text-slate-100 placeholder:text-slate-500 focus:border-ectoplasm/70 focus:outline-none focus:ring-2 focus:ring-ectoplasm/20 sm:text-sm"
                />
              </div>
              <button
                type="submit"
                disabled={isSummoning || !urlInput.trim()}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-ectoplasm/50 bg-ectoplasm/15 px-5 py-2.5 font-mono text-xs font-semibold uppercase tracking-wider text-ectoplasm transition hover:bg-ectoplasm/25 disabled:cursor-not-allowed disabled:opacity-45 sm:text-sm"
              >
                {isSummoning ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Summoning...
                  </>
                ) : (
                  <>
                    <Flame className="h-4 w-4" />
                    Summon Repo
                  </>
                )}
              </button>
            </form>

            {summonError && (
              <div
                role="alert"
                className="flex items-start justify-between gap-3 rounded-xl border border-crimson/40 bg-crimson/10 px-3.5 py-2.5 text-xs text-rose-200"
              >
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-crimson" />
                  <span>{summonError}</span>
                </div>
                <button
                  type="button"
                  onClick={onClearError}
                  aria-label="Dismiss error"
                  className="text-rose-300 hover:text-white"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}

            {/* 1-Click Offline Demo Presets */}
            <div className="grid grid-cols-1 gap-2.5 md:grid-cols-3">
              {presets.map((preset) => {
                const isSelected =
                  activeRepo?.repo_id === `preset:${preset.preset_id}`;
                return (
                  <motion.button
                    key={preset.preset_id}
                    type="button"
                    whileHover={{ y: -2 }}
                    whileTap={{ scale: 0.99 }}
                    disabled={isSummoning}
                    onClick={() => onSummonPreset(preset.preset_id)}
                    className={`group flex flex-col justify-between rounded-xl border p-3 text-left transition ${
                      isSelected
                        ? "border-ectoplasm/65 bg-ectoplasm/10 shadow-spectral"
                        : "border-slate-800 bg-panel/80 hover:border-slate-700 hover:bg-panel"
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-semibold text-sm text-slate-100 group-hover:text-ectoplasm">
                          {preset.name}
                        </span>
                        <span className="shrink-0 rounded-md border border-slate-700 bg-void/70 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
                          {preset.language}
                        </span>
                      </div>
                      <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-slate-400">
                        {preset.tagline}
                      </p>
                    </div>

                    <div className="mt-2.5 flex items-center justify-between border-t border-slate-800/80 pt-2 font-mono text-[11px]">
                      <span className="text-slate-400">
                        {preset.commit_count} commits
                      </span>
                      <span className="text-parchment">
                        {preset.estimated_drift.toFixed(1)}% drift
                      </span>
                    </div>
                  </motion.button>
                );
              })}
            </div>
          </div>

          {/* Right: Animated Ship-of-Theseus Drift Gauge */}
          <div className="flex items-center justify-between gap-4 rounded-2xl border border-slate-800/90 bg-panel/85 p-4 xl:col-span-4">
            <div className="relative flex h-28 w-28 shrink-0 items-center justify-center">
              <svg className="h-28 w-28 -rotate-90" viewBox="0 0 104 104">
                <circle
                  cx="52"
                  cy="52"
                  r={GAUGE_RADIUS}
                  fill="none"
                  stroke="rgba(51, 65, 85, 0.45)"
                  strokeWidth="8"
                />
                <motion.circle
                  cx="52"
                  cy="52"
                  r={GAUGE_RADIUS}
                  fill="none"
                  stroke={colors.stroke}
                  strokeWidth="8"
                  strokeLinecap="round"
                  strokeDasharray={GAUGE_CIRCUMFERENCE}
                  initial={{ strokeDashoffset: GAUGE_CIRCUMFERENCE }}
                  animate={{ strokeDashoffset }}
                  transition={{ duration: 0.9, ease: "easeOut" }}
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                <span className={`font-mono text-xl font-bold ${colors.textClass}`}>
                  {activeRepo ? `${clampedDrift.toFixed(1)}%` : "—"}
                </span>
                <span className="text-[9px] uppercase tracking-wider text-slate-400">
                  Theseus Drift
                </span>
              </div>
            </div>

            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate font-semibold text-sm text-slate-100">
                  {activeRepo ? activeRepo.name : "No Archive Summoned"}
                </span>
                {activeRepo?.source_url && (
                  <a
                    href={activeRepo.source_url}
                    target="_blank"
                    rel="noreferrer"
                    title="Open GitHub Repository"
                    className="text-slate-400 hover:text-ectoplasm"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}
              </div>

              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                <span
                  className={`inline-flex rounded-full border px-2.5 py-0.5 font-mono text-[11px] font-medium ${colors.badgeClass}`}
                >
                  {activeRepo ? activeRepo.drift_verdict : "Awaiting Summons"}
                </span>
                {activeRepo && (
                  <span className="text-[11px] text-slate-400">
                    Rewritten Since Genesis
                  </span>
                )}
              </div>

              {activeRepo && (
                <div className="mt-2.5 flex flex-wrap items-center gap-2 font-mono text-[11px] text-slate-400">
                  <span className="inline-flex items-center gap-1 rounded bg-void/70 px-2 py-0.5 text-slate-300">
                    <GitBranch className="h-3 w-3 text-ectoplasm" />
                    {activeRepo.total_commits} commits
                  </span>
                  <span className="rounded bg-void/70 px-2 py-0.5">
                    {formatShortDate(activeRepo.genesis_date)} →{" "}
                    {formatShortDate(activeRepo.latest_date)}
                  </span>
                  {topLanguages.map(([lang, count]) => (
                    <span
                      key={lang}
                      className="rounded border border-slate-800 bg-void/60 px-1.5 py-0.5 text-[10px] text-slate-300"
                    >
                      {lang} ({count})
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
