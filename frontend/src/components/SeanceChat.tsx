import {
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Check,
  Copy,
  FileCode2,
  GitCommitHorizontal,
  Loader2,
  Send,
  ShieldCheck,
  Sparkles,
  Terminal,
  X,
} from "lucide-react";
import type {
  ChatMessage,
  Citation,
  DiffInspectionTarget,
  RepoSummary,
} from "../types";

interface SeanceChatProps {
  repo: RepoSummary | null;
  sampleQuestions: string[];
  messages: ChatMessage[];
  isAsking: boolean;
  askError: string | null;
  activeCommitHash: string | null;
  onAsk: (question: string) => void;
  onInspectCitation: (citation: Citation) => void;
}

const DEFAULT_PROMPTS = [
  "Why was this architecture changed?",
  "Where are the bug hotspots?",
  "Which modules stayed untouched since genesis?",
  "Summarize the architectural evolution",
];

function renderInlineMarkdown(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={idx} className="font-semibold text-slate-50">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code
          key={idx}
          className="rounded bg-void/90 px-1.5 py-0.5 font-mono text-[11px] text-ectoplasm"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return <Fragment key={idx}>{part}</Fragment>;
  });
}

function SafeMarkdownLite({ content }: { content: string }) {
  const lines = content.split("\n");
  return (
    <div className="space-y-1.5 text-xs leading-relaxed text-slate-200 sm:text-sm">
      {lines.map((line, idx) => {
        const trimmed = line.trim();
        if (!trimmed) {
          return <div key={idx} className="h-1" />;
        }
        if (trimmed.startsWith("- ")) {
          return (
            <div key={idx} className="flex items-start gap-2 pl-1">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ectoplasm/80" />
              <div className="min-w-0 flex-1 break-words">
                {renderInlineMarkdown(trimmed.slice(2))}
              </div>
            </div>
          );
        }
        return (
          <p key={idx} className="break-words">
            {renderInlineMarkdown(line)}
          </p>
        );
      })}
    </div>
  );
}

function StreamingAssistantText({
  content,
  animate,
}: {
  content: string;
  animate: boolean;
}) {
  const [visibleChars, setVisibleChars] = useState(
    animate ? Math.min(24, content.length) : content.length
  );

  useEffect(() => {
    if (!animate) {
      setVisibleChars(content.length);
      return;
    }
    setVisibleChars(Math.min(24, content.length));
    const timer = window.setInterval(() => {
      setVisibleChars((prev) => {
        if (prev >= content.length) {
          window.clearInterval(timer);
          return content.length;
        }
        return Math.min(content.length, prev + 28);
      });
    }, 16);
    return () => window.clearInterval(timer);
  }, [content, animate]);

  const shown = content.slice(0, visibleChars);
  const isStreaming = visibleChars < content.length;

  return (
    <div>
      <SafeMarkdownLite content={shown} />
      {isStreaming && (
        <span className="mt-1 inline-block h-3.5 w-1.5 animate-pulse bg-ectoplasm align-middle" />
      )}
    </div>
  );
}

export function SeanceChat({
  repo,
  sampleQuestions,
  messages,
  isAsking,
  askError,
  activeCommitHash,
  onAsk,
  onInspectCitation,
}: SeanceChatProps) {
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const prompts = useMemo(
    () => (sampleQuestions.length > 0 ? sampleQuestions : DEFAULT_PROMPTS),
    [sampleQuestions]
  );

  const lastAssistantId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === "assistant" && messages[i].mode) {
        return messages[i].id;
      }
    }
    return null;
  }, [messages]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length, isAsking]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cleaned = draft.trim();
    if (!cleaned || !repo || isAsking) return;
    setDraft("");
    onAsk(cleaned);
  };

  return (
    <section className="flex flex-col overflow-hidden rounded-2xl border border-slate-800/90 bg-crypt/90 lg:h-[calc(100vh-295px)] lg:min-h-[540px]">
      {/* Console Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/90 bg-panel/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-ectoplasm" />
          <div>
            <h2 className="font-display text-sm font-semibold tracking-wide text-slate-100">
              Grounded Séance Console
            </h2>
            <p className="text-[11px] text-slate-400">
              {repo
                ? `Channeling verified commits from ${repo.name}`
                : "Summon a repository to open the séance channel"}
            </p>
          </div>
        </div>

        <span className="inline-flex items-center gap-1.5 rounded-full border border-ectoplasm/35 bg-ectoplasm/10 px-2.5 py-1 font-mono text-[10px] text-ectoplasm">
          <ShieldCheck className="h-3.5 w-3.5" />
          Zero-Hallucination Citation Guard
        </span>
      </div>

      {/* Suggested Prompts */}
      <div className="border-b border-slate-800/70 bg-void/40 px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 font-mono text-[10px] uppercase tracking-wider text-slate-500">
            Prompts:
          </span>
          {prompts.map((prompt) => (
            <button
              key={prompt}
              type="button"
              disabled={!repo || isAsking}
              onClick={() => onAsk(prompt)}
              className="rounded-full border border-slate-700/80 bg-panel/80 px-2.5 py-1 text-[11px] text-slate-300 transition hover:border-ectoplasm/55 hover:bg-ectoplasm/10 hover:text-ectoplasm disabled:cursor-not-allowed disabled:opacity-45"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>

      {/* Transcript */}
      <div
        ref={scrollRef}
        className="spectral-scroll flex-1 space-y-4 overflow-y-auto p-4"
      >
        {messages.map((msg) => {
          if (msg.role === "user") {
            return (
              <div key={msg.id} className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-br-sm border border-ectoplasm/35 bg-ectoplasm/15 px-4 py-2.5 text-xs text-slate-100 sm:text-sm">
                  {msg.content}
                </div>
              </div>
            );
          }

          return (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className="rounded-2xl rounded-bl-sm border border-slate-800 bg-panel/80 p-4"
            >
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/70 pb-2">
                <div className="flex items-center gap-1.5 font-mono text-[11px] text-ectoplasm">
                  <Sparkles className="h-3.5 w-3.5" />
                  <span>Archive Spirit</span>
                </div>
                <div className="flex items-center gap-2 font-mono text-[10px]">
                  {msg.mode && (
                    <span
                      className={`rounded-full border px-2 py-0.5 uppercase ${
                        msg.mode === "llm"
                          ? "border-ectoplasm/40 bg-ectoplasm/10 text-ectoplasm"
                          : "border-parchment/40 bg-parchment/10 text-parchment"
                      }`}
                    >
                      {msg.mode === "llm" ? "LLM Grounded" : "Extractive Mode"}
                    </span>
                  )}
                  {typeof msg.retrievedCommitCount === "number" && (
                    <span className="text-slate-500">
                      {msg.retrievedCommitCount} commits matched
                    </span>
                  )}
                </div>
              </div>

              <StreamingAssistantText
                content={msg.content}
                animate={msg.id === lastAssistantId}
              />

              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-3 border-t border-slate-800/70 pt-3">
                  <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-slate-400">
                    Verified Commit Citations (click to inspect raw diff):
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {msg.citations.map((cit) => {
                      const isSelected = activeCommitHash === cit.commit_hash;
                      return (
                        <button
                          key={`${msg.id}-${cit.commit_hash}-${cit.file_path}`}
                          type="button"
                          onClick={() => onInspectCitation(cit)}
                          className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 font-mono text-[11px] transition ${
                            isSelected
                              ? "border-ectoplasm bg-ectoplasm/20 text-white shadow-spectral"
                              : "border-ectoplasm/35 bg-void/85 text-ectoplasm hover:border-ectoplasm hover:bg-ectoplasm/15"
                          }`}
                        >
                          <GitCommitHorizontal className="h-3 w-3" />
                          <span className="font-semibold">
                            [{cit.short_hash}]
                          </span>
                          <span className="max-w-[180px] truncate text-slate-300">
                            {cit.file_path}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </motion.div>
          );
        })}

        {isAsking && (
          <div className="flex items-center gap-2 rounded-xl border border-slate-800 bg-panel/60 px-4 py-3 font-mono text-xs text-ectoplasm">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>Cross-examining commit ledger and verifying citations...</span>
          </div>
        )}

        {askError && (
          <div
            role="alert"
            className="rounded-xl border border-crimson/40 bg-crimson/10 px-4 py-2.5 text-xs text-rose-200"
          >
            {askError}
          </div>
        )}
      </div>

      {/* Query Composer */}
      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2 border-t border-slate-800/90 bg-panel/70 p-3"
      >
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={!repo || isAsking}
          placeholder={
            repo
              ? `Ask ${repo.name} why legacy code was written or changed...`
              : "Summon a repository first..."
          }
          className="flex-1 rounded-xl border border-slate-700/80 bg-void/90 px-3.5 py-2.5 text-xs text-slate-100 placeholder:text-slate-500 focus:border-ectoplasm/70 focus:outline-none focus:ring-2 focus:ring-ectoplasm/20 sm:text-sm"
        />
        <button
          type="submit"
          disabled={!repo || isAsking || !draft.trim()}
          className="inline-flex items-center gap-1.5 rounded-xl border border-ectoplasm/50 bg-ectoplasm/20 px-4 py-2.5 font-mono text-xs font-semibold text-ectoplasm transition hover:bg-ectoplasm/30 disabled:cursor-not-allowed disabled:opacity-45 sm:text-sm"
        >
          <Send className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Ask Archive</span>
        </button>
      </form>
    </section>
  );
}

export function DiffInspectorModal({
  target,
  onClose,
}: {
  target: DiffInspectionTarget | null;
  onClose: () => void;
}) {
  const [selectedPath, setSelectedPath] = useState<string>("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!target) return;
    setSelectedPath(target.activeFile || target.diffs[0]?.file_path || "");
    setCopied(false);

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [target, onClose]);

  const activeDiff = useMemo(() => {
    if (!target || target.diffs.length === 0) return null;
    return (
      target.diffs.find((d) => d.file_path === selectedPath) ?? target.diffs[0]
    );
  }, [target, selectedPath]);

  const rawDiff = activeDiff?.diff_snippet || target?.fallbackSnippet || "";

  const handleCopyHash = async () => {
    if (!target || !navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(target.commitHash);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Ignore clipboard failures in restricted browsers
    }
  };

  return (
    <AnimatePresence>
      {target && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 12 }}
            transition={{ duration: 0.18 }}
            onClick={(e) => e.stopPropagation()}
            className="flex max-h-[86vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-ectoplasm/40 bg-crypt shadow-2xl shadow-black"
          >
            {/* Modal Header */}
            <div className="flex items-start justify-between gap-4 border-b border-slate-800 bg-panel/90 px-5 py-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded border border-ectoplasm/45 bg-ectoplasm/15 px-2 py-0.5 font-mono text-xs font-semibold text-ectoplasm">
                    [{target.shortHash}]
                  </span>
                  <span className="rounded border border-slate-700 bg-void px-2 py-0.5 font-mono text-[10px] uppercase text-slate-300">
                    {target.sourceLabel === "citation"
                      ? "Verified Citation"
                      : "Commit Snapshot"}
                  </span>
                  <button
                    type="button"
                    onClick={handleCopyHash}
                    className="inline-flex items-center gap-1 rounded border border-slate-700 bg-void/80 px-2 py-0.5 font-mono text-[10px] text-slate-400 hover:border-ectoplasm/50 hover:text-ectoplasm"
                  >
                    {copied ? (
                      <>
                        <Check className="h-3 w-3 text-emerald-400" />
                        Copied SHA
                      </>
                    ) : (
                      <>
                        <Copy className="h-3 w-3" />
                        {target.commitHash.slice(0, 14)}…
                      </>
                    )}
                  </button>
                </div>

                <h3 className="mt-2 text-sm font-semibold text-slate-100 sm:text-base">
                  {target.message || "(no commit message)"}
                </h3>
                <p className="mt-1 font-mono text-[11px] text-slate-400">
                  Author: <span className="text-slate-200">{target.author}</span>{" "}
                  · Date: <span className="text-slate-200">{target.date}</span>
                </p>
              </div>

              <button
                type="button"
                onClick={onClose}
                aria-label="Close diff modal"
                className="rounded-lg border border-slate-700 p-1.5 text-slate-400 hover:border-slate-500 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* File Switcher Tabs */}
            {target.diffs.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 border-b border-slate-800/80 bg-void/60 px-5 py-2.5">
                {target.diffs.map((diff) => {
                  const selected = activeDiff?.file_path === diff.file_path;
                  return (
                    <button
                      key={diff.file_path}
                      type="button"
                      onClick={() => setSelectedPath(diff.file_path)}
                      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 font-mono text-[11px] transition ${
                        selected
                          ? "border-ectoplasm/60 bg-ectoplasm/15 text-ectoplasm"
                          : "border-slate-800 bg-panel/70 text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      <FileCode2 className="h-3 w-3" />
                      <span>{diff.file_path}</span>
                      <span className="text-[10px] text-emerald-400">
                        +{diff.additions}
                      </span>
                      <span className="text-[10px] text-crimson">
                        -{diff.deletions}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}

            {/* Symbols Bar */}
            {activeDiff && activeDiff.symbols.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 border-b border-slate-800/70 bg-panel/40 px-5 py-2 font-mono text-[10px]">
                <span className="text-slate-500">Extracted Symbols:</span>
                {activeDiff.symbols.map((sym) => (
                  <span
                    key={sym}
                    className="rounded border border-parchment/30 bg-parchment/10 px-1.5 py-0.5 text-parchment"
                  >
                    {sym}
                  </span>
                ))}
              </div>
            )}

            {/* Color-Coded Raw Diff Viewer */}
            <div className="spectral-scroll flex-1 overflow-auto bg-void p-4 font-mono text-xs leading-relaxed">
              {rawDiff ? (
                rawDiff.split("\n").map((line, idx) => {
                  let lineStyle = "text-slate-300";
                  if (line.startsWith("+") && !line.startsWith("+++")) {
                    lineStyle =
                      "bg-emerald-500/10 text-emerald-300 border-l-2 border-emerald-500/60";
                  } else if (line.startsWith("-") && !line.startsWith("---")) {
                    lineStyle =
                      "bg-crimson/10 text-rose-300 border-l-2 border-crimson/60";
                  } else if (line.startsWith("@@")) {
                    lineStyle = "bg-parchment/10 text-parchment";
                  }
                  return (
                    <div
                      key={idx}
                      className={`whitespace-pre-wrap break-all px-2.5 py-0.5 ${lineStyle}`}
                    >
                      {line || " "}
                    </div>
                  );
                })
              ) : (
                <div className="rounded-xl border border-dashed border-slate-800 p-6 text-center text-slate-500">
                  No raw unified diff hunk stored for this file (binary, metadata-only, or truncated).
                </div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
