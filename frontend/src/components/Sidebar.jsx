import { useEffect, useState } from "react";
import { Button, ClusterBadge, Spinner, StatusBadge } from "./ui.jsx";

function NewSimulation({ personas, scripts, onStart, starting }) {
  const [personaId, setPersonaId] = useState("");
  const [scriptId, setScriptId] = useState("");

  useEffect(() => {
    if (!personaId && personas.length) setPersonaId(String(personas[0].id));
  }, [personas, personaId]);
  useEffect(() => {
    if (!scriptId && scripts.length) setScriptId(String(scripts[0].id));
  }, [scripts, scriptId]);

  const script = scripts.find((s) => String(s.id) === scriptId);
  const selectClass =
    "w-full rounded-md border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none";

  return (
    <div className="space-y-3 border-b border-slate-800 p-4">
      <div className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">Red-Team Simulator</div>
      <label className="block">
        <span className="mb-1 block text-xs text-slate-500">Decoy persona</span>
        <select className={selectClass} value={personaId} onChange={(e) => setPersonaId(e.target.value)}>
          {personas.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} — {p.role}
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="mb-1 block text-xs text-slate-500">Attacker script</span>
        <select className={selectClass} value={scriptId} onChange={(e) => setScriptId(e.target.value)}>
          {scripts.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </label>
      {script && <p className="text-xs leading-relaxed text-slate-500">{script.description}</p>}
      <Button
        className="w-full"
        disabled={!personaId || !scriptId || starting}
        onClick={() => onStart(Number(personaId), Number(scriptId))}
      >
        {starting ? <Spinner /> : "▶"} Start new simulation
      </Button>
    </div>
  );
}

function IncidentItem({ incident, selected, onSelect }) {
  const linked = incident.cluster_size > 1;
  return (
    <button
      onClick={() => onSelect(incident.id)}
      className={`w-full border-l-2 px-4 py-3 text-left transition-colors ${
        selected ? "border-cyan-400 bg-slate-800/70" : "border-transparent hover:bg-slate-800/40"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={`font-mono text-xs font-semibold ${linked ? "text-amber-300" : "text-slate-300"}`}>
          {incident.ref}
        </span>
        <div className="flex items-center gap-1.5">
          <ClusterBadge size={incident.cluster_size} />
          <StatusBadge status={incident.status} />
        </div>
      </div>
      <div className="mt-1.5 text-sm text-slate-200">
        {incident.attacker_script?.name ?? "Manual input"}
        <span className="text-slate-500"> → {incident.persona.name}</span>
      </div>
      <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-slate-500">{incident.summary}</p>
      <div className="mt-1.5 flex items-center gap-3 font-mono text-[10px] text-slate-600">
        <span>{incident.exchange_count} exchanges</span>
        {incident.mitre_technique && <span className="text-cyan-400/70">{incident.mitre_technique.split(" ")[0]}</span>}
      </div>
    </button>
  );
}

export default function Sidebar({ personas, scripts, incidents, selectedId, onSelect, onStart, starting }) {
  return (
    <aside className="flex min-h-0 flex-col rounded-lg border border-slate-800 bg-slate-900/60">
      <NewSimulation personas={personas} scripts={scripts} onStart={onStart} starting={starting} />
      <div className="flex items-center justify-between px-4 pb-1 pt-3">
        <span className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">Incident feed</span>
        <span className="font-mono text-xs text-slate-600">{incidents.length}</span>
      </div>
      <div className="scrollbar-thin min-h-0 flex-1 divide-y divide-slate-800/60 overflow-y-auto">
        {incidents.length === 0 ? (
          <p className="px-4 py-6 text-center text-xs text-slate-600">
            No incidents yet. Start a simulation to deploy a decoy.
          </p>
        ) : (
          incidents.map((incident) => (
            <IncidentItem
              key={incident.id}
              incident={incident}
              selected={incident.id === selectedId}
              onSelect={onSelect}
            />
          ))
        )}
      </div>
    </aside>
  );
}
