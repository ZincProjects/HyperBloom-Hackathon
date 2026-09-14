import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import AnalysisPanel from "./components/AnalysisPanel.jsx";
import IncidentView from "./components/IncidentView.jsx";
import ReportModal from "./components/ReportModal.jsx";
import Sidebar from "./components/Sidebar.jsx";
import StatsBar from "./components/StatsBar.jsx";
import ThreatMap from "./components/ThreatMap.jsx";
import { Button } from "./components/ui.jsx";

const AUTOPLAY_INTERVAL_MS = 2500;
const AUTOPLAY_MAX_EXCHANGES = 8; // cost guard: auto-play pauses here

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function ModeBadge({ health }) {
  if (!health) return null;
  if (health.llm_mode === "live") {
    return (
      <span className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 font-mono text-[11px] text-emerald-300">
        ● LIVE · {health.chat_model}
      </span>
    );
  }
  return (
    <span
      title="Set ANTHROPIC_API_KEY in backend/.env and restart the backend for live Claude conversations"
      className="rounded-full border border-amber-400/40 bg-amber-400/10 px-2.5 py-1 font-mono text-[11px] text-amber-300"
    >
      ● OFFLINE MOCK LLM
    </span>
  );
}

export default function App() {
  const [tab, setTab] = useState("live");
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [personas, setPersonas] = useState([]);
  const [scripts, setScripts] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [threatMap, setThreatMap] = useState(null);
  const [report, setReport] = useState(null);

  const [starting, setStarting] = useState(false);
  const [responding, setResponding] = useState(false);
  const [closing, setClosing] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [autoPlay, setAutoPlay] = useState(false);
  const [toast, setToast] = useState(null);

  const selectedRef = useRef(null);
  const inFlightRef = useRef(null);

  const notify = useCallback((message, tone = "error") => {
    setToast({ message, tone, key: Date.now() });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), toast.tone === "error" ? 7000 : 5000);
    return () => clearTimeout(t);
  }, [toast]);

  const refreshOverview = useCallback(async () => {
    try {
      const [s, list, map] = await Promise.all([api.stats(), api.incidents(), api.threatMap()]);
      setStats(s);
      setIncidents(list);
      setThreatMap(map);
    } catch (e) {
      notify(e.message);
    }
  }, [notify]);

  useEffect(() => {
    (async () => {
      try {
        const [h, p, sc] = await Promise.all([api.health(), api.personas(), api.scripts()]);
        setHealth(h);
        setPersonas(p);
        setScripts(sc);
      } catch (e) {
        notify(e.message);
      }
      refreshOverview();
    })();
  }, [notify, refreshOverview]);

  const selectIncident = useCallback(
    async (id) => {
      setAutoPlay(false);
      setSelectedId(id);
      selectedRef.current = id;
      setTab("live");
      try {
        const d = await api.incident(id);
        if (selectedRef.current === id) setDetail(d);
      } catch (e) {
        notify(e.message);
      }
    },
    [notify],
  );

  const startSimulation = async (personaId, scriptId) => {
    setStarting(true);
    setAutoPlay(false);
    try {
      const res = await api.simulate(personaId, scriptId);
      selectedRef.current = res.incident_id;
      setSelectedId(res.incident_id);
      setDetail(res.incident);
      refreshOverview();
    } catch (e) {
      notify(e.message);
    } finally {
      setStarting(false);
    }
  };

  const nextExchange = useCallback(
    async (id) => {
      const run = (async () => {
        setResponding(true);
        try {
          const res = await api.respond(id);
          if (selectedRef.current === id) setDetail(res.incident);
          api.incidents().then(setIncidents).catch(() => {});
          return res.incident;
        } catch (e) {
          notify(e.message);
          setAutoPlay(false);
          // Keep whatever turns were saved before the failure.
          api.incident(id).then((d) => selectedRef.current === id && setDetail(d)).catch(() => {});
          return null;
        } finally {
          setResponding(false);
        }
      })();
      inFlightRef.current = run;
      const result = await run;
      inFlightRef.current = null;
      return result;
    },
    [notify],
  );

  // Auto-play: one exchange, wait ~2.5s, repeat - until toggled off, closed, or the cost guard trips.
  useEffect(() => {
    if (!autoPlay || !detail || detail.status !== "active") return;
    const id = detail.id;
    let cancelled = false;
    (async () => {
      while (!cancelled) {
        const updated = await nextExchange(id);
        if (!updated || cancelled) break;
        if (updated.exchange_count >= AUTOPLAY_MAX_EXCHANGES) {
          setAutoPlay(false);
          notify(`Auto-play paused after ${AUTOPLAY_MAX_EXCHANGES} exchanges — time to Close & analyze.`, "info");
          break;
        }
        await sleep(AUTOPLAY_INTERVAL_MS);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoPlay, detail?.id]);

  const closeIncident = async () => {
    if (!detail) return;
    const id = detail.id;
    setAutoPlay(false);
    setClosing(true);
    try {
      if (inFlightRef.current) await inFlightRef.current;
      const res = await api.close(id);
      if (selectedRef.current === id) setDetail(res);
      if (res.linked_incidents?.length) {
        const top = res.linked_incidents[0];
        notify(
          `Campaign match: ${res.ref} ↔ ${top.ref} (${(top.similarity * 100).toFixed(1)}% similar) — same attacker detected.`,
          "amber",
        );
      }
      refreshOverview();
    } catch (e) {
      notify(e.message);
      api.incident(id).then((d) => selectedRef.current === id && setDetail(d)).catch(() => {});
      refreshOverview();
    } finally {
      setClosing(false);
    }
  };

  const openReport = async () => {
    setReportLoading(true);
    try {
      setReport(await api.report(detail.id));
    } catch (e) {
      notify(e.message);
    } finally {
      setReportLoading(false);
    }
  };

  const resetDemo = async () => {
    if (!window.confirm("Delete ALL incidents, profiles and links? Personas and scripts are kept.")) return;
    setAutoPlay(false);
    await api.reset();
    setSelectedId(null);
    selectedRef.current = null;
    setDetail(null);
    refreshOverview();
  };

  const toastTones = {
    error: "border-red-500/50 bg-red-950/90 text-red-200",
    amber: "border-amber-400/60 bg-amber-950/90 text-amber-200",
    info: "border-cyan-500/50 bg-slate-900/95 text-cyan-200",
  };

  return (
    <div className="flex h-full flex-col gap-4 px-4 py-4 lg:px-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h1 className="font-mono text-2xl font-semibold tracking-[0.3em] text-cyan-300">MIRAGE</h1>
          <span className="text-sm text-slate-500">AI deception &amp; threat intelligence</span>
        </div>
        <div className="flex items-center gap-3">
          <ModeBadge health={health} />
          <Button variant="ghost" onClick={resetDemo} className="text-xs">
            Reset demo
          </Button>
        </div>
      </header>

      <StatsBar stats={stats} />

      <nav className="flex gap-1 border-b border-slate-800">
        {[
          ["live", "Live Incidents"],
          ["map", "Threat Map"],
        ].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              tab === key ? "border-cyan-400 text-cyan-300" : "border-transparent text-slate-500 hover:text-slate-300"
            }`}
          >
            {label}
            {key === "map" && stats?.multi_incident_clusters > 0 && (
              <span className="ml-2 rounded-full bg-amber-400 px-1.5 font-mono text-[10px] text-slate-950">
                {stats.multi_incident_clusters}
              </span>
            )}
          </button>
        ))}
      </nav>

      {tab === "live" ? (
        <main className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[320px_1fr_400px]">
          <Sidebar
            personas={personas}
            scripts={scripts}
            incidents={incidents}
            selectedId={selectedId}
            onSelect={selectIncident}
            onStart={startSimulation}
            starting={starting}
          />
          {detail ? (
            <>
              <IncidentView
                incident={detail}
                responding={responding}
                closing={closing}
                autoPlay={autoPlay}
                onNext={() => nextExchange(detail.id)}
                onToggleAutoPlay={() => setAutoPlay((v) => !v)}
                onClose={closeIncident}
              />
              <AnalysisPanel
                incident={detail}
                closing={closing}
                onReport={openReport}
                reportLoading={reportLoading}
                onSelectIncident={selectIncident}
              />
            </>
          ) : (
            <div className="flex items-center justify-center rounded-lg border border-dashed border-slate-800 p-10 text-center text-sm text-slate-500 lg:col-span-2">
              Pick a decoy persona and an attacker script, then start a simulation — or select an incident from the feed.
            </div>
          )}
        </main>
      ) : (
        <ThreatMap data={threatMap} onSelectIncident={selectIncident} />
      )}

      {report && <ReportModal report={report} onClose={() => setReport(null)} />}
      {toast && (
        <div
          key={toast.key}
          className={`fixed bottom-5 right-5 z-40 max-w-md rounded-lg border px-4 py-3 text-sm shadow-xl ${toastTones[toast.tone]}`}
        >
          {toast.message}
        </div>
      )}
    </div>
  );
}
