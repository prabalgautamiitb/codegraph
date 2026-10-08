import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { DataSet } from "vis-data";
import { Network } from "vis-network";
import {
  Activity,
  CircleAlert,
  Database,
  FileSearch,
  GitBranch,
  Loader2,
  NetworkIcon,
  Play,
  RefreshCw,
  Search,
  Scan,
  ZoomIn
} from "lucide-react";
import "vis-network/styles/vis-network.css";
import "./styles.css";

const API_BASE = import.meta.env.VITE_CODEGRAPH_API_BASE ?? "http://127.0.0.1:8000";
const API_TOKEN = import.meta.env.VITE_CODEGRAPH_API_TOKEN ?? "dev-local-token";
const DEFAULT_PATH =
  import.meta.env.VITE_CODEGRAPH_DEMO_PATH ??
  "/Users/prabalgautam/Desktop/Projects/code-knowledge-graph/fixtures/python_demo";

type Job = {
  id: number;
  repo_id: number;
  status: string;
  stage: string;
  counts: Record<string, number>;
  diagnostics: string[];
  failure_reason: string | null;
  snapshot_id: number | null;
};

type SymbolResult = {
  id: string;
  kind: string;
  name: string;
  qualified_name: string;
  path: string;
  signature: string;
};

type Summary = {
  repo_id: number;
  snapshot_id: number;
  analyzer_version: string;
  counts: Record<string, number>;
  languages: Array<{ language: string; file_count: number }>;
  edge_counts: Array<{ kind: string; count: number }>;
};

type GraphNode = {
  id: string;
  kind: string;
  name: string;
  qualified_name: string;
  path: string;
  depth: number;
};

type GraphEdge = {
  kind: string;
  source_id: string;
  target_id: string;
  evidence: { path: string; rule: string; span: { start_line: number; end_line: number }; status: string };
};

type GraphPayload = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  visited_count: number;
  truncated: boolean;
  truncation_reason: string | null;
};

type NodeDetails = SymbolResult & {
  span: Record<string, number>;
  snippet: { start_line: number; end_line: number; lines: Array<{ line: number; text: string }> };
};

type Direction = "incoming" | "outgoing" | "both";

function App() {
  const [repoPath, setRepoPath] = useState(DEFAULT_PATH);
  const [sourceMode, setSourceMode] = useState<"local" | "github">("local");
  const [repoId, setRepoId] = useState<number | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [query, setQuery] = useState("store");
  const [symbols, setSymbols] = useState<SymbolResult[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [highlightedSymbol, setHighlightedSymbol] = useState(0);
  const [selectedSymbol, setSelectedSymbol] = useState<SymbolResult | null>(null);
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [details, setDetails] = useState<NodeDetails | null>(null);
  const [direction, setDirection] = useState<Direction>("incoming");
  const [depth, setDepth] = useState(2);
  const [edgeTypes, setEdgeTypes] = useState<Record<string, boolean>>({
    CALLS: true,
    INHERITS: true,
    IMPORTS: false,
    CONTAINS: false,
    REFERENCES: false,
    DECLARES_DEPENDENCY: false
  });
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const suppressNextSearchRef = useRef(false);

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers ?? {}),
        ...(init.method && init.method !== "GET" ? { Authorization: `Bearer ${API_TOKEN}` } : {})
      }
    });
    if (!response.ok) {
      const body = await response.text();
      throw new Error(body || `${response.status} ${response.statusText}`);
    }
    return response.json();
  }

  async function registerRepository() {
    setLoading("register");
    setError(null);
    try {
      const body = sourceMode === "github" ? { github_url: repoPath } : { local_path: repoPath };
      const repo = await request<{ id: number; root: string }>("/api/repositories", {
        method: "POST",
        body: JSON.stringify(body)
      });
      setRepoId(repo.id);
      setSummary(null);
      setJob(null);
      setGraph(null);
      setDetails(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(null);
    }
  }

  async function enqueueIndex() {
    if (!repoId) return;
    setLoading("index");
    setError(null);
    try {
      const result = await request<{ job_id: number; status: string }>(`/api/repositories/${repoId}/index`, { method: "POST" });
      const queued = await request<Job>(`/api/jobs/${result.job_id}`);
      setJob(queued);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(null);
    }
  }

  async function refreshJob() {
    if (!job) return;
    const current = await request<Job>(`/api/jobs/${job.id}`);
    setJob(current);
    if (current.status === "succeeded" && repoId) {
      setSummary(await request<Summary>(`/api/repositories/${repoId}/summary`));
    }
  }

  async function searchSymbols() {
    if (!repoId) return;
    setLoading("search");
    setError(null);
    try {
      const result = await request<{ snapshot_id: number; symbols: SymbolResult[] }>(
        `/api/repositories/${repoId}/symbols?q=${encodeURIComponent(query)}&limit=30`
      );
      setSymbols(result.symbols);
      setSearchOpen(true);
      setHighlightedSymbol(0);
      if (result.symbols[0]) {
        setSelectedSymbol(result.symbols[0]);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(null);
    }
  }

  function chooseSymbol(symbol: SymbolResult) {
    setSelectedSymbol(symbol);
    suppressNextSearchRef.current = true;
    setQuery(symbol.qualified_name);
    setSearchOpen(false);
    loadGraph(symbol);
  }

  async function loadGraph(symbol = selectedSymbol) {
    if (!repoId || !symbol) return;
    setLoading("graph");
    setError(null);
    try {
      const enabledEdges = Object.entries(edgeTypes)
        .filter(([, enabled]) => enabled)
        .map(([kind]) => kind)
        .join(",");
      const result = await request<GraphPayload>(
        `/api/repositories/${repoId}/graph?seed_node_id=${encodeURIComponent(symbol.id)}&edge_types=${enabledEdges}&direction=${direction}&depth=${depth}`
      );
      setGraph(result);
      await loadNode(symbol.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(null);
    }
  }

  async function loadNode(nodeId: string) {
    if (!repoId) return;
    const node = await request<NodeDetails>(`/api/repositories/${repoId}/nodes/${encodeURIComponent(nodeId)}`);
    setDetails(node);
  }

  useEffect(() => {
    if (!job || job.status === "succeeded" || job.status === "failed" || job.status === "interrupted") return;
    const timer = window.setInterval(() => {
      refreshJob().catch((err) => setError((err as Error).message));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status]);

  useEffect(() => {
    if (suppressNextSearchRef.current) {
      suppressNextSearchRef.current = false;
      return;
    }
    if (!repoId || !query.trim()) {
      setSymbols([]);
      setSearchOpen(false);
      return;
    }
    const timer = window.setTimeout(() => {
      searchSymbols().catch((err) => setError((err as Error).message));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, repoId]);

  return (
    <main className="app-shell">
      <section className="sidebar">
        <div className="brand">
          <NetworkIcon size={24} />
          <div>
            <h1>CodeGraph</h1>
            <span>Local repository explorer</span>
          </div>
        </div>

        <Panel title="Repository" icon={<Database size={16} />}>
          <label className="field">
            <span>{sourceMode === "github" ? "GitHub HTTPS URL" : "Local path"}</span>
            <input value={repoPath} onChange={(event) => setRepoPath(event.target.value)} />
          </label>
          <div className="segmented">
            <button className={sourceMode === "local" ? "active" : ""} onClick={() => setSourceMode("local")}>
              Local
            </button>
            <button className={sourceMode === "github" ? "active" : ""} onClick={() => setSourceMode("github")}>
              GitHub
            </button>
          </div>
          <div className="button-row">
            <button onClick={registerRepository} disabled={loading === "register"}>
              {loading === "register" ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
              Register
            </button>
            <button onClick={enqueueIndex} disabled={!repoId || loading === "index"}>
              {loading === "index" ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
              Index
            </button>
          </div>
          <StatusLine label="Repository" value={repoId ? `#${repoId}` : "Not registered"} />
          <StatusLine label="Job" value={job ? `#${job.id} ${job.status}` : "No job"} />
        </Panel>

        <Panel title="Search" icon={<Search size={16} />}>
          <div className="search-combobox">
            <div className="search-row">
            <input
              value={query}
              onFocus={() => symbols.length > 0 && setSearchOpen(true)}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown") {
                  event.preventDefault();
                  setSearchOpen(true);
                  setHighlightedSymbol((current) => Math.min(current + 1, Math.max(0, symbols.length - 1)));
                }
                if (event.key === "ArrowUp") {
                  event.preventDefault();
                  setHighlightedSymbol((current) => Math.max(0, current - 1));
                }
                if (event.key === "Enter") {
                  event.preventDefault();
                  const symbol = symbols[highlightedSymbol] ?? symbols[0];
                  if (symbol) chooseSymbol(symbol);
                  else searchSymbols();
                }
                if (event.key === "Escape") {
                  setSearchOpen(false);
                }
              }}
              placeholder={repoId ? "Search symbols..." : "Register and index a repo first"}
            />
            <button className="icon-button" onClick={searchSymbols} disabled={!repoId || loading === "search"} title="Search symbols">
              {loading === "search" ? <Loader2 className="spin" size={16} /> : <Search size={16} />}
            </button>
            </div>
            {searchOpen && (
              <div className="search-options">
                {symbols.map((symbol, index) => (
                  <button
                    key={symbol.id}
                    className={index === highlightedSymbol ? "search-option active" : "search-option"}
                    onMouseEnter={() => setHighlightedSymbol(index)}
                    onClick={() => chooseSymbol(symbol)}
                  >
                    <strong>{symbol.qualified_name}</strong>
                    <span>{symbol.kind} · {symbol.path}</span>
                  </button>
                ))}
                {symbols.length === 0 && <div className="search-empty">No matches</div>}
              </div>
            )}
          </div>
          <div className="symbol-list">
            {symbols.map((symbol) => (
              <button
                key={symbol.id}
                className={selectedSymbol?.id === symbol.id ? "symbol active" : "symbol"}
                onClick={() => chooseSymbol(symbol)}
              >
                <strong>{symbol.qualified_name}</strong>
                <span>{symbol.kind} · {symbol.path}</span>
              </button>
            ))}
            {symbols.length === 0 && <Empty text="No symbols loaded" />}
          </div>
        </Panel>

        <Panel title="Graph Controls" icon={<GitBranch size={16} />}>
          <div className="segmented">
            {(["incoming", "outgoing", "both"] as Direction[]).map((value) => (
              <button key={value} className={direction === value ? "active" : ""} onClick={() => setDirection(value)}>
                {value}
              </button>
            ))}
          </div>
          <label className="field">
            <span>Depth {depth}</span>
            <input type="range" min="1" max="3" value={depth} onChange={(event) => setDepth(Number(event.target.value))} />
          </label>
          <div className="checks">
            {Object.keys(edgeTypes).map((kind) => (
              <label key={kind}>
                <input
                  type="checkbox"
                  checked={edgeTypes[kind]}
                  onChange={(event) => setEdgeTypes({ ...edgeTypes, [kind]: event.target.checked })}
                />
                {kind}
              </label>
            ))}
          </div>
          <button onClick={() => loadGraph()} disabled={!selectedSymbol || loading === "graph"}>
            {loading === "graph" ? <Loader2 className="spin" size={16} /> : <ZoomIn size={16} />}
            Load Graph
          </button>
        </Panel>
      </section>

      <section className="workspace">
        {error && (
          <div className="notice error">
            <CircleAlert size={18} />
            <span>{error}</span>
          </div>
        )}

        <div className="metrics">
          <Metric label="Snapshot" value={summary?.snapshot_id ?? "-"} />
          <Metric label="Files" value={summary?.counts.supported ?? "-"} />
          <Metric label="Edges" value={summary?.counts.edges ?? "-"} />
          <Metric label="Unresolved" value={summary?.counts.unresolved ?? "-"} />
          <Metric label="Parse Errors" value={summary?.counts.parse_errors ?? "-"} />
        </div>

        <div className="graph-layout">
          <div className="graph-area">
            <div className="section-title">
              <Activity size={16} />
              <span>Relationship Graph</span>
              {graph?.truncated && <em>Truncated: {graph.truncation_reason}</em>}
            </div>
            {graph ? <GraphView graph={graph} onSelectNode={loadNode} /> : <Empty text="Select a symbol and load a graph" />}
          </div>

          <aside className="details">
            <div className="section-title">
              <FileSearch size={16} />
              <span>Source Evidence</span>
            </div>
            {details ? <SourcePanel details={details} /> : <Empty text="Click a node to inspect source" />}
          </aside>
        </div>
      </section>
    </main>
  );
}

function GraphView({ graph, onSelectNode }: { graph: GraphPayload; onSelectNode: (nodeId: string) => void }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const networkRef = useRef<Network | null>(null);

  function fitGraph() {
    networkRef.current?.fit({
      animation: { duration: 250, easingFunction: "easeInOutQuad" },
      maxZoomLevel: 1.2
    });
  }

  const nodes = useMemo(
    () =>
      graph.nodes.map((node) => ({
        id: node.id,
        label: node.qualified_name,
        shape: node.kind === "Class" ? "box" : node.kind === "File" ? "database" : "dot",
        color: colorForKind(node.kind),
        font: { size: 14, face: "Inter, system-ui, sans-serif" }
      })),
    [graph.nodes]
  );

  const edges = useMemo(
    () =>
      graph.edges.map((edge, index) => ({
        id: `${edge.source_id}-${edge.target_id}-${edge.kind}-${index}`,
        from: edge.source_id,
        to: edge.target_id,
        label: edge.kind,
        arrows: "to",
        color: colorForEdge(edge.kind),
        font: { size: 10, align: "middle" }
      })),
    [graph.edges]
  );

  useEffect(() => {
    if (!containerRef.current) return;
    const network = new Network(
      containerRef.current,
      { nodes: new DataSet(nodes), edges: new DataSet(edges) },
      {
        autoResize: true,
        layout: { improvedLayout: true },
        physics: { stabilization: true, barnesHut: { springLength: 150 } },
        interaction: { hover: false, multiselect: false },
        edges: { smooth: { enabled: true, type: "dynamic", roundness: 0.5 } }
      }
    );
    network.on("click", (params) => {
      const nodeId = params.nodes[0];
      if (nodeId) onSelectNode(String(nodeId));
    });
    network.once("stabilizationIterationsDone", () => {
      fitGraph();
    });
    networkRef.current = network;
    window.requestAnimationFrame(() => fitGraph());
    window.setTimeout(() => fitGraph(), 150);
    return () => {
      network.destroy();
      networkRef.current = null;
    };
  }, [nodes, edges, onSelectNode]);

  return (
    <div className="graph-frame">
      <button className="graph-fit-button" onClick={fitGraph} title="Fit graph">
        <Scan size={16} />
        Fit
      </button>
      <div className="graph-canvas" ref={containerRef} />
    </div>
  );
}

function SourcePanel({ details }: { details: NodeDetails }) {
  return (
    <div className="source-panel">
      <div className="node-heading">
        <strong>{details.qualified_name}</strong>
        <span>{details.kind} · {details.path}</span>
      </div>
      <pre>
        {details.snippet.lines.map((line) => (
          <code key={line.line} className={line.line >= details.span.start_line && line.line <= details.span.end_line ? "hit" : ""}>
            <span>{String(line.line).padStart(4, " ")}</span>
            {line.text}
            {"\n"}
          </code>
        ))}
      </pre>
    </div>
  );
}

function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="panel">
      <div className="panel-title">
        {icon}
        <span>{title}</span>
      </div>
      {children}
    </div>
  );
}

function StatusLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="status-line">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>;
}

function colorForKind(kind: string) {
  if (kind === "Class") return { background: "#dff3ea", border: "#31936a" };
  if (kind === "Method") return { background: "#e7efff", border: "#3d69b1" };
  if (kind === "File") return { background: "#f6e9d9", border: "#a56b2a" };
  return { background: "#f3e7ef", border: "#9b477b" };
}

function colorForEdge(kind: string) {
  if (kind === "CALLS") return "#3d69b1";
  if (kind === "INHERITS") return "#31936a";
  if (kind === "IMPORTS") return "#a56b2a";
  if (kind === "REFERENCES") return "#8a5a9e";
  if (kind === "DECLARES_DEPENDENCY") return "#b35c48";
  return "#6c737f";
}

createRoot(document.getElementById("root")!).render(<App />);
