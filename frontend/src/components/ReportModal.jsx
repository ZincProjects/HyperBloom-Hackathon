import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "./ui.jsx";

export default function ReportModal({ report, onClose }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const copy = async () => {
    await navigator.clipboard.writeText(report.markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const download = () => {
    const url = URL.createObjectURL(new Blob([report.markdown], { type: "text/markdown" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = report.filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-xl border border-slate-700 bg-slate-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between gap-3 border-b border-slate-800 px-5 py-3">
          <span className="font-mono text-sm text-slate-300">{report.filename}</span>
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={copy}>
              {copied ? "✓ Copied" : "Copy markdown"}
            </Button>
            <Button onClick={download}>Download .md</Button>
            <Button variant="ghost" onClick={onClose} aria-label="Close report">
              ✕
            </Button>
          </div>
        </header>
        <article className="report scrollbar-thin overflow-y-auto px-8 py-6">
          <Markdown remarkPlugins={[remarkGfm]}>{report.markdown}</Markdown>
        </article>
      </div>
    </div>
  );
}
