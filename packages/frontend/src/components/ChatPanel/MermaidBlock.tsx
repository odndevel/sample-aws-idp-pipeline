import { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { X, Workflow } from 'lucide-react';
import mermaid from 'mermaid';

let renderCounter = 0;

// Prevent mermaid from auto-scanning the DOM on load
mermaid.initialize({ startOnLoad: false });

function isDarkMode() {
  return document.documentElement.classList.contains('dark');
}

function cleanupMermaidElements(id: string) {
  document.getElementById('d' + id)?.remove();
  document.getElementById(id)?.remove();
}

async function renderMermaid(code: string): Promise<string | null> {
  const id = `mermaid-${++renderCounter}`;
  mermaid.initialize({
    startOnLoad: false,
    theme: isDarkMode() ? 'dark' : 'default',
    securityLevel: 'loose',
    suppressErrorRendering: true,
  });

  const valid = await mermaid.parse(code, { suppressErrors: true });
  if (!valid) return null;

  try {
    const { svg } = await mermaid.render(id, code);
    cleanupMermaidElements(id);
    return svg;
  } catch {
    cleanupMermaidElements(id);
    return null;
  }
}

interface MermaidBlockProps {
  code: string;
}

export default function MermaidBlock({ code }: MermaidBlockProps) {
  const [showModal, setShowModal] = useState(false);
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const codeRef = useRef(code);
  codeRef.current = code;

  const handleOpen = useCallback(() => {
    setShowModal(true);
    setLoading(true);
    setError(false);
    setSvg(null);
    renderMermaid(codeRef.current).then((result) => {
      setLoading(false);
      if (result) {
        setSvg(result);
      } else {
        setError(true);
      }
    });
  }, []);

  // Re-render on theme change while modal is open
  useEffect(() => {
    if (!showModal || !svg) return;
    const observer = new MutationObserver(() => {
      renderMermaid(codeRef.current).then((result) => {
        if (result) setSvg(result);
      });
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });
    return () => observer.disconnect();
  }, [showModal, svg]);

  // Close on Escape
  useEffect(() => {
    if (!showModal) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowModal(false);
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [showModal]);

  return (
    <>
      <div className="my-3 flex items-center gap-3 px-4 py-3 rounded-xl border border-indigo-200 dark:border-indigo-500/30 bg-gradient-to-r from-indigo-50/80 to-violet-50/80 dark:from-indigo-900/20 dark:to-violet-900/20">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 shadow-sm flex-shrink-0">
          <Workflow className="w-4 h-4 text-white" />
        </div>
        <span className="flex-1 text-sm font-medium text-slate-700 dark:text-slate-300">
          Mermaid Diagram
        </span>
        <button
          type="button"
          onClick={handleOpen}
          className="px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-500 hover:bg-indigo-600 text-white transition-colors shadow-sm"
        >
          View
        </button>
      </div>

      {showModal &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
            onClick={(e) => {
              if (e.target === e.currentTarget) setShowModal(false);
            }}
          >
            <div className="relative w-[90vw] max-w-4xl max-h-[85vh] bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 overflow-hidden flex flex-col">
              {/* Header */}
              <div className="flex items-center gap-2.5 px-4 py-3 border-b border-slate-200 dark:border-slate-700">
                <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 shadow-sm">
                  <Workflow className="w-3.5 h-3.5 text-white" />
                </div>
                <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                  Mermaid Diagram
                </span>
                <div className="flex-1" />
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                >
                  <X className="w-4 h-4 text-slate-500 dark:text-slate-400" />
                </button>
              </div>

              {/* Content */}
              <div className="flex-1 overflow-auto p-6">
                {loading && (
                  <div className="flex items-center justify-center py-12">
                    <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                  </div>
                )}
                {error && (
                  <pre className="overflow-x-auto rounded-lg bg-slate-100 dark:bg-slate-900 p-4 text-sm">
                    <code className="language-mermaid">{code}</code>
                  </pre>
                )}
                {svg && (
                  <div
                    className="flex justify-center [&_svg]:max-w-full"
                    dangerouslySetInnerHTML={{ __html: svg }}
                  />
                )}
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
