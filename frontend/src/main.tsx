import React, {
  FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { createRoot } from "react-dom/client";
import cytoscape, { Core } from "cytoscape";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Database,
  FileText,
  GitBranch,
  Github,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  Network,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
  ZoomIn,
  ZoomOut,
  Maximize2,
  ExternalLink,
  CheckCircle2,
  Clock3,
  AlertCircle,
  FolderOpen,
} from "lucide-react";
import "./styles.css";

type Row = Record<string, any>;
async function api(path: string, options: RequestInit = {}) {
  const headers: Record<string, string> =
    options.body instanceof FormData
      ? {}
      : { "Content-Type": "application/json" };
  const response = await fetch(path, {
    ...options,
    headers: { ...headers, ...options.headers },
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      typeof result.detail === "string"
        ? result.detail
        : JSON.stringify(result.detail),
    );
  return result;
}
const send = (method: string, body?: unknown): RequestInit => ({
  method,
  ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
});
const date = (value: string) =>
  value
    ? new Date(value).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
const short = (value: string, n = 100) =>
  value?.length > n ? value.slice(0, n) + "…" : value;
const NAV = [
  ["overview", "Overview", LayoutDashboard],
  ["sources", "Sources", FileText],
  ["connectors", "Connectors", GitBranch],
  ["graph", "Graph explorer", Network],
  ["agents", "Agents", Bot],
  ["reviews", "Review queue", ShieldCheck],
  ["activity", "Activity", Activity],
] as const;

function Badge({ value }: { value: string }) {
  return (
    <span className={`badge ${value}`}>{value?.replaceAll("_", " ")}</span>
  );
}
function Empty({
  icon: Icon = FolderOpen,
  title,
  description,
  action,
}: {
  icon?: React.ElementType;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={28} />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="modal-shade"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="section-head">
          <h2>{title}</h2>
          <button className="icon-button" onClick={onClose} aria-label="Close">
            <X size={19} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

function Auth({ setup, onSuccess }: { setup: boolean; onSuccess: () => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(e.currentTarget);
    try {
      await api(
        `/api/auth/${setup ? "setup" : "login"}`,
        send("POST", Object.fromEntries(form)),
      );
      onSuccess();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth">
      <div className="auth-story">
        <div className="brand">
          <div className="brand-symbol">
            <GitBranch size={24} />
          </div>
          DecisionTrail
        </div>
        <div>
          <div className="eyebrow light">CONNECTED COMPANY INTELLIGENCE</div>
          <h1>
            Your knowledge.
            <br />
            Connected to
            <br />
            <em>what happens next.</em>
          </h1>
          <p>
            Bring your sources together, explore the relationships, and give
            your agents the context to act.
          </p>
          <div className="auth-capabilities">
            <span>
              <Database size={16} /> FalkorDB knowledge graph
            </span>
            <span>
              <Github size={16} /> GitHub + file ingestion
            </span>
            <span>
              <Bot size={16} /> Agents with evidence
            </span>
          </div>
        </div>
        <small>Local workspace · Your data stays under your control</small>
      </div>
      <div className="auth-form">
        <form onSubmit={submit}>
          <div className="eyebrow">
            {setup ? "GET STARTED" : "WELCOME BACK"}
          </div>
          <h2>
            {setup ? "Create your workspace" : "Sign in to DecisionTrail"}
          </h2>
          <p className="subtle">
            {setup
              ? "Create the administrator account for this installation."
              : "Continue to your company knowledge workspace."}
          </p>
          {setup && (
            <label>
              Your name
              <input name="name" placeholder="Alex Morgan" required />
            </label>
          )}
          <label>
            Email
            <input
              name="email"
              type="email"
              placeholder="you@company.com"
              required
            />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              minLength={10}
              placeholder={setup ? "At least 10 characters" : "Your password"}
              required
            />
          </label>
          {error && <div className="error-banner">{error}</div>}
          <button className="primary wide" disabled={busy}>
            {busy ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <ArrowRight size={17} />
            )}{" "}
            {setup ? "Create workspace" : "Sign in"}
          </button>
          <button type="button" className="secondary wide" style={{marginTop:12}} disabled={busy} onClick={async()=>{setBusy(true);setError('');try{await api('/api/auth/github-cli',send('POST'));onSuccess()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}><Github size={17}/>Continue with GitHub CLI</button>
          <p className="fine-print">
            {setup
              ? "Account and connector settings are stored locally. Hosted database credentials can be configured later."
              : "Contact your installation administrator if you need an account."}
          </p>
        </form>
      </div>
    </div>
  );
}

function GraphExplorer({
  base,
  labels,
  notify,
}: {
  base: string;
  labels: Row[];
  notify: (text: string, error?: boolean) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);
  const [data, setData] = useState<Row>({ nodes: [], edges: [] });
  const [search, setSearch] = useState("");
  const [label, setLabel] = useState("");
  const [selected, setSelected] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState(
    "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 30",
  );
  const [results, setResults] = useState<Row | null>(null);
  const [consoleOpen, setConsoleOpen] = useState(false);
  const [impact, setImpact] = useState<Row | null>(null);
  useEffect(() => setImpact(null), [selected?.id]);
  async function previewImpact() {
    try {
      setImpact(await api(`${base}/graph/impact?entity_id=${encodeURIComponent(selected!.id)}`));
    } catch (e) {
      notify((e as Error).message, true);
    }
  }
  const load = useCallback(
    async (more = false) => {
      setBusy(true);
      try {
        const result = await api(
          `${base}/graph?search=${encodeURIComponent(search)}&label=${encodeURIComponent(label)}&limit=300&offset=${more ? data.nodes.length : 0}&visible=${more ? data.nodes.map((n: Row) => n.internal_id).join(',') : ''}`,
        );
        setData((prev) =>
          more
            ? {
                ...result,
                nodes: [...prev.nodes, ...result.nodes],
                edges: [...new Map([...prev.edges, ...result.edges].map((edge: Row) => [edge.id, edge])).values()],
              }
            : result,
        );
      } catch (e) {
        notify((e as Error).message, true);
      } finally {
        setBusy(false);
      }
    },
    [base, search, label, data.nodes],
  );
  useEffect(() => {
    load();
  }, [base]);
  useEffect(() => {
    if (!container.current) return;
    const colors: Record<string, string> = {
      Document: "#d68a4a",
      DocumentVersion: "#b8c7bd",
      Chunk: "#c7d8c8",
      Person: "#5c79ca",
      Repository: "#7e63bb",
      File: "#b28e52",
      Issue: "#cf6e72",
      PullRequest: "#459897",
      Project: "#36825a",
      Task: "#3c9777",
      Record: "#75a0bf",
    };
    const elements: any[] = [
      ...data.nodes.map((n: Row) => ({
        data: {
          id: String(n.internal_id),
          label: n.name || n.id,
          color:
            colors[n.labels?.find((x: string) => x !== "Entity")] || "#537c65",
          raw: n,
        },
      })),
      ...data.edges.map((r: Row) => ({
        data: {
          id: "e" + r.id,
          source: String(r.source),
          target: String(r.target),
          label: r.predicate || r.type,
          inactive: r.active === false,
        },
      })),
    ];
    cy.current?.destroy();
    cy.current = cytoscape({
      container: container.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            width: 26,
            height: 26,
            "font-size": 10,
            "text-valign": "bottom",
            "text-margin-y": 8,
            color: "#40564a",
            "text-max-width": "100px",
            "text-wrap": "ellipsis",
            "border-width": 3,
            "border-color": "#ffffff",
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.2,
            "line-color": "#b6c9bc",
            "target-arrow-color": "#b6c9bc",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "arrow-scale": 0.6,
            opacity: 0.65,
          },
        },
        {
          selector: ":selected",
          style: {
            "border-width": 5,
            "border-color": "#b2dc76",
            "background-color": "#174e3b",
          },
        },
        {
          selector: "edge:selected",
          style: {
            label: "data(label)",
            "font-size": 10,
            "text-background-color": "#fff",
            "text-background-opacity": 1,
            "line-color": "#174e3b",
          },
        },
      ],
      layout: {
        name: "cose",
        animate: false,
        padding: 45,
        nodeRepulsion: () => 9000,
        idealEdgeLength: () => 80,
      } as any,
      minZoom: 0.08,
      maxZoom: 4,
    });
    cy.current.on("tap", "node", (event) =>
      setSelected(event.target.data("raw")),
    );
    return () => {
      cy.current?.destroy();
      cy.current = null;
    };
  }, [data]);
  async function expand() {
    if (!selected) return;
    try {
      const result = await api(
        `${base}/graph/neighbors?entity_id=${encodeURIComponent(selected.id)}`,
      );
      setData((prev: Row) => ({
        ...prev,
        nodes: [
          ...new Map(
            [...prev.nodes, ...result.nodes].map((n: Row) => [
              n.internal_id,
              n,
            ]),
          ).values(),
        ],
        edges: [
          ...new Map(
            [...prev.edges, ...result.edges].map((r: Row) => [r.id, r]),
          ).values(),
        ],
      }));
    } catch (e) {
      notify((e as Error).message, true);
    }
  }
  async function runQuery() {
    setBusy(true);
    try {
      const result = await api(`${base}/graph/query`, send("POST", { query }));
      setResults(result);
      const nodes = new Map(),
        edges = new Map();
      function visit(v: any) {
        if (!v || typeof v !== "object") return;
        if (v.kind === "node") nodes.set(v.internal_id, v);
        if (v.kind === "edge")
          edges.set(v.internal_id, { id: v.internal_id, ...v });
        Object.values(v).forEach((x) => {
          if (typeof x === "object") visit(x);
        });
      }
      result.rows.forEach(visit);
      if (nodes.size)
        setData({ nodes: [...nodes.values()], edges: [...edges.values()] });
      notify(`Query returned ${result.rows.length} rows`);
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-title">
        <div>
          <div className="eyebrow">EXPLORE YOUR COMPANY</div>
          <h1>Knowledge graph</h1>
          <p>Follow the connections behind your sources, people, and work.</p>
        </div>
        <button
          className="secondary"
          onClick={() => setConsoleOpen(!consoleOpen)}
        >
          <Database size={16} />
          Query console
        </button>
      </div>
      <section className="panel graph-panel">
        <div className="graph-toolbar">
          <div className="search-box">
            <Search size={16} />
            <input
              aria-label="Search graph nodes"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search nodes…"
              onKeyDown={(e) => {
                if (e.key === "Enter") load();
              }}
            />
          </div>
          <select
            aria-label="Filter node type"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          >
            <option value="">All node types</option>
            {labels.map((l) => (
              <option key={l.label}>{l.label}</option>
            ))}
          </select>
          <button className="secondary" onClick={() => load()} disabled={busy}>
            Apply filters
          </button>
          <span className="graph-count">
            {data.nodes.length} nodes · {data.edges.length} edges
          </span>
        </div>
        <div className="graph-area">
          <div className="graph-canvas" ref={container} />
          {!data.nodes.length && (
            <div className="graph-empty">
              <Network size={40} />
              <h3>Your connections will appear here</h3>
              <p>Import sources to start building your graph.</p>
            </div>
          )}
          <div className="graph-zoom">
            <button
              title="Zoom in"
              onClick={() => cy.current?.zoom((cy.current?.zoom() || 1) * 1.3)}
            >
              <ZoomIn size={18} />
            </button>
            <button
              title="Zoom out"
              onClick={() => cy.current?.zoom((cy.current?.zoom() || 1) / 1.3)}
            >
              <ZoomOut size={18} />
            </button>
            <button
              title="Fit graph"
              onClick={() => cy.current?.fit(undefined, 40)}
            >
              <Maximize2 size={17} />
            </button>
          </div>
          {selected && (
            <aside className="node-inspector">
              <div className="section-head">
                <span className="eyebrow">NODE INSPECTOR</span>
                <button
                  className="icon-button"
                  onClick={() => setSelected(null)}
                  aria-label="Close inspector"
                >
                  <X size={16} />
                </button>
              </div>
              <h3>{selected.name}</h3>
              <div className="row wrap">
                {selected.labels?.map((x: string) => (
                  <Badge key={x} value={x} />
                ))}
              </div>
              <dl>
                {Object.entries(selected)
                  .filter(
                    ([k]) =>
                      ![
                        "kind",
                        "internal_id",
                        "name",
                        "labels",
                        "text",
                        "embedding",
                      ].includes(k),
                  )
                  .map(([k, v]) => (
                    <React.Fragment key={k}>
                      <dt>{k}</dt>
                      <dd>{String(v)}</dd>
                    </React.Fragment>
                  ))}
              </dl>
              {selected.text && (
                <p className="source-excerpt">{short(selected.text, 1600)}</p>
              )}
              <button className="primary small" onClick={expand}>
                <Plus size={15} />
                Expand neighbors
              </button>
              {selected.labels?.includes("Entity") && (
                <>
                  <button className="secondary small" onClick={previewImpact}>
                    <Network size={15} />
                    Preview impact
                  </button>
                  {impact && (
                    <div className="impact-preview">
                      <p className="fine-print">
                        Simulation only — nothing is changed. Assumption:{" "}
                        {impact.assumption}. Follows active DEPENDS_ON, PART_OF,
                        IN_REPOSITORY, USES, REQUIRES and BLOCKED_BY
                        relationships up to 3 hops.
                      </p>
                      {impact.items.length ? (
                        impact.items.map((item: Row) => (
                          <div className="version-item" key={item.id}>
                            <strong>{item.name}</strong>
                            <small>
                              {item.hops} hop{item.hops > 1 ? "s" : ""}:{" "}
                              {item.path.join(" → ")} ({item.relations.join(", ")})
                            </small>
                          </div>
                        ))
                      ) : (
                        <p className="subtle">No dependent entities found.</p>
                      )}
                    </div>
                  )}
                </>
              )}
            </aside>
          )}
        </div>
        <div className="graph-footer">
          <span>
            <span className="dot" />
            Click a node to inspect evidence. Drag to explore; scroll to zoom.
          </span>
          {data.has_more && (
            <button className="text-button" onClick={() => load(true)}>
              Load more nodes <ChevronRight size={15} />
            </button>
          )}
        </div>
      </section>
      {consoleOpen && (
        <section className="panel query-console">
          <div className="section-head">
            <div>
              <h2>Cypher console</h2>
              <p className="subtle">
                Read-only queries in the current workspace · 2 second query
                limit
              </p>
            </div>
            <button className="primary" onClick={runQuery} disabled={busy}>
              Run query <ArrowRight size={15} />
            </button>
          </div>
          <textarea
            aria-label="Cypher query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            spellCheck={false}
          />
          {results && (
            <div className="query-results">
              <small>
                {results.rows.length} rows{" "}
                {results.truncated ? "· results truncated" : ""}
              </small>
              <pre>{JSON.stringify(results.rows, null, 2)}</pre>
            </div>
          )}
        </section>
      )}
    </>
  );
}

function App() {
  const [ready, setReady] = useState(false),
    [setup, setSetup] = useState(false),
    [user, setUser] = useState<Row | null>(null);
  const [workspaces, setWorkspaces] = useState<Row[]>([]),
    [workspaceId, setWorkspaceId] = useState("");
  const [view, setView] = useState(
    new URLSearchParams(location.search).get("view") || "overview",
  );
  const [overview, setOverview] = useState<Row>({}),
    [sources, setSources] = useState<Row[]>([]),
    [tasks, setTasks] = useState<Row[]>([]),
    [diff, setDiff] = useState<Row | null>(null),
    [conflicts, setConflicts] = useState<Row[]>([]),
    [jobs, setJobs] = useState<Row[]>([]),
    [agents, setAgents] = useState<Row[]>([]),
    [runs, setRuns] = useState<Row[]>([]),
    [reviews, setReviews] = useState<Row[]>([]),
    [connector, setConnector] = useState<Row>({ connections: [] });
  const [toast, setToast] = useState<{ text: string; error: boolean } | null>(
      null,
    ),
    [modal, setModal] = useState(""),
    [busy, setBusy] = useState(false),
    [detail, setDetail] = useState<Row | null>(null),
    [search, setSearch] = useState("");
  const [agentId, setAgentId] = useState(""),
    [question, setQuestion] = useState(""),
    [answer, setAnswer] = useState<Row | null>(null),
    [useAI, setUseAI] = useState(true);
  const [adminSettings, setAdminSettings] = useState<Row>({}),
    [users, setUsers] = useState<Row[]>([]),
    [audit, setAudit] = useState<Row[]>([]),
    [repos, setRepos] = useState<Row[]>([]);
  const [repoPage, setRepoPage] = useState(1);
  const [repoSearch, setRepoSearch] = useState("");
  const base = `/api/w/${workspaceId}`;
  const jobsSnapshot = useRef("");
  const currentWorkspaceRef = useRef(workspaceId);
  currentWorkspaceRef.current = workspaceId;
  const activeWorkspace = workspaces.find((w) => w.id === workspaceId);
  function notify(text: string, error = false) {
    setToast({ text, error });
    setTimeout(() => setToast(null), 5500);
  }
  const init = useCallback(async () => {
    try {
      const status = await api("/api/auth/status");
      setSetup(status.setup_required);
      try {
        const me = await api("/api/me");
        setUser(me);
        const ws = await api("/api/workspaces");
        setWorkspaces(ws);
        setWorkspaceId((prev) =>
          ws.some((x: Row) => x.id === prev) ? prev : ws[0]?.id || "",
        );
      } catch {
        setUser(null);
      }
    } finally {
      setReady(true);
    }
  }, []);
  useEffect(() => {
    init();
  }, [init]);
  const refresh = useCallback(async () => {
    if (!workspaceId) return;
    try {
      const [o, s, j, a, r, rv, c, tk, cf] = await Promise.all([
        api(base + "/overview"),
        api(base + "/sources"),
        api(base + "/jobs"),
        api(base + "/agents"),
        api(base + "/runs"),
        api(base + "/reviews"),
        api("/api/connectors"),
        api(base + "/tasks"),
        api(base + "/analysis/conflicts"),
      ]);
      if (currentWorkspaceRef.current !== workspaceId) return;
      jobsSnapshot.current = JSON.stringify(j);
      setOverview(o);
      setSources(s);
      setJobs(j);
      setAgents(a);
      setRuns(r);
      setReviews(rv);
      setConnector(c);
      setTasks(tk);
      setConflicts(cf.candidates);
      setAgentId((prev) =>
        a.some((x: Row) => x.id === prev) ? prev : a[0]?.id || "",
      );
    } catch (e) {
      notify((e as Error).message, true);
    }
  }, [workspaceId, base]);
  useEffect(() => setDiff(null), [detail?.id]);
  useEffect(() => {
    setAnswer(null);
    setDetail(null);
    refresh();
  }, [refresh]);
  useEffect(() => {
    if (!workspaceId) return;
    const timer = setInterval(async () => {
      try {
        const updated = await api(base + "/jobs");
        if (currentWorkspaceRef.current !== workspaceId) return;
        if (jobsSnapshot.current !== JSON.stringify(updated)) {
          jobsSnapshot.current = JSON.stringify(updated);
          await refresh();
        }
      } catch {}
    }, 3000);
    return () => clearInterval(timer);
  }, [base, workspaceId, refresh]);
  useEffect(() => {
    if (view === "admin" && user?.role === "admin") {
      Promise.all([
        api("/api/admin/settings"),
        api("/api/admin/users"),
        api("/api/admin/audit"),
      ])
        .then(([s, u, a]) => {
          setAdminSettings(s);
          setUsers(u);
          setAudit(a);
        })
        .catch((e) => notify(e.message, true));
    }
  }, [view, user, modal]);
  async function upload(files: FileList | null) {
    if (!files) return;
    setBusy(true);
    try {
      for (const file of Array.from(files)) {
        const body = new FormData();
        body.append("file", file);
        await api(base + "/sources/upload", { method: "POST", body });
      }
      notify(
        `${files.length} file${files.length > 1 ? "s" : ""} queued for ingestion`,
      );
      await refresh();
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function action(path: string, body: unknown = {}, message = "Saved") {
    setBusy(true);
    try {
      const result = await api(path, send("POST", body));
      notify(message);
      await refresh();
      return result;
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function submitModal(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const values = Object.fromEntries(new FormData(e.currentTarget));
    setBusy(true);
    try {
      if (modal === "workspace") {
        await api("/api/workspaces", send("POST", values));
        await init();
      }
      if (modal === "text") {
        await api(base + "/sources/text", send("POST", values));
        await refresh();
      }
      if (modal === "agent") {
        await api(base + "/agents", send("POST", values));
        await refresh();
      }
      if (modal === "user") {
        await api("/api/admin/users", send("POST", values));
      }
      setModal("");
      notify("Saved successfully");
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function runAgent(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setAnswer(null);
    try {
      const result = await api(
        `${base}/agents/${agentId}/run`,
        send("POST", { question, use_ai: useAI }),
      );
      setAnswer(result);
      await refresh();
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function saveSettings(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    try {
      await api(
        "/api/admin/settings",
        send("PUT", Object.fromEntries(new FormData(e.currentTarget))),
      );
      notify("Integration settings saved");
      setAdminSettings(await api("/api/admin/settings"));
      setConnector(await api("/api/connectors"));
    } catch (e) {
      notify((e as Error).message, true);
    }
  }
  async function sync(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await action(
      base + "/connectors/github/sync",
      {
        repository: f.get("repository"),
        documents: f.has("documents"),
        issues: f.has("issues"),
        pull_requests: f.has("pull_requests"),
        limit: Number(f.get("limit")),
      },
      "Repository sync queued",
    );
  }
  async function openSource(id: string) {
    try {
      setDetail(await api(base + "/sources/" + id));
    } catch (e) {
      notify((e as Error).message, true);
    }
  }
  if (!ready)
    return (
      <div className="loading-screen">
        <LoaderCircle className="spin" />
        Loading your workspace…
      </div>
    );
  if (!user) return <Auth setup={setup} onSuccess={init} />;
  const activeJobs = jobs.filter((j) =>
    ["queued", "running"].includes(j.status),
  );
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-symbol">
            <GitBranch size={22} />
          </div>
          DecisionTrail
        </div>
        <div className="workspace-picker">
          <div className="workspace-icon">
            {activeWorkspace?.name?.[0] || "W"}
          </div>
          <select
            aria-label="Workspace"
            value={workspaceId}
            onChange={(e) => setWorkspaceId(e.target.value)}
          >
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
          <button
            aria-label="Create workspace"
            onClick={() => setModal("workspace")}
          >
            <Plus size={15} />
          </button>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {NAV.map(([id, label, Icon]) => (
            <button
              key={id}
              className={view === id ? "active" : ""}
              onClick={() => setView(id)}
            >
              <Icon size={18} />
              <span>{label}</span>
              {id === "reviews" && overview.pending_reviews > 0 && (
                <b>{overview.pending_reviews}</b>
              )}
              {id === "activity" && activeJobs.length > 0 && (
                <span className="nav-dot" />
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          {user.role === "admin" && (
            <button
              className={view === "admin" ? "active" : ""}
              onClick={() => setView("admin")}
            >
              <Settings2 size={18} />
              Administration
            </button>
          )}
          <div className="storage-card">
            <Database size={17} />
            <div>
              <strong>{overview.graph ? 'FalkorDB connected' : 'Connecting to graph…'}</strong>
              <small>Persistent local workspace</small>
            </div>
            <span className="live-dot" />
          </div>
          <div className="user-row">
            <div className="avatar">{user.name[0]}</div>
            <div>
              <strong>{user.name}</strong>
              <small>{user.role}</small>
            </div>
            <button
              aria-label="Sign out"
              onClick={async () => {
                await api("/api/auth/logout", send("POST"));
                setUser(null);
              }}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <span>{activeWorkspace?.name}</span>
            <ChevronRight size={14} />
            <strong>
              {view === "admin"
                ? "Administration"
                : NAV.find((n) => n[0] === view)?.[1]}
            </strong>
          </div>
          <div className="row">
            <span className="local-label">
              <span className="dot" />
              Local installation
            </span>
            <button
              className="icon-button"
              aria-label="Refresh workspace"
              onClick={refresh}
            >
              <Activity size={18} />
            </button>
          </div>
        </header>
        <main className={"content " + (view === "graph" ? "wide-content" : "")}>
          {view === "overview" && (
            <>
              <div className="page-title">
                <div>
                  <div className="eyebrow">YOUR COMPANY, CONNECTED</div>
                  <h1>Workspace overview</h1>
                  <p>
                    From scattered sources to a shared understanding of your
                    company.
                  </p>
                </div>
                <button className="primary" onClick={() => setView("sources")}>
                  <Plus size={16} />
                  Add knowledge
                </button>
              </div>
              <div className="stats-grid">
                {[
                  [
                    FileText,
                    overview.sources || 0,
                    "Sources",
                    "Connected knowledge",
                  ],
                  [
                    Network,
                    overview.graph?.nodes || 0,
                    "Graph nodes",
                    `${overview.graph?.edges || 0} relationships`,
                  ],
                  [
                    Bot,
                    overview.agents || 0,
                    "Agents",
                    "Workspace intelligence",
                  ],
                  [
                    ShieldCheck,
                    overview.pending_reviews || 0,
                    "Pending reviews",
                    "Actions awaiting a decision",
                  ],
                ].map(([Icon, value, label, note], i) => {
                  const I = Icon as React.ElementType;
                  return (
                    <div className="stat-card" key={i}>
                      <div className="stat-icon">
                        <I size={19} />
                      </div>
                      <strong>{String(value)}</strong>
                      <span>{String(label)}</span>
                      <small>{String(note)}</small>
                    </div>
                  );
                })}
              </div>
              {!overview.sources ? (
                <section className="onboarding panel">
                  <div className="onboarding-art">
                    <Network size={74} />
                    <span className="orbit one" />
                    <span className="orbit two" />
                  </div>
                  <div>
                    <div className="eyebrow">BUILD YOUR COMPANY BRAIN</div>
                    <h2>Start with the knowledge you already have.</h2>
                    <p>
                      Upload documents, import structured records, or connect a
                      GitHub repository. Your graph will grow from the data you
                      add.
                    </p>
                    <div className="row">
                      <button
                        className="primary"
                        onClick={() => setView("sources")}
                      >
                        <Upload size={16} />
                        Import your first source
                      </button>
                      <button
                        className="secondary"
                        onClick={() => setView("connectors")}
                      >
                        <Github size={16} />
                        Connect GitHub
                      </button>
                    </div>
                  </div>
                </section>
              ) : (
                <div className="two-columns">
                  <section className="panel">
                    <div className="section-head">
                      <h2>Knowledge composition</h2>
                      <button
                        className="text-button"
                        onClick={() => setView("graph")}
                      >
                        Explore graph <ArrowRight size={15} />
                      </button>
                    </div>
                    <div className="label-bars">
                      {overview.graph?.labels
                        ?.filter((x: Row) => x.label !== "Entity")
                        .slice(0, 7)
                        .map((x: Row) => (
                          <div key={x.label}>
                            <span>{x.label}</span>
                            <div>
                              <i
                                style={{
                                  width: `${Math.max(4, (x.count / overview.graph.nodes) * 100)}%`,
                                }}
                              />
                            </div>
                            <strong>{x.count}</strong>
                          </div>
                        ))}
                    </div>
                  </section>
                  <section className="panel">
                    <div className="section-head">
                      <h2>Recent sources</h2>
                      <button
                        className="text-button"
                        onClick={() => setView("sources")}
                      >
                        View all
                      </button>
                    </div>
                    {sources.slice(0, 5).map((s) => (
                      <button
                        className="list-item"
                        key={s.id}
                        onClick={() => openSource(s.id)}
                      >
                        <FileText size={18} />
                        <div>
                          <strong>{short(s.title, 60)}</strong>
                          <small>
                            {s.kind} · version {s.version}
                          </small>
                        </div>
                        <ChevronRight size={15} />
                      </button>
                    ))}
                  </section>
                </div>
              )}
              <div className="two-columns">
                <section className="panel">
                  <div className="section-head">
                    <h2>Recent activity</h2>
                    <button
                      className="text-button"
                      onClick={() => setView("activity")}
                    >
                      View jobs
                    </button>
                  </div>
                  {jobs.length ? (
                    jobs.slice(0, 4).map((j) => (
                      <div className="activity-item" key={j.id}>
                        <div className={"activity-symbol " + j.status}>
                          {j.status === "completed" ? (
                            <Check size={16} />
                          ) : j.status === "failed" ? (
                            <AlertCircle size={16} />
                          ) : (
                            <Clock3 size={16} />
                          )}
                        </div>
                        <div>
                          <strong>
                            {j.kind === "github"
                              ? "GitHub repository sync"
                              : j.kind === "enrich"
                                ? "Knowledge enrichment"
                                : "Source ingestion"}
                          </strong>
                          <small>{short(j.message, 100)}</small>
                        </div>
                        <Badge value={j.status} />
                      </div>
                    ))
                  ) : (
                    <p className="quiet">
                      Ingestion and sync activity will appear here.
                    </p>
                  )}
                </section>
                <section className="panel">
                  <div className="section-head">
                    <h2>Ask your knowledge</h2>
                    <Bot size={19} />
                  </div>
                  <p className="subtle">
                    Agents search your sources, follow graph relationships, and
                    return evidence you can inspect.
                  </p>
                  <div className="suggestions">
                    {[
                      "What projects and people are connected?",
                      "Which sources discuss our current priorities?",
                    ].map((q) => (
                      <button
                        key={q}
                        onClick={() => {
                          setQuestion(q);
                          setView("agents");
                        }}
                      >
                        {q}
                        <ArrowRight size={15} />
                      </button>
                    ))}
                  </div>
                </section>
              </div>
            </>
          )}
          {view === "sources" && (
            <>
              <div className="page-title">
                <div>
                  <div className="eyebrow">YOUR KNOWLEDGE LIBRARY</div>
                  <h1>Sources</h1>
                  <p>
                    Import data, inspect its provenance, and keep every version.
                  </p>
                </div>
                <div className="row">
                  <button
                    className="secondary"
                    onClick={() => setModal("text")}
                  >
                    <FileText size={16} />
                    Paste text
                  </button>
                  <label className="primary button-label">
                    <Upload size={16} />
                    Upload files
                    <input
                      type="file"
                      multiple
                      hidden
                      accept=".md,.txt,.csv,.json,.pdf,.docx,.rst,.log,.yaml,.yml"
                      onChange={(e) => {
                        upload(e.target.files);
                        e.target.value = "";
                      }}
                    />
                  </label>
                </div>
              </div>
              <div
                className="upload-zone"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  upload(e.dataTransfer.files);
                }}
              >
                <div className="upload-icon">
                  <ArrowDownToLine size={23} />
                </div>
                <div>
                  <strong>Drop your company knowledge here</strong>
                  <p>
                    PDF, DOCX, Markdown, text, CSV, JSON and YAML · Up to 10 MB
                    per file
                  </p>
                </div>
                <span className="subtle">Versioned automatically</span>
              </div>
              {activeJobs.length > 0 && (
                <div className="info-banner">
                  <LoaderCircle className="spin" size={16} />
                  {activeJobs.length} ingestion job
                  {activeJobs.length > 1 ? "s" : ""} running. Sources appear as
                  they finish.
                </div>
              )}
              <section className="panel table-panel">
                <div className="table-toolbar">
                  <h2>{sources.length} sources</h2>
                  <div className="search-box">
                    <Search size={16} />
                    <input
                      placeholder="Find a source…"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </div>
                </div>
                {sources.length ? (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Source</th>
                          <th>Type</th>
                          <th>Version</th>
                          <th>Status</th>
                          <th>Updated</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {sources
                          .filter((s) =>
                            s.title
                              .toLowerCase()
                              .includes(search.toLowerCase()),
                          )
                          .map((s) => (
                            <tr key={s.id}>
                              <td>
                                <button
                                  className="source-name"
                                  onClick={() => openSource(s.id)}
                                >
                                  <FileText size={17} />
                                  {short(s.title, 75)}
                                </button>
                              </td>
                              <td>
                                <Badge value={s.kind} />
                              </td>
                              <td>v{s.version}</td>
                              <td>
                                <Badge value={s.status} />
                              </td>
                              <td className="subtle">{date(s.updated_at)}</td>
                              <td>
                                <button
                                  className="icon-button"
                                  aria-label={"Inspect " + s.title}
                                  onClick={() => openSource(s.id)}
                                >
                                  <ChevronRight size={17} />
                                </button>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty
                    title="Your source library is ready"
                    description="Bring in documents or structured records. CSV rows and JSON graph data become queryable nodes; documents become versioned passages."
                  />
                )}
              </section>
            </>
          )}
          {view === "connectors" && (
            <>
              <div className="page-title">
                <div>
                  <div className="eyebrow">CONNECT YOUR TOOLS</div>
                  <h1>Connectors</h1>
                  <p>
                    Bring current work and its context into your company graph.
                  </p>
                </div>
              </div>
              <div className="two-columns">
                <section className="panel connector-card">
                  <div className="section-head">
                    <div className="connector-icon">
                      <Github size={30} />
                    </div>
                    <Badge
                      value={
                        connector.connections.length
                          ? "connected"
                          : "not_connected"
                      }
                    />
                  </div>
                  <h2>GitHub</h2>
                  <p className="subtle">
                    Import repository documents, issues, pull requests, authors,
                    and assignees with their relationships.
                  </p>
                  {connector.connections.length ? (
                    <>
                      <div className="connected-account">
                        <CheckCircle2 size={17} />
                        Connected as{" "}
                        <strong>{connector.connections[0].login}</strong>
                      </div>
                      <div className="row">
                        <button
                          className="secondary"
                          onClick={async () => {
                            try {
                              setRepos(
                                await api(
                                  "/api/connectors/github/repositories",
                                ),
                              );
                              setRepoPage(1);
                            } catch (e) {
                              notify((e as Error).message, true);
                            }
                          }}
                        >
                          Browse repositories
                        </button>
                        <a className="text-button" href={connector.connections[0].manage_url} target="_blank" rel="noreferrer">Manage access <ExternalLink size={13}/></a>
                        <button
                          className="text-button"
                          onClick={() =>
                            action(
                              "/api/connectors/github/disconnect",
                              {},
                              "Connection removed locally",
                            )
                          }
                        >
                          Disconnect
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <p className="fine-print">Choose specific repositories during installation. DecisionTrail requests read access to contents, issues, pull requests, and metadata.</p>
                      <a
                        className={
                          "primary " +
                          (!connector.github_configured ? "disabled" : "")
                        }
                        href={
                          connector.github_configured
                            ? `/api/connectors/github/start`
                            : undefined
                        }
                      >
                        <Github size={16} />
                        Install GitHub App
                      </a>
                      {!connector.github_configured && (
                        <p className="fine-print">
                          An administrator needs to register the GitHub App in{" "}
                          <button
                            className="inline-link"
                            onClick={() => setView("admin")}
                          >
                            Administration
                          </button>
                          .
                        </p>
                      )}
                    </>
                  )}
                </section>
                <section className="panel">
                  <div className="eyebrow">SYNC A REPOSITORY</div>
                  <h2>Choose what to bring in</h2>
                  <p className="subtle">
                    Public repositories work immediately. Connected accounts can
                    use their authorized repositories.
                  </p>
                  <form onSubmit={sync}>
                    <label>
                      Repository
                      <input
                        name="repository"
                        placeholder="owner/repository"
                        required
                        list="repo-options"
                      />
                    </label>
                    <datalist id="repo-options">
                      {repos.map((r) => (
                        <option key={r.full_name} value={r.full_name} />
                      ))}
                    </datalist>
                    <div className="row wrap">
                      <label className="checkbox">
                        <input
                          name="documents"
                          type="checkbox"
                          defaultChecked
                        />
                        Documents
                      </label>
                      <label className="checkbox">
                        <input name="issues" type="checkbox" defaultChecked />
                        Issues
                      </label>
                      <label className="checkbox">
                        <input
                          name="pull_requests"
                          type="checkbox"
                          defaultChecked
                        />
                        Pull requests
                      </label>
                    </div>
                    <label>
                      Maximum items per category
                      <input
                        name="limit"
                        type="number"
                        min="1"
                        max="100"
                        defaultValue="30"
                      />
                    </label>
                    <button className="primary" disabled={busy}>
                      <GitBranch size={16} />
                      Start sync
                    </button>
                  </form>
                </section>
              </div>
              {repos.length > 0 && (
                <section className="panel">
                  <div className="section-head">
                    <h2>Your repositories</h2>
                    <span className="subtle">
                      {repos.length} repositories loaded
                    </span>
                  </div>
                  <div className="search-box"><Search size={16}/><input aria-label="Filter repositories" placeholder="Filter loaded repositories…" value={repoSearch} onChange={e=>setRepoSearch(e.target.value)}/></div>
                  {repos.filter(r => r.full_name.toLowerCase().includes(repoSearch.toLowerCase())).map((r) => (
                    <div className="list-item" key={r.full_name}>
                      <Github size={17} />
                      <div>
                        <strong>{r.full_name}</strong>
                        <small>{r.description || "No description"}</small>
                      </div>
                      <Badge value={r.private ? "private" : "public"} />
                    </div>
                  ))}
                  {repos.length >= repoPage * 50 && (
                    <button
                      className="secondary small"
                      onClick={async () => {
                        try {
                          const next = await api('/api/connectors/github/repositories?page=' + (repoPage + 1));
                          setRepos(prev => [...new Map([...prev, ...next].map((r: Row) => [r.full_name, r])).values()]);
                          setRepoPage(prev => prev + 1);
                          if (!next.length) notify('All available repositories loaded');
                        } catch (e) {
                          notify((e as Error).message, true);
                        }
                      }}
                    >
                      Load more repositories
                    </button>
                  )}
                </section>
              )}
              <section className="panel">
                <div className="section-head">
                  <div>
                    <h2>Files & structured data</h2>
                    <p className="subtle">
                      Upload documents or import JSON nodes and edges with
                      custom relationships.
                    </p>
                  </div>
                  <button
                    className="secondary"
                    onClick={() => setView("sources")}
                  >
                    <Upload size={16} />
                    Import files
                  </button>
                </div>
                <div className="format-chips">
                  {[
                    "PDF",
                    "DOCX",
                    "Markdown",
                    "CSV",
                    "JSON graph",
                    "Text",
                    "YAML",
                  ].map((f) => (
                    <span key={f}>{f}</span>
                  ))}
                </div>
              </section>
            </>
          )}
          {view === "graph" && (
            <GraphExplorer
              base={base}
              labels={overview.graph?.labels || []}
              notify={notify}
            />
          )}
          {view === "agents" && (
            <>
              <div className="page-title">
                <div>
                  <div className="eyebrow">INTELLIGENCE WITH CONTEXT</div>
                  <h1>Agents</h1>
                  <p>
                    Investigate your workspace with graph tools and traceable
                    sources.
                  </p>
                </div>
                <button className="secondary" onClick={() => setModal("agent")}>
                  <Plus size={16} />
                  Create agent
                </button>
              </div>
              <div className="agent-layout">
                <aside className="agent-list panel">
                  {agents.map((a) => (
                    <button
                      className={agentId === a.id ? "selected" : ""}
                      key={a.id}
                      onClick={() => {
                        setAgentId(a.id);
                        setAnswer(null);
                      }}
                    >
                      <div className="agent-icon">
                        <Bot size={20} />
                      </div>
                      <div>
                        <strong>{a.name}</strong>
                        <small>{short(a.instructions, 90)}</small>
                      </div>
                      <ChevronRight size={15} />
                    </button>
                  ))}
                  <div className="agent-history">
                    <div className="eyebrow">RECENT RUNS</div>
                    {runs.slice(0, 8).map((r) => (
                      <button
                        key={r.id}
                        onClick={() => {
                          setAnswer(JSON.parse(r.response));
                          setQuestion(r.question);
                          setAgentId(r.agent_id);
                        }}
                      >
                        <Clock3 size={14} />
                        <span>{short(r.question, 40)}</span>
                      </button>
                    ))}
                  </div>
                </aside>
                <section className="panel agent-workbench">
                  <div className="section-head">
                    <div>
                      <h2>
                        {agents.find((a) => a.id === agentId)?.name ||
                          "Choose an agent"}
                      </h2>
                      <p className="subtle">
                        Search sources · Discover entities · Traverse
                        relationships · Inspect history
                      </p>
                    </div>
                    <Badge value="workspace_scoped" />
                  </div>
                  <details className="agent-config">
                    <summary>Agent instructions</summary>
                    <form
                      key={agentId}
                      onSubmit={async (e) => {
                        e.preventDefault();
                        try {
                          const f = Object.fromEntries(
                            new FormData(e.currentTarget),
                          );
                          await api(
                            base + "/agents/" + agentId,
                            send("PUT", f),
                          );
                          notify("Agent updated");
                          refresh();
                        } catch (e) {
                          notify((e as Error).message, true);
                        }
                      }}
                    >
                      <input
                        name="name"
                        defaultValue={
                          agents.find((a) => a.id === agentId)?.name
                        }
                      />
                      <textarea
                        name="instructions"
                        defaultValue={
                          agents.find((a) => a.id === agentId)?.instructions
                        }
                      />
                      <button className="secondary small">
                        Save instructions
                      </button>
                    </form>
                  </details>
                  <form onSubmit={runAgent} className="agent-question">
                    <textarea
                      aria-label="Question for your agent"
                      placeholder="Ask a question about your sources, projects, people, or decisions…"
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      required
                    />
                    <div className="section-head">
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={useAI}
                          onChange={(e) => setUseAI(e.target.checked)}
                        />
                        Use free OpenRouter model
                      </label>
                      <button className="primary" disabled={busy || !agentId}>
                        {busy ? (
                          <LoaderCircle className="spin" size={17} />
                        ) : (
                          <Sparkles size={17} />
                        )}
                        Run investigation
                      </button>
                    </div>
                  </form>
                  {busy && (
                    <div className="investigating">
                      <LoaderCircle className="spin" size={22} />
                      <h3>Investigating your knowledge graph</h3>
                      <p>
                        Retrieving passages and following their connections…
                      </p>
                    </div>
                  )}
                  {answer && (
                    <div className="agent-result">
                      <div className="section-head">
                        <h3>Findings</h3>
                        <Badge value={answer.model_status} />
                      </div>
                      <p className="answer-text">{answer.answer}</p>
                      {answer.proposals?.length > 0 && (
                        <div className="info-banner">
                          <ShieldCheck size={16} />
                          {answer.proposals.length} review task(s) proposed.{" "}
                          <button
                            className="inline-link"
                            onClick={() => setView("reviews")}
                          >
                            Open review queue
                          </button>
                        </div>
                      )}
                      <h4>
                        Sources & evidence{" "}
                        <span>{answer.citations?.length || 0}</span>
                      </h4>
                      {answer.citations?.map((c: Row, i: number) => (
                        <div className="citation" key={i}>
                          <div className="section-head">
                            <button onClick={() => openSource(c.source_id)}>
                              <span>{i + 1}</span>
                              {c.title}
                            </button>
                            {c.uri && /^https:\/\//.test(c.uri) && (
                              <a
                                href={c.uri}
                                target="_blank"
                                rel="noreferrer"
                                aria-label="Open original source"
                              >
                                <ExternalLink size={14} />
                              </a>
                            )}
                          </div>
                          <blockquote>{c.quote}</blockquote>
                        </div>
                      ))}
                      {answer.paths?.length > 0 && (
                        <>
                          <h4>Relationship paths</h4>
                          {answer.paths.slice(0, 8).map((p: Row, i: number) => (
                            <div key={i} className="path-strip">
                              {p.path.join(" → ")}
                              <small>{p.relations.join(" · ")}</small>
                            </div>
                          ))}
                        </>
                      )}
                      <details className="trace">
                        <summary>
                          Inspect tool execution · {answer.trace?.length || 0}{" "}
                          calls
                        </summary>
                        {answer.trace?.map((t: Row, i: number) => (
                          <div key={i}>
                            <strong>{t.tool}</strong>
                            <span>
                              {t.rows} rows · {t.duration_ms} ms
                            </span>
                            <pre>{JSON.stringify(t.arguments, null, 2)}</pre>
                          </div>
                        ))}
                      </details>
                    </div>
                  )}
                  {!answer && !busy && (
                    <Empty
                      icon={Bot}
                      title="An agent grounded in your company"
                      description="Ask a specific question. The agent can search your sources, discover entities, and follow relationships. Every run is saved for review."
                    />
                  )}
                </section>
              </div>
            </>
          )}
          {view === "reviews" && (
            <>
              <div className="page-title">
                <div>
                  <div className="eyebrow">FROM EVIDENCE TO ACTION</div>
                  <h1>Review queue</h1>
                  <p>
                    Review agent proposals. Approved items become tasks in your
                    company graph.
                  </p>
                </div>
                <Badge
                  value={`${reviews.filter((r) => r.status === "pending").length} pending`}
                />
              </div>
              <section className="panel">
                <div className="section-head">
                  <h2>Conflict candidates</h2>
                  <Badge value={`${conflicts.length}`} />
                </div>
                <p className="fine-print">
                  The same subject and relationship names different targets in
                  different current sources. Candidates only — review the quoted
                  evidence before acting.
                </p>
                {conflicts.length ? (
                  conflicts.map((c) => (
                    <div className="conflict" key={c.subject_id + c.predicate}>
                      <strong>{c.subject}</strong> · {c.predicate}
                      {c.claims.map((cl: Row, i: number) => (
                        <div className="version-item" key={i}>
                          <span>{cl.object}</span>
                          <button className="text-button" onClick={() => openSource(cl.source_id)}>
                            {cl.source}
                          </button>
                          <small>{cl.quote}</small>
                        </div>
                      ))}
                    </div>
                  ))
                ) : (
                  <p className="subtle">No conflicting claims found across current sources.</p>
                )}
              </section>
              <section className="panel">
                <div className="section-head">
                  <h2>Tasks</h2>
                  <Badge value={`${tasks.length}`} />
                </div>
                {tasks.length ? (
                  tasks.map((t) => (
                    <div className="version-item" key={t.id}>
                      <strong>{t.title}</strong>
                      <button className="text-button" onClick={() => openSource(t.source_id)}>
                        {t.source}
                      </button>
                      <select
                        aria-label={`Status of ${t.title}`}
                        value={t.status}
                        onChange={async (e) => {
                          try {
                            await api(`${base}/tasks/${encodeURIComponent(t.id)}`, send("PATCH", { status: e.target.value }));
                            notify("Task updated");
                            await refresh();
                          } catch (err) {
                            notify((err as Error).message, true);
                          }
                        }}
                      >
                        <option value="open">Open</option>
                        <option value="in_progress">In progress</option>
                        <option value="done">Done</option>
                      </select>
                    </div>
                  ))
                ) : (
                  <p className="subtle">Approved proposals appear here as tasks.</p>
                )}
              </section>
              {reviews.length ? (
                reviews.map((r) => (
                  <section className="panel review-card" key={r.id}>
                    <div className="section-head">
                      <h2>{r.title}</h2>
                      <Badge value={r.status} />
                    </div>
                    <p className="subtle">{r.reason}</p>
                    <button
                      className="text-button"
                      onClick={() => openSource(r.source_id)}
                    >
                      <FileText size={15} />
                      Inspect source evidence
                    </button>
                    {r.status === "pending" && (
                      <div className="row review-actions">
                        <button
                          className="primary"
                          disabled={busy}
                          onClick={() =>
                            action(
                              `${base}/reviews/${r.id}`,
                              { approve: true },
                              "Task added to your graph",
                            )
                          }
                        >
                          <Check size={16} />
                          Approve & create task
                        </button>
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() =>
                            action(
                              `${base}/reviews/${r.id}`,
                              { approve: false },
                              "Proposal rejected",
                            )
                          }
                        >
                          Reject
                        </button>
                      </div>
                    )}
                  </section>
                ))
              ) : (
                <section className="panel">
                  <Empty
                    icon={ShieldCheck}
                    title="Nothing waiting for review"
                    description="When an agent finds something worth acting on, its evidence-backed proposals appear here. You decide what happens next."
                  />
                </section>
              )}
            </>
          )}
          {view === "activity" && (
            <>
              <div className="page-title">
                <div>
                  <div className="eyebrow">PIPELINE VISIBILITY</div>
                  <h1>Activity</h1>
                  <p>
                    Track ingestion, enrichment, sync progress, and recover
                    failed jobs.
                  </p>
                </div>
                <button className="secondary" onClick={refresh}>
                  <Activity size={16} />
                  Refresh
                </button>
              </div>
              <section className="panel table-panel">
                {jobs.length ? (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Job</th>
                          <th>Status</th>
                          <th>Progress</th>
                          <th>Details</th>
                          <th>Updated</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {jobs.map((j) => (
                          <tr key={j.id}>
                            <td>
                              <strong>{j.kind}</strong>
                              <small className="mono block">
                                {j.id.slice(0, 14)}
                              </small>
                            </td>
                            <td>
                              <Badge value={j.status} />
                            </td>
                            <td>
                              {j.total ? `${j.progress}/${j.total}` : "—"}
                            </td>
                            <td className="job-message">{j.message}</td>
                            <td className="subtle">{date(j.updated_at)}</td>
                            <td>
                              {j.status === "failed" && (
                                <button
                                  className="secondary small"
                                  onClick={() =>
                                    action(
                                      `${base}/jobs/${j.id}/retry`,
                                      {},
                                      "Retry queued",
                                    )
                                  }
                                >
                                  Retry
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty
                    icon={Activity}
                    title="Your pipeline is quiet"
                    description="Import a source or sync a repository to see the processing steps here."
                  />
                )}
              </section>
            </>
          )}
          {view === "admin" && user.role === "admin" && (
            <>
              <div className="page-title">
                <div>
                  <div className="eyebrow">INSTALLATION SETTINGS</div>
                  <h1>Administration</h1>
                  <p>
                    Manage integration credentials, AI models, accounts, and
                    audit history.
                  </p>
                </div>
              </div>
              <form onSubmit={saveSettings}>
                <div className="two-columns">
                  <section className="panel">
                    <div className="section-head">
                      <h2>
                        <Github size={20} /> GitHub App
                      </h2>
                      <a
                        className="text-button"
                        href="/api/connectors/github/app/register"
                      >
                        Register on GitHub <ExternalLink size={14} />
                      </a>
                    </div>
                    <p className="subtle">
                      Register through GitHub to configure credentials automatically, or enter an existing app below. Repository access is selected during installation; tokens expire after an hour and are renewed on demand.
                    </p>
                    <label>
                      Homepage URL
                      <div className="code-field">{location.origin}</div>
                    </label>
                    <label>
                      Installation setup URL
                      <div className="code-field">
                        {adminSettings.callback_url}
                      </div>
                    </label>
                    <label>
                      App ID
                      <input
                        name="github_app_id"
                        defaultValue={adminSettings.github_app_id}
                        key={adminSettings.github_app_id || "empty"}
                        placeholder="GitHub App numeric ID"
                      />
                    </label>
                    <label>
                      App slug
                      <input name="github_app_slug" defaultValue={adminSettings.github_app_slug} key={adminSettings.github_app_slug || 'slug'} placeholder="your-app-name"/>
                    </label>
                    <label>
                      Private key (PEM)
                      <textarea
                        name="github_app_private_key"
                        rows={4}
                        placeholder={
                          adminSettings.github_key_configured
                            ? "Configured · leave blank to keep"
                            : "-----BEGIN RSA PRIVATE KEY-----"
                        }
                      />
                    </label>
                    <p className="fine-print">
                      Secrets are encrypted in the local control database and
                      never returned to the browser.
                    </p>
                  </section>
                  <section className="panel">
                    <div className="section-head">
                      <h2>
                        <Sparkles size={20} /> OpenRouter
                      </h2>
                      <Badge
                        value={
                          adminSettings.openrouter_key_configured
                            ? "configured"
                            : "needs_key"
                        }
                      />
                    </div>
                    <p className="subtle">
                      Agents and enrichment use free models only. Unavailable
                      models fall back to graph evidence.
                    </p>
                    <label>
                      Free model ID
                      <input
                        name="openrouter_model"
                        defaultValue={adminSettings.openrouter_model}
                        key={adminSettings.openrouter_model || "model"}
                      />
                    </label>
                    <label>
                      API key
                      <input
                        name="openrouter_api_key"
                        type="password"
                        autoComplete="new-password"
                        placeholder={
                          adminSettings.openrouter_key_configured
                            ? "Configured · leave blank to keep"
                            : "OpenRouter API key"
                        }
                      />
                    </label>
                    <div className="notice">
                      <CircleHelp size={18} />
                      <p>
                        AI enrichment sends selected source passages to
                        OpenRouter. Enrichment is a separate action; uploads and
                        GitHub sync preserve your raw content without calling a
                        model.
                      </p>
                    </div>
                    <button className="primary">
                      <Check size={16} />
                      Save integration settings
                    </button>
                  </section>
                </div>
              </form>
              <section className="panel table-panel">
                <div className="table-toolbar">
                  <h2>Accounts</h2>
                  <button
                    className="secondary small"
                    onClick={() => setModal("user")}
                  >
                    <Plus size={15} />
                    Add account
                  </button>
                </div>
                <table>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Email</th>
                      <th>Role</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id}>
                        <td>{u.name}</td>
                        <td>{u.email}</td>
                        <td>
                          <Badge value={u.role} />
                        </td>
                        <td>{date(u.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
              <section className="panel">
                <div className="section-head">
                  <h2>Audit history</h2>
                  <ShieldCheck size={18} />
                </div>
                {audit.length ? (
                  audit.slice(0, 20).map((a) => (
                    <div className="audit-item" key={a.id}>
                      <span className="mono">{a.event}</span>
                      <small>{date(a.created_at)}</small>
                    </div>
                  ))
                ) : (
                  <p className="quiet">
                    Configuration changes and reviewed actions will appear here.
                  </p>
                )}
              </section>
            </>
          )}
        </main>
      </div>
      {toast && (
        <div className={"toast " + (toast.error ? "error" : "")} role="status">
          {toast.error ? <AlertCircle size={18} /> : <CheckCircle2 size={18} />}
          <span>{toast.text}</span>
          <button onClick={() => setToast(null)} aria-label="Dismiss">
            <X size={15} />
          </button>
        </div>
      )}
      {modal && (
        <Modal
          title={
            {
              workspace: "Create a workspace",
              text: "Add a text source",
              agent: "Create an agent",
              user: "Add an account",
            }[modal] || ""
          }
          onClose={() => setModal("")}
        >
          <form onSubmit={submitModal}>
            {modal === "workspace" && (
              <label>
                Workspace name
                <input name="name" placeholder="Acme company" required />
              </label>
            )}
            {modal === "text" && (
              <>
                <label>
                  Source title
                  <input
                    name="title"
                    placeholder="Product roadmap.md"
                    required
                  />
                </label>
                <label>
                  Content
                  <textarea
                    name="content"
                    rows={12}
                    placeholder="Paste your document, notes, or meeting transcript…"
                    required
                  />
                </label>
              </>
            )}
            {modal === "agent" && (
              <>
                <label>
                  Agent name
                  <input name="name" placeholder="Product analyst" required />
                </label>
                <label>
                  Instructions
                  <textarea
                    name="instructions"
                    rows={5}
                    placeholder="Describe what this agent should investigate, and how it should use evidence…"
                    required
                  />
                </label>
              </>
            )}
            {modal === "user" && (
              <>
                <label>
                  Name
                  <input name="name" required />
                </label>
                <label>
                  Email
                  <input name="email" type="email" required />
                </label>
                <label>
                  Initial password
                  <input
                    name="password"
                    type="password"
                    minLength={10}
                    required
                    autoComplete="new-password"
                  />
                </label>
                <p className="fine-print">
                  Creates a member account with its own isolated workspace.
                </p>
              </>
            )}
            <div className="modal-actions">
              <button
                type="button"
                className="secondary"
                onClick={() => setModal("")}
              >
                Cancel
              </button>
              <button className="primary" disabled={busy}>
                {busy ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <Plus size={16} />
                )}
                Save
              </button>
            </div>
          </form>
        </Modal>
      )}
      {detail && (
        <div
          className="drawer-shade"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setDetail(null);
          }}
        >
          <aside className="source-drawer">
            <div className="section-head">
              <div className="eyebrow">SOURCE INSPECTOR</div>
              <button
                className="icon-button"
                onClick={() => setDetail(null)}
                aria-label="Close source"
              >
                <X size={20} />
              </button>
            </div>
            <h2>{detail.title}</h2>
            <div className="row wrap">
              <Badge value={detail.kind} />
              <Badge value={detail.status} />
              <span className="subtle">Version {detail.version}</span>
            </div>
            {detail.uri && /^https:\/\//.test(detail.uri) && (
              <a
                className="text-button"
                href={detail.uri}
                target="_blank"
                rel="noreferrer"
              >
                Open original <ExternalLink size={14} />
              </a>
            )}
            <div className="source-actions">
              <button
                className="primary small"
                onClick={() =>
                  action(
                    `${base}/sources/${detail.id}/enrich?max_chunks=6`,
                    {},
                    "AI enrichment queued for the first 6 passages",
                  )
                }
              >
                <Sparkles size={15} />
                Enrich with AI
              </button>
              <button
                className="secondary small"
                onClick={() => {
                  setDetail(null);
                  setView("graph");
                }}
              >
                <Network size={15} />
                Explore graph
              </button>
            </div>
            <p className="fine-print">
              Enrichment sends up to 6 source passages to the configured free
              OpenRouter model. See Activity for accepted relations and partial
              coverage.
            </p>
            <h3>Source content</h3>
            {detail.editing ? <><textarea aria-label="Edit source content" rows={16} value={detail.content} onChange={e => setDetail({...detail,content:e.target.value})}/><button className="primary small" disabled={busy} onClick={async()=>{const result=await action(base+'/sources/text',{title:detail.title,content:detail.content},'New version queued');if(result)setDetail(null)}}>Save new version</button></> : <><pre className="document-content">{detail.content}</pre>{detail.kind==='upload' && /\.(md|txt|csv|json|rst|log|yaml|yml)$/i.test(detail.title) && <button className="secondary small" onClick={()=>setDetail({...detail,editing:true})}>Edit content</button>}</>}
            <h3>Version history</h3>
            {detail.history?.map((v: Row) => (
              <div className="version-item" key={v.hash}>
                <span className="mono">{v.hash.slice(0, 12)}</span>
                <small>{date(v.recorded_at)}</small>
                <Badge value={v.active ? "current" : "historical"} />
                {!v.active && (
                  <button
                    className="text-button"
                    onClick={async () => {
                      try {
                        setDiff({ ...(await api(`${base}/sources/${detail.id}/diff?before_hash=${v.hash}`)), changes: await api(`${base}/sources/${detail.id}/changes`) });
                      } catch (e) {
                        notify((e as Error).message, true);
                      }
                    }}
                  >
                    Compare with current
                  </button>
                )}
              </div>
            ))}
            {diff && (
              <div className="diff-view">
                <p className="fine-print">
                  {diff.before_hash.slice(0, 12)} → {diff.after_hash.slice(0, 12)}:{" "}
                  +{diff.added} / −{diff.removed} lines
                  {diff.truncated ? " (truncated)" : ""}
                </p>
                <pre className="document-content">
                  {diff.lines.length ? diff.lines.map((line: string, i: number) => (
                    <div key={i} className={line.startsWith("+") && !line.startsWith("+++") ? "diff-add" : line.startsWith("-") && !line.startsWith("---") ? "diff-del" : ""}>{line}</div>
                  )) : "No text differences."}
                </pre>
                {diff.changes && (diff.changes.added.length > 0 || diff.changes.removed.length > 0) && (
                  <div>
                    <h4>Relationship changes (all earlier versions vs current)</h4>
                    {diff.changes.removed.map((r: Row, i: number) => (
                      <div className="diff-del" key={"r" + i}>− {r.subject} {r.predicate} {r.object}</div>
                    ))}
                    {diff.changes.added.map((r: Row, i: number) => (
                      <div className="diff-add" key={"a" + i}>+ {r.subject} {r.predicate} {r.object}</div>
                    ))}
                  </div>
                )}
                {diff.related_entities?.length > 0 && (
                  <p className="fine-print">
                    Entities mentioned in this source: {diff.related_entities.map((e: Row) => e.name).join(", ")}
                  </p>
                )}
              </div>
            )}
            <details>
              <summary>Metadata</summary>
              <pre>
                {JSON.stringify(JSON.parse(detail.metadata || "{}"), null, 2)}
              </pre>
            </details>
            {detail.status !== "archived" && (
              <button
                className="text-button danger"
                onClick={async () => {
                  await action(
                    `${base}/sources/${detail.id}/archive`,
                    {},
                    "Source archived; history retained",
                  );
                  setDetail(null);
                }}
              >
                Archive source
              </button>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
