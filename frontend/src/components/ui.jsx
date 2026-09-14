export function StatusBadge({ status }) {
  if (status === "needs_review") {
    return (
      <span
        title="Extraction did not meet the validation schema; no profile was generated"
        className="inline-flex items-center gap-1.5 rounded-full border border-violet-400/50 bg-violet-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-violet-300"
      >
        ⚑ Needs review
      </span>
    );
  }
  if (status === "active") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-red-500/40 bg-red-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-red-400">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />
        Active
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-400">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
      Closed
    </span>
  );
}

const CONFIDENCE_STYLES = {
  high: { dot: "bg-emerald-400", text: "text-emerald-300", border: "border-emerald-500/40" },
  medium: { dot: "bg-yellow-300", text: "text-yellow-200", border: "border-yellow-400/40" },
  low: { dot: "bg-orange-400", text: "text-orange-300", border: "border-orange-500/50" },
};

export function ConfidenceBadge({ level }) {
  const style = CONFIDENCE_STYLES[level];
  if (!style) {
    return <span className="font-mono text-[10px] uppercase tracking-wider text-slate-600">confidence n/a</span>;
  }
  return (
    <span
      title="The extractor's self-reported confidence in this summary: how explicit the transcript was vs. how much it had to infer"
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${style.border} ${style.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {level} confidence
    </span>
  );
}

export function ClusterBadge({ size }) {
  if (!size || size < 2) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-amber-400/50 bg-amber-400/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-300">
      ◆ Cluster ×{size}
    </span>
  );
}

const BUTTON_VARIANTS = {
  primary: "bg-cyan-500 text-slate-950 hover:bg-cyan-400 disabled:bg-slate-700 disabled:text-slate-400",
  secondary:
    "border border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700 disabled:text-slate-500 disabled:hover:bg-slate-800",
  danger: "bg-red-500 text-white hover:bg-red-400 disabled:bg-slate-700 disabled:text-slate-400",
  amber: "bg-amber-400 text-slate-950 hover:bg-amber-300 disabled:bg-slate-700 disabled:text-slate-400",
  review: "bg-violet-500 text-white hover:bg-violet-400 disabled:bg-slate-700 disabled:text-slate-400",
  ghost: "text-slate-400 hover:text-slate-200 hover:bg-slate-800",
};

export function Button({ variant = "primary", className = "", children, ...props }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed ${BUTTON_VARIANTS[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function Spinner({ className = "h-4 w-4" }) {
  return (
    <span
      className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${className}`}
    />
  );
}

export function Panel({ title, action, children, className = "" }) {
  return (
    <section className={`rounded-lg border border-slate-800 bg-slate-900/60 ${className}`}>
      {title && (
        <header className="flex items-center justify-between border-b border-slate-800 px-4 py-2.5">
          <h3 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">{title}</h3>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function TacticTag({ tactic, count }) {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-fuchsia-500/30 bg-fuchsia-500/10 px-2 py-0.5 font-mono text-xs text-fuchsia-300">
      {tactic}
      {count != null && <span className="text-fuchsia-400/60">×{count}</span>}
    </span>
  );
}

export function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}
