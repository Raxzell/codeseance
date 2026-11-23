import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Bug,
  Code2,
  FileWarning,
  Filter,
  GitCommitHorizontal,
  History,
  ShieldCheck,
  X,
} from "lucide-react";
import type { CommitNode, RepoSummary } from "../types";

interface TheseusTimelineProps {
  repo: RepoSummary | null;
  selectedFile: string | null;
  activeCommitHash: string | null;
  onSelectFile: (filePath: string | null) => void;
  onInspectCommit: (commit: CommitNode) => void;
}

export function TheseusTimeline({
  repo,
  selectedFile,
  activeCommitHash,
  onSelectFile,
  onInspectCommit,
}: TheseusTimelineProps) {
  const [bugfixOnly, setBugfixOnly] = useState(false);

  const genesisHash = useMemo(() => {
    if (!repo || repo.commits.length === 0) return null;
    return repo.commits[repo.commits.length - 1].commit_hash;
  }, [repo]);

  const filteredCommits = useMemo(() => {
    if (!repo) return [];
    return repo.commits.filter((commit) => {
      if (bugfixOnly && !commit.is_bugfix) return false;
      if (selectedFile && !commit.files_changed.includes(selectedFile)) {
        return false;
      }
      return true;
    });
  }, [repo, selectedFile, bugfixOnly]);

  if (!repo) {
    return (
      <section className="flex h-full min-h-[420px] flex-col items-center justify-center rounded-2xl border border-slate-800/90 bg-crypt/85 p-8 text-center">
        <History className="h-10 w-10 text-slate-600" />
        <h2 className="mt-3 font-display text-lg text-slate-300">
          Timeline Dormant
        </h2>
        <p className="mt-1 max-w-xs text-xs text-slate-500">
          Select a demo preset or paste a public GitHub URL above to exhume its commit chronology and file hotspots.
        </p>
      </section>
    );
  }

  return (
    <section className="flex flex-col overflow-hidden rounded-2xl border border-slate-800/90 bg-crypt/90 lg:h-[calc(100vh-295px)] lg:min-h-[540px]">
      {/* File Hotspot Radar */}
      <div className="border-b border-slate-800/90 bg-panel/60 p-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <FileWarning className="h-4 w-4 text-parchment" />
            <h2 className="font-display text-sm font-semibold tracking-wide text-slate-100">
              File Hotspot Radar
            </h2>
          </div>
          <span className="font-mono text-[11px] text-slate-400">
            Click file to filter ({repo.hotspots.length} files)
          </span>
        </div>

        <div className="spectral-scroll mt-3 max-h-44 space-y-2 overflow-y-auto pr-1">
          {repo.hotspots.length === 0 ? (
            <p className="text-xs text-slate-500">No file churn recorded.</p>
          ) : (
            repo.hotspots.map((hotspot) => {
              const isActive = selectedFile === hotspot.file_path;
              const isRelic = hotspot.drift_score === 0;
              return (
                <button
                  key={hotspot.file_path}
                  type="button"
                  onClick={() =>
                    onSelectFile(isActive ? null : hotspot.file_path)
                  }
                  className={`w-full rounded-xl border px-3 py-2 text-left transition ${
                    isActive
                      ? "border-ectoplasm/70 bg-ectoplasm/10 shadow-spectral"
                      : "border-slate-800 bg-void/70 hover:border-slate-700 hover:bg-void"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-mono text-xs font-medium text-slate-100">
                      {hotspot.file_path}
                    </span>
                    <div className="flex shrink-0 items-center gap-1.5 font-mono text-[10px]">
                      {isRelic && (
                        <span className="inline-flex items-center gap-1 rounded border border-ectoplasm/40 bg-ectoplasm/10 px-1.5 py-0.5 text-ectoplasm">
                          <ShieldCheck className="h-3 w-3" />
                          0% Relic
                        </span>
                      )}
                      {hotspot.bugfix_count > 0 && (
                        <span className="inline-flex items-center gap-1 rounded border border-crimson/40 bg-crimson/10 px-1.5 py-0.5 text-crimson">
                          <Bug className="h-3 w-3" />
                          {hotspot.bugfix_count} fix
                        </span>
                      )}
                      <span className="text-slate-400">
                        {hotspot.commit_count}c · {hotspot.drift_score.toFixed(0)}%
                      </span>
                    </div>
                  </div>

                  {/* Drift / Churn Bar */}
                  <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                    <div
                      className={`h-full rounded-full transition-all ${
                        hotspot.drift_score === 0
                          ? "bg-ectoplasm"
                          : hotspot.drift_score >= 80
                            ? "bg-crimson"
                            : "bg-parchment"
                      }`}
                      style={{
                        width: `${Math.max(4, Math.min(100, hotspot.drift_score))}%`,
                      }}
                    />
                  </div>

                  {hotspot.symbols.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-1">
                      <Code2 className="h-3 w-3 text-slate-500" />
                      {hotspot.symbols.slice(0, 3).map((sym) => (
                        <span
                          key={sym}
                          className="rounded bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] text-slate-400"
                        >
                          {sym}
                        </span>
                      ))}
                    </div>
                  )}
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Timeline Filter Controls */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 px-4 py-2.5 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5 font-medium text-slate-200">
            <GitCommitHorizontal className="h-4 w-4 text-ectoplasm" />
            <span>Commit Chronology</span>
          </div>
          <span className="font-mono text-[11px] text-slate-400">
            ({filteredCommits.length}/{repo.total_commits})
          </span>
          {selectedFile && (
            <button
              type="button"
              onClick={() => onSelectFile(null)}
              className="inline-flex items-center gap-1 rounded-full border border-ectoplasm/45 bg-ectoplasm/10 px-2 py-0.5 font-mono text-[10px] text-ectoplasm hover:bg-ectoplasm/20"
            >
              <Filter className="h-2.5 w-2.5" />
              {selectedFile}
              <X className="h-3 w-3" />
            </button>
          )}
        </div>

        <button
          type="button"
          onClick={() => setBugfixOnly((prev) => !prev)}
          className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 font-mono text-[11px] transition ${
            bugfixOnly
              ? "border-crimson/55 bg-crimson/15 text-crimson"
              : "border-slate-700 bg-void/70 text-slate-400 hover:text-slate-200"
          }`}
        >
          <Bug className="h-3 w-3" />
          Bugfixes Only
        </button>
      </div>

      {/* Vertical Commit Chronology */}
      <div className="spectral-scroll flex-1 overflow-y-auto p-4">
        {filteredCommits.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-800 p-6 text-center text-xs text-slate-500">
            No commits match the current filter.
          </div>
        ) : (
          <div className="relative space-y-3 pl-5 before:absolute before:bottom-2 before:left-1.5 before:top-2 before:w-px before:bg-slate-800">
            {filteredCommits.map((commit, idx) => {
              const isGenesis = commit.commit_hash === genesisHash;
              const isHighlighted = activeCommitHash === commit.commit_hash;
              return (
                <motion.div
                  key={commit.commit_hash}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.2, delay: Math.min(idx * 0.02, 0.25) }}
                  className="relative"
                >
                  {/* Node Marker */}
                  <span
                    className={`absolute -left-[18px] top-3.5 h-2.5 w-2.5 rounded-full ring-4 ring-crypt ${
                      isGenesis
                        ? "bg-parchment"
                        : commit.is_bugfix
                          ? "bg-crimson"
                          : "bg-ectoplasm"
                    }`}
                  />

                  <button
                    type="button"
                    onClick={() => onInspectCommit(commit)}
                    className={`w-full rounded-xl border p-3 text-left transition ${
                      isHighlighted
                        ? "border-ectoplasm/75 bg-ectoplasm/10 shadow-spectral"
                        : "border-slate-800/90 bg-panel/70 hover:border-slate-700 hover:bg-panel"
                    }`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="rounded border border-ectoplasm/35 bg-void px-1.5 py-0.5 font-mono text-[11px] font-semibold text-ectoplasm">
                          {commit.short_hash}
                        </span>
                        {isGenesis && (
                          <span className="rounded border border-parchment/45 bg-parchment/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase text-parchment">
                            Genesis
                          </span>
                        )}
                        {commit.is_bugfix && (
                          <span className="rounded border border-crimson/45 bg-crimson/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase text-crimson">
                            Bugfix
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2 font-mono text-[11px]">
                        <span className="text-emerald-400">
                          +{commit.additions}
                        </span>
                        <span className="text-crimson">-{commit.deletions}</span>
                        <span className="text-slate-500">
                          {commit.date.slice(0, 10)}
                        </span>
                      </div>
                    </div>

                    <p className="mt-1.5 text-xs font-medium leading-snug text-slate-100">
                      {commit.message || "(no commit message)"}
                    </p>

                    <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
                      <span>by {commit.author}</span>
                      <div className="flex flex-wrap gap-1">
                        {commit.files_changed.slice(0, 3).map((fp) => (
                          <span
                            key={fp}
                            className="max-w-[160px] truncate rounded bg-void/90 px-1.5 py-0.5 font-mono text-[10px] text-slate-400"
                          >
                            {fp}
                          </span>
                        ))}
                        {commit.files_changed.length > 3 && (
                          <span className="rounded bg-void/90 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
                            +{commit.files_changed.length - 3}
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
