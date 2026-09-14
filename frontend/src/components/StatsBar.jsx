import { TacticTag } from "./ui.jsx";

function StatCard({ label, value, sub, tone = "slate" }) {
  const tones = {
    slate: "text-slate-100",
    red: "text-red-400",
    amber: "text-amber-300",
    cyan: "text-cyan-300",
  };
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">{label}</div>
      <div className={`mt-1 font-mono text-2xl font-semibold ${tones[tone]}`}>{value ?? "—"}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export default function StatsBar({ stats }) {
  const s = stats || {};
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <StatCard
        label="Total incidents"
        value={s.total_incidents}
        sub={`${s.analyzed_incidents ?? 0} analyzed · ${s.needs_review_incidents ?? 0} need review`}
      />
      <StatCard
        label="Open threats"
        value={s.open_incidents}
        tone={s.open_incidents ? "red" : "slate"}
        sub="decoys engaging attackers"
      />
      <StatCard
        label="Attacker clusters"
        value={s.unique_attacker_clusters}
        tone={s.multi_incident_clusters ? "amber" : "slate"}
        sub={`${s.multi_incident_clusters ?? 0} multi-incident campaign${s.multi_incident_clusters === 1 ? "" : "s"}`}
      />
      <StatCard label="IOCs extracted" value={s.total_iocs} tone="cyan" sub={`${s.total_links ?? 0} similarity links`} />
      <div className="col-span-2 rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3 lg:col-span-1">
        <div className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">Top tactics</div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {s.top_tactics?.length ? (
            s.top_tactics.slice(0, 4).map((t) => <TacticTag key={t.tactic} tactic={t.tactic} count={t.count} />)
          ) : (
            <span className="text-xs text-slate-600">None yet</span>
          )}
        </div>
      </div>
    </div>
  );
}
