import { Button, Panel, Spinner, TacticTag } from "./ui.jsx";

const IOC_LABELS = {
  url: "URL",
  phone: "Phone",
  email: "Email",
  payment_account: "Payment",
  other: "Other",
};

const PIPELINE_STEPS = [
  "Structured extraction (LLM → validated JSON)",
  "Embedding profile (all-MiniLM-L6-v2)",
  "Cosine similarity vs. past incidents",
  "Linking campaign clusters",
];

function attackUrl(tid) {
  return `https://attack.mitre.org/techniques/${tid.replace(".", "/")}/`;
}

function Pending({ closing }) {
  if (closing) {
    return (
      <Panel title="Analysis pipeline">
        <ol className="space-y-3 p-4">
          {PIPELINE_STEPS.map((step, i) => (
            <li key={step} className="flex items-center gap-3 text-sm text-slate-300">
              <Spinner className="h-3.5 w-3.5 text-amber-300" />
              <span className="font-mono text-xs text-slate-500">0{i + 1}</span>
              {step}
            </li>
          ))}
        </ol>
      </Panel>
    );
  }
  return (
    <Panel title="Threat intelligence">
      <div className="space-y-3 p-4 text-sm text-slate-400">
        <p>The decoy is keeping the attacker engaged and drawing out details.</p>
        <p>
          <span className="text-amber-300">Close &amp; analyze</span> runs a second LLM pass that extracts the MITRE
          ATT&amp;CK technique, IOCs and manipulation tactics, embeds the profile, and checks it against every past
          incident for a campaign match.
        </p>
      </div>
    </Panel>
  );
}

export default function AnalysisPanel({ incident, closing, onReport, reportLoading, onSelectIncident }) {
  const profile = incident.profile;
  if (!profile) return <Pending closing={closing} />;

  const links = incident.linked_incidents;
  return (
    <div className="scrollbar-thin min-h-0 space-y-3 overflow-y-auto pr-1">
      {links.length > 0 && (
        <div className="rounded-lg border border-amber-400/50 bg-amber-400/10 p-4 shadow-[0_0_24px_rgba(251,191,36,0.15)]">
          <div className="text-[11px] font-semibold uppercase tracking-widest text-amber-300">◆ Campaign match detected</div>
          <p className="mt-1.5 text-sm text-amber-100/90">
            This attacker profile matches {links.length} past incident{links.length > 1 ? "s" : ""} — likely the same
            attacker or script, even though a different decoy was targeted.
          </p>
        </div>
      )}

      <Panel title="Attacker goal">
        <p className="p-4 text-sm leading-relaxed text-slate-200">{profile.attacker_goal}</p>
      </Panel>

      <Panel title="MITRE ATT&CK">
        <div className="space-y-2 p-4">
          <div className="flex items-center gap-2">
            {profile.technique_id && (
              <a
                href={attackUrl(profile.technique_id)}
                target="_blank"
                rel="noreferrer"
                className="rounded border border-cyan-500/40 bg-cyan-500/10 px-2 py-0.5 font-mono text-sm font-semibold text-cyan-300 hover:bg-cyan-500/20"
              >
                {profile.technique_id}
              </a>
            )}
            <span className="text-sm font-medium text-slate-100">{profile.technique_name}</span>
          </div>
          <p className="text-sm leading-relaxed text-slate-400">{profile.technique_explanation}</p>
        </div>
      </Panel>

      <Panel title="Manipulation tactics">
        <div className="flex flex-wrap gap-1.5 p-4">
          {profile.manipulation_tactics.length ? (
            profile.manipulation_tactics.map((t) => <TacticTag key={t} tactic={t} />)
          ) : (
            <span className="text-xs text-slate-500">None identified</span>
          )}
        </div>
      </Panel>

      <Panel title={`Indicators of compromise (${profile.iocs.length})`}>
        {profile.iocs.length ? (
          <table className="w-full text-sm">
            <tbody className="divide-y divide-slate-800">
              {profile.iocs.map((ioc) => (
                <tr key={`${ioc.type}:${ioc.value}`}>
                  <td className="w-20 px-4 py-2 align-top text-[11px] uppercase tracking-wider text-slate-500">
                    {IOC_LABELS[ioc.type] ?? ioc.type}
                  </td>
                  <td className="break-all px-4 py-2 font-mono text-xs text-amber-300">{ioc.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="p-4 text-xs text-slate-500">No indicators extracted.</p>
        )}
      </Panel>

      <Panel title="Linked incidents">
        {links.length ? (
          <ul className="divide-y divide-slate-800">
            {links.map((link) => (
              <li key={link.incident_id}>
                <button
                  onClick={() => onSelectIncident(link.incident_id)}
                  className="w-full px-4 py-2.5 text-left hover:bg-slate-800/50"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-semibold text-amber-300">{link.ref}</span>
                    <span className="font-mono text-xs text-amber-200">{(link.similarity * 100).toFixed(1)}% similar</span>
                  </div>
                  <div className="mt-1.5 h-1 overflow-hidden rounded bg-slate-800">
                    <div className="h-full bg-amber-400" style={{ width: `${link.similarity * 100}%` }} />
                  </div>
                  <div className="mt-1.5 text-xs text-slate-400">
                    {link.attacker_script ?? "Manual input"} → {link.persona_name}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="p-4 text-xs text-slate-500">No similar past incidents above the similarity threshold.</p>
        )}
      </Panel>

      <div className="flex items-center justify-between gap-3 px-1">
        <span className="font-mono text-[10px] leading-relaxed text-slate-600">
          analyzer: {profile.analyzer}
          <br />
          embedding: {profile.embedding_model} · {profile.embedding_dims}d
        </span>
        <Button onClick={onReport} disabled={reportLoading} className="shrink-0 whitespace-nowrap">
          {reportLoading ? <Spinner /> : "📄"} Generate report
        </Button>
      </div>
    </div>
  );
}
