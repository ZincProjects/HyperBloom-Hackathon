import { useEffect, useRef } from "react";
import { Button, ClusterBadge, Spinner, StatusBadge, TypingDots } from "./ui.jsx";

const RECOMMENDED_EXCHANGES = 4;

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// Highlight extracted IOC values inside attacker messages once the incident is analyzed.
function highlight(text, values) {
  const present = values.filter((v) => v && v.length >= 4 && text.includes(v));
  if (!present.length) return text;
  present.sort((a, b) => b.length - a.length);
  const re = new RegExp(`(${present.map(escapeRe).join("|")})`, "g");
  return text.split(re).map((part, i) =>
    present.includes(part) ? (
      <mark key={i} className="rounded bg-amber-400/15 px-0.5 font-mono text-[0.9em] text-amber-300">
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

function Bubble({ message, incident, iocValues }) {
  const isAttacker = message.sender === "attacker";
  const time = new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return (
    <div className={`flex ${isAttacker ? "justify-start" : "justify-end"}`}>
      <div className="max-w-[78%]">
        <div
          className={`mb-1 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest ${
            isAttacker ? "text-red-400/80" : "justify-end text-cyan-400/80"
          }`}
        >
          {isAttacker ? `Attacker · ${incident.attacker_script?.name ?? "manual"}` : `Decoy · ${incident.persona.name}`}
          <span className="font-mono font-normal normal-case tracking-normal text-slate-600">{time}</span>
        </div>
        <div
          className={`rounded-lg border px-3.5 py-2.5 text-sm leading-relaxed ${
            isAttacker
              ? "rounded-tl-none border-red-500/25 bg-red-950/30 text-slate-200"
              : "rounded-tr-none border-cyan-500/25 bg-cyan-950/30 text-slate-200"
          }`}
        >
          {isAttacker ? highlight(message.content, iocValues) : message.content}
        </div>
      </div>
    </div>
  );
}

export default function IncidentView({
  incident, responding, closing, autoPlay, onNext, onToggleAutoPlay, onClose,
}) {
  const scrollRef = useRef(null);
  const count = incident.messages.length;

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [count, responding]);

  const active = incident.status === "active";
  const exchanges = incident.exchange_count;
  const ready = exchanges >= RECOMMENDED_EXCHANGES;
  const needsAnalysisRetry = !active && !incident.profile && count > 0;
  const iocValues = (incident.profile?.iocs ?? []).map((i) => i.value);

  return (
    <section className="flex min-h-0 flex-col rounded-lg border border-slate-800 bg-slate-900/60">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-semibold text-slate-100">{incident.ref}</span>
            <StatusBadge status={incident.status} />
            <ClusterBadge size={incident.cluster_size} />
          </div>
          <div className="mt-0.5 text-xs text-slate-500">
            <span className="text-red-400/80">{incident.attacker_script?.name ?? "Manual input"}</span> targeting{" "}
            <span className="text-cyan-400/80">{incident.persona.name}</span> · {incident.persona.role} · channel:{" "}
            {incident.channel}
          </div>
        </div>
        <div className="font-mono text-xs text-slate-500">
          {exchanges} exchange{exchanges === 1 ? "" : "s"} · {count} messages
        </div>
      </header>

      <div ref={scrollRef} className="scrollbar-thin min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5">
        {incident.messages.map((m) => (
          <Bubble key={m.id} message={m} incident={incident} iocValues={iocValues} />
        ))}
        {responding && (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <TypingDots /> Decoy is replying, attacker is reacting…
          </div>
        )}
        {!active && (
          <div className="flex items-center gap-3 py-2 text-[10px] font-semibold uppercase tracking-widest text-emerald-500/70">
            <span className="h-px flex-1 bg-emerald-500/20" /> Incident closed <span className="h-px flex-1 bg-emerald-500/20" />
          </div>
        )}
      </div>

      <footer className="flex flex-wrap items-center gap-3 border-t border-slate-800 px-5 py-3">
        {active ? (
          <>
            <Button variant="secondary" onClick={onNext} disabled={responding || closing || autoPlay}>
              {responding && !autoPlay ? <Spinner /> : "⏭"} Next exchange
            </Button>
            <label className="flex cursor-pointer select-none items-center gap-2 text-sm text-slate-400">
              <span
                role="switch"
                aria-checked={autoPlay}
                onClick={onToggleAutoPlay}
                className={`relative h-5 w-9 rounded-full transition-colors ${autoPlay ? "bg-cyan-500" : "bg-slate-700"}`}
              >
                <span
                  className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${autoPlay ? "left-4.5" : "left-0.5"}`}
                />
              </span>
              <span onClick={onToggleAutoPlay}>Auto-play</span>
            </label>
            <div className="ml-auto flex items-center gap-3">
              <span className={`text-xs ${ready ? "text-emerald-400" : "text-slate-500"}`}>
                {ready ? "Enough signal gathered" : `Recommended ${RECOMMENDED_EXCHANGES}–6 exchanges (${exchanges}/${RECOMMENDED_EXCHANGES})`}
              </span>
              <Button
                variant={ready ? "amber" : "secondary"}
                onClick={onClose}
                disabled={closing || exchanges < 1}
                className={ready && !closing ? "shadow-[0_0_18px_rgba(251,191,36,0.35)]" : ""}
              >
                {closing ? <Spinner /> : "⛨"} Close &amp; analyze
              </Button>
            </div>
          </>
        ) : needsAnalysisRetry ? (
          <Button variant="amber" onClick={onClose} disabled={closing}>
            {closing ? <Spinner /> : "↻"} Retry analysis
          </Button>
        ) : (
          <span className="text-xs text-slate-500">
            Closed {incident.closed_at ? new Date(incident.closed_at).toLocaleString() : ""} — decoy disengaged.
          </span>
        )}
      </footer>
    </section>
  );
}
