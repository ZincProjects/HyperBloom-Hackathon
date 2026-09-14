const BASE = import.meta.env.VITE_API_URL || "/api";

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new Error("Cannot reach the MIRAGE backend - is uvicorn running on port 8000?");
  }
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg).join("; ")
      : detail || `Request failed (${res.status})`;
    const error = new Error(message);
    error.status = res.status;
    throw error;
  }
  return data;
}

const post = (path, body) =>
  request(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

export const api = {
  health: () => request("/health"),
  stats: () => request("/dashboard/stats"),
  personas: () => request("/personas"),
  scripts: () => request("/attacker-scripts"),
  incidents: () => request("/incidents"),
  incident: (id) => request(`/incidents/${id}`),
  simulate: (personaId, scriptId) =>
    post("/incidents/simulate", { persona_id: personaId, attacker_script_id: scriptId }),
  respond: (id) => post(`/incidents/${id}/respond`),
  close: (id) => post(`/incidents/${id}/close`),
  report: (id) => request(`/incidents/${id}/report`),
  threatMap: () => request("/threat-map"),
  reset: () => post("/demo/reset"),
};
