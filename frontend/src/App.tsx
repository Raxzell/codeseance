import { useCallback, useEffect, useMemo, useState } from "react";
import { askSeance, fetchHealth, fetchPresets, summonRepo } from "./api";
import { RepoSummoner } from "./components/RepoSummoner";
import { DiffInspectorModal, SeanceChat } from "./components/SeanceChat";
import { TheseusTimeline } from "./components/TheseusTimeline";
import type {
  ChatMessage,
  Citation,
  CommitNode,
  DiffInspectionTarget,
  HealthResponse,
  PresetRepoInfo,
  RepoSummary,
} from "./types";

function makeWelcomeMessage(repo: RepoSummary): ChatMessage {
  const topHotspot = repo.hotspots[0]?.file_path;
  const hotspotNote = topHotspot
    ? ` Top churn hotspot detected at \`${topHotspot}\`.`
    : "";
  return {
    id: `welcome-${repo.repo_id}-${Date.now()}`,
    role: "assistant",
    content:
      `Archive summoned for **${repo.name}** — **${repo.theseus_drift_score.toFixed(1)}%** ` +
      `rewritten since genesis (**${repo.drift_verdict}** across \`${repo.total_commits}\` commits).${hotspotNote} ` +
      `Ask any question below or click a suggested prompt to interrogate verified commit history.`,
    timestamp: new Date().toISOString(),
  };
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [presets, setPresets] = useState<PresetRepoInfo[]>([]);
  const [activeRepo, setActiveRepo] = useState<RepoSummary | null>(null);
  const [isSummoning, setIsSummoning] = useState(false);
  const [summonError, setSummonError] = useState<string | null>(null);

  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [activeCommitHash, setActiveCommitHash] = useState<string | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isAsking, setIsAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [inspectedTarget, setInspectedTarget] =
    useState<DiffInspectionTarget | null>(null);

  const activateSummonedRepo = useCallback((summary: RepoSummary) => {
    setActiveRepo(summary);
    setSelectedFile(null);
    setActiveCommitHash(null);
    setAskError(null);
    setInspectedTarget(null);
    setMessages([makeWelcomeMessage(summary)]);
  }, []);

  const handleSummonPreset = useCallback(
    async (presetId: string) => {
      setIsSummoning(true);
      setSummonError(null);
      try {
        const summary = await summonRepo({ preset_id: presetId });
        activateSummonedRepo(summary);
      } catch (err) {
        setSummonError(
          err instanceof Error ? err.message : "Failed to summon preset archive."
        );
      } finally {
        setIsSummoning(false);
      }
    },
    [activateSummonedRepo]
  );

  const handleSummonUrl = useCallback(
    async (repoUrl: string) => {
      setIsSummoning(true);
      setSummonError(null);
      try {
        const summary = await summonRepo({ repo_url: repoUrl });
        activateSummonedRepo(summary);
      } catch (err) {
        setSummonError(
          err instanceof Error ? err.message : "Failed to summon GitHub repository."
        );
      } finally {
        setIsSummoning(false);
      }
    },
    [activateSummonedRepo]
  );

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      try {
        const [healthData, presetList] = await Promise.all([
          fetchHealth(),
          fetchPresets(),
        ]);
        if (cancelled) return;
        setHealth(healthData);
        setPresets(presetList);
        if (presetList.length > 0) {
          setIsSummoning(true);
          try {
            const firstSummary = await summonRepo({
              preset_id: presetList[0].preset_id,
            });
            if (!cancelled) {
              activateSummonedRepo(firstSummary);
            }
          } catch (err) {
            if (!cancelled) {
              setSummonError(
                err instanceof Error
                  ? err.message
                  : "Could not summon initial preset."
              );
            }
          } finally {
            if (!cancelled) setIsSummoning(false);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setSummonError(
            err instanceof Error
              ? `${err.message}. Start FastAPI on port 8000.`
              : "Backend API unreachable."
          );
        }
      }
    }
    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [activateSummonedRepo]);

  const sampleQuestions = useMemo(() => {
    if (!activeRepo || activeRepo.source_type !== "preset") return [];
    const presetId = activeRepo.repo_id.replace(/^preset:/, "");
    return (
      presets.find((p) => p.preset_id === presetId)?.sample_questions ?? []
    );
  }, [activeRepo, presets]);

  const handleAsk = useCallback(
    async (question: string) => {
      if (!activeRepo) return;
      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content: question,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsAsking(true);
      setAskError(null);

      try {
        const res = await askSeance(activeRepo.repo_id, question);
        const assistantMsg: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: res.answer,
          citations: res.citations,
          mode: res.mode,
          retrievedCommitCount: res.retrieved_commit_count,
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        setAskError(
          err instanceof Error
            ? err.message
            : "Séance query failed unexpectedly."
        );
      } finally {
        setIsAsking(false);
      }
    },
    [activeRepo]
  );

  const handleInspectCommit = useCallback((commit: CommitNode) => {
    setActiveCommitHash(commit.commit_hash);
    setInspectedTarget({
      commitHash: commit.commit_hash,
      shortHash: commit.short_hash,
      author: commit.author,
      date: commit.date,
      message: commit.message,
      activeFile: commit.diffs[0]?.file_path || commit.files_changed[0] || "",
      diffs: commit.diffs,
      sourceLabel: "timeline",
    });
  }, []);

  const handleInspectCitation = useCallback(
    (citation: Citation) => {
      const matchedCommit = activeRepo?.commits.find(
        (c) => c.commit_hash === citation.commit_hash
      );
      setActiveCommitHash(citation.commit_hash);
      setInspectedTarget({
        commitHash: citation.commit_hash,
        shortHash: citation.short_hash,
        author: citation.author,
        date: citation.date,
        message: citation.commit_message,
        activeFile: citation.file_path,
        diffs: matchedCommit?.diffs ?? [],
        fallbackSnippet: citation.diff_snippet,
        sourceLabel: "citation",
      });
    },
    [activeRepo]
  );

  return (
    <div className="spectral-bg min-h-screen text-slate-100">
      <RepoSummoner
        presets={presets}
        activeRepo={activeRepo}
        health={health}
        isSummoning={isSummoning}
        summonError={summonError}
        onClearError={() => setSummonError(null)}
        onSummonPreset={handleSummonPreset}
        onSummonUrl={handleSummonUrl}
      />

      <main className="mx-auto max-w-[1600px] px-4 py-5 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <TheseusTimeline
              repo={activeRepo}
              selectedFile={selectedFile}
              activeCommitHash={activeCommitHash}
              onSelectFile={setSelectedFile}
              onInspectCommit={handleInspectCommit}
            />
          </div>

          <div className="lg:col-span-7">
            <SeanceChat
              repo={activeRepo}
              sampleQuestions={sampleQuestions}
              messages={messages}
              isAsking={isAsking}
              askError={askError}
              activeCommitHash={activeCommitHash}
              onAsk={handleAsk}
              onInspectCitation={handleInspectCitation}
            />
          </div>
        </div>
      </main>

      <DiffInspectorModal
        target={inspectedTarget}
        onClose={() => setInspectedTarget(null)}
      />
    </div>
  );
}
