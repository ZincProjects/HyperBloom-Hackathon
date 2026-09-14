import { useMemo } from "react";
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from "d3-force";
import { Panel, StatusBadge } from "./ui.jsx";

const W = 760;
const H = 520;

// Each cluster gets its own grid cell (campaigns first) so halos never swallow unrelated nodes.
function clusterAnchors(clusters) {
  const cols = Math.max(1, Math.ceil(Math.sqrt(clusters.length)));
  const rows = Math.max(1, Math.ceil(clusters.length / cols));
  const anchors = {};
  clusters.forEach((c, i) => {
    anchors[c.cluster_id] = {
      x: ((i % cols) + 0.5) * (W / cols),
      y: (Math.floor(i / cols) + 0.5) * (H / rows),
    };
  });
  return anchors;
}

function layoutGraph(data) {
  const anchors = clusterAnchors(data.clusters);
  const nodes = data.nodes.map((n) => ({ ...n, x: anchors[n.cluster_id].x, y: anchors[n.cluster_id].y }));
  const links = data.links.map((l) => ({ ...l }));
  const simulation = forceSimulation(nodes)
    .force("link", forceLink(links).id((d) => d.id).distance((l) => 145 + (1 - l.similarity) * 120).strength(0.7))
    .force("charge", forceManyBody().strength(-180).distanceMax(220))
    .force("collide", forceCollide(58))
    .force("x", forceX((d) => anchors[d.cluster_id].x).strength(0.18))
    .force("y", forceY((d) => anchors[d.cluster_id].y).strength(0.18))
    .stop();
  for (let i = 0; i < 320; i++) simulation.tick();
  for (const n of nodes) {
    n.x = Math.max(50, Math.min(W - 50, n.x));
    n.y = Math.max(45, Math.min(H - 55, n.y));
  }
  return { nodes, links };
}

function campaignLabels(clusters) {
  const labels = {};
  clusters
    .filter((c) => c.size > 1)
    .forEach((c, i) => {
      labels[c.cluster_id] = `CAMPAIGN-${String(i + 1).padStart(2, "0")}`;
    });
  return labels;
}

export default function ThreatMap({ data, onSelectIncident }) {
  const graph = useMemo(() => (data ? layoutGraph(data) : null), [data]);
  const labels = useMemo(() => (data ? campaignLabels(data.clusters) : {}), [data]);

  if (!data) return <div className="p-8 text-sm text-slate-500">Loading threat map…</div>;

  const halos = data.clusters
    .filter((c) => c.size > 1)
    .map((c) => {
      const members = graph.nodes.filter((n) => c.incident_ids.includes(n.id));
      const cx = members.reduce((s, n) => s + n.x, 0) / members.length;
      const cy = members.reduce((s, n) => s + n.y, 0) / members.length;
      const r = Math.max(...members.map((n) => Math.hypot(n.x - cx, n.y - cy))) + 70;
      return { id: c.cluster_id, cx, cy, r };
    });

  return (
    <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[1fr_360px]">
      <Panel
        title="Attacker network — incident similarity graph"
        className="flex min-h-0 flex-col"
        action={<span className="font-mono text-[10px] text-slate-500">edge = cosine similarity &gt; {data.threshold}</span>}
      >
        {graph.nodes.length === 0 ? (
          <div className="flex flex-1 items-center justify-center p-10 text-center text-sm text-slate-500">
            No analyzed incidents yet. Close &amp; analyze two simulations that use the same attacker script to watch a
            campaign cluster form.
          </div>
        ) : (
          <svg viewBox={`0 0 ${W} ${H}`} className="h-full max-h-[calc(100vh-280px)] w-full">
            <defs>
              <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
                <path d="M 32 0 L 0 0 0 32" fill="none" stroke="#1e293b" strokeWidth="0.6" />
              </pattern>
            </defs>
            <rect width={W} height={H} fill="url(#grid)" />
            {halos.map((h) => (
              <g key={h.id}>
                <circle cx={h.cx} cy={h.cy} r={h.r} fill="#fbbf24" fillOpacity="0.05" stroke="#fbbf24" strokeDasharray="4 6" className="halo-pulse" />
                <text x={h.cx} y={Math.max(14, h.cy - h.r + 18)} textAnchor="middle" className="fill-amber-300 font-mono text-[11px] font-semibold">
                  {labels[h.id]}
                </text>
              </g>
            ))}
            {graph.links.map((l) => {
              // Edge label sits slightly off the midpoint, away from the node subtitles below each node.
              const mx = (l.source.x + l.target.x) / 2;
              const my = (l.source.y + l.target.y) / 2 - 14;
              return (
                <g key={`${l.source.id}-${l.target.id}`}>
                  <line x1={l.source.x} y1={l.source.y} x2={l.target.x} y2={l.target.y} stroke="#fbbf24" strokeOpacity="0.7" strokeWidth={1 + l.similarity * 3} />
                  <rect x={mx - 22} y={my - 9} width="44" height="18" rx="4" fill="#0f172a" stroke="#78350f" />
                  <text x={mx} y={my + 4} textAnchor="middle" className="fill-amber-200 font-mono text-[10px]">
                    {Math.round(l.similarity * 100)}%
                  </text>
                </g>
              );
            })}
            {graph.nodes.map((n) => {
              const linked = n.cluster_size > 1;
              return (
                <g key={n.id} transform={`translate(${n.x},${n.y})`} className="cursor-pointer" onClick={() => onSelectIncident(n.id)}>
                  <title>{`${n.ref} · ${n.attacker_script} → ${n.persona_name}\n${n.mitre_technique}\n${n.attacker_goal}`}</title>
                  <circle r="22" fill={linked ? "#451a03" : "#1e293b"} stroke={linked ? "#fbbf24" : "#475569"} strokeWidth="2" />
                  <circle r="5" fill={n.status === "active" ? "#ef4444" : "#10b981"} cx="16" cy="-16" stroke="#0f172a" strokeWidth="2" />
                  <text textAnchor="middle" y="4" className={`font-mono text-[10px] font-semibold ${linked ? "fill-amber-200" : "fill-slate-300"}`}>
                    {n.technique_id ?? "?"}
                  </text>
                  <text textAnchor="middle" y="38" className="fill-slate-300 font-mono text-[10px]">
                    {n.ref}
                  </text>
                  <text textAnchor="middle" y="51" className="fill-slate-500 text-[10px]">
                    {n.attacker_script} → {n.persona_name.split(" ")[0]}
                  </text>
                </g>
              );
            })}
          </svg>
        )}
      </Panel>

      <div className="scrollbar-thin min-h-0 space-y-3 overflow-y-auto pr-1">
        {data.clusters.map((c) => {
          const campaign = labels[c.cluster_id];
          const members = data.nodes.filter((n) => c.incident_ids.includes(n.id));
          return (
            <div
              key={c.cluster_id}
              className={`rounded-lg border p-4 ${campaign ? "border-amber-400/50 bg-amber-400/5" : "border-slate-800 bg-slate-900/60"}`}
            >
              <div className="flex items-center justify-between">
                <span className={`font-mono text-xs font-semibold ${campaign ? "text-amber-300" : "text-slate-400"}`}>
                  {campaign ?? "Singleton attacker"}
                </span>
                <span className="font-mono text-xs text-slate-500">
                  {c.size} incident{c.size > 1 ? "s" : ""}
                </span>
              </div>
              <div className="mt-2 text-xs text-slate-400">
                {c.attacker_scripts.join(", ")} · targeted {c.personas_targeted.join(", ")}
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {members.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => onSelectIncident(m.id)}
                    className="flex items-center gap-1.5 rounded border border-slate-700 bg-slate-800 px-2 py-0.5 font-mono text-[11px] text-slate-300 hover:border-cyan-500"
                  >
                    {m.ref} <StatusBadge status={m.status} />
                  </button>
                ))}
              </div>
              {c.shared_iocs.length > 0 && (
                <div className="mt-3">
                  <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">Shared infrastructure</div>
                  <ul className="mt-1 space-y-0.5">
                    {c.shared_iocs.slice(0, 6).map((v) => (
                      <li key={v} className="break-all font-mono text-[11px] text-amber-300">
                        {v}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
