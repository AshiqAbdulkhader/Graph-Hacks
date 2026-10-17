# DecisionTrail product delivery plan

Updated: October 17, 2026. The real-product scope below supersedes the initial Atlas-only prototype. The fixture remains an isolated regression test; the product starts with an empty workspace and operates on user-ingested data.

## Current checkpoint

The local product works with real data and a connected GitHub App. The full plan is **not complete**. A checked item means its implementation exists; the evidence below identifies what has actually been exercised. File-format support, for example, does not mean every format has received a separate browser test.

| Area | Current state | Remaining work |
| --- | --- | --- |
| Local platform and accounts | Implemented; authorization/isolation tests pass | Hosted authentication and operations are deferred |
| Ingestion and provenance | Uploads, structured graphs, versions, archive, jobs and optional enrichment implemented | Broader format/restart/retry checks and scale evaluation |
| GitHub App | User created and installed it; live repository sync verified | Verify repository pagination; optional automatic sync and deletion reconciliation |
| Graph and administration | Actual FalkorDB nodes/edges, browser exploration and Cypher verified | Complete new analysis controls and usability checks |
| Agents and reviewed actions | Retrieval, free-model answer, citations, traces and reviewed Task creation verified | Generic decision comparison/contradictions and broader counterfactual analysis |
| New analysis/task endpoints | Backend implementation exists | UI integration and targeted tests; see Phase 5A |
| Packaging and submission | Setup/docs/screenshot exist; current build and tests pass | Recorded demo, final review, publishing and submission |
| Hosting | Deferred by user | Choose hosts, migrate database and verify deployment later |

### Verification evidence

- Latest checkpoint: `python -m pytest -q` using `.venv` → **39 passed** (adds paging, end-to-end scenario, diff, impact, task-lifecycle, conflict, format/parser-error and job-recovery tests); `npm run build` in `frontend` → **passed** on October 17. A JSX syntax error in the repository pagination button was corrected before this build.
- Product tests cover uploads, source versioning/deduplication, archive/reimport, graph write rejection, workspace isolation, secret redaction, retrieval, LangChain fake-model planning and approved task persistence. GitHub App tests cover state, JWTs, temporary tokens and the nullable webhook-secret regression. The total also includes the retained Atlas fixture tests; it is not 15 end-to-end product scenarios.
- Live GitHub App sync of `FalkorDB/falkordb`: **7 sources, 51 nodes, 53 relationships before enrichment**. These are observations from that bounded import, not fixed application totals.
- Live OpenRouter free-model agent run: **connected** model status, **8 cited evidence passages**, **2 tool calls**. Retrieval fallback was checked separately.
- Live opt-in enrichment: **1 of 1 selected passages processed**, **3 evidenced relationships accepted**. This verifies a bounded request, not extraction coverage of the entire repository.
- Browser checks exercised local CLI sign-in, GitHub App registration/installation, repository listing, actual graph rendering and a query-rendered subgraph. Screenshot: `docs/screenshots/graph-explorer.png`.
- The version-diff, dependency-impact and task-status endpoints now have dedicated tests. Their UI controls (version diff, impact preview, task status) were exercised in the browser on a scratch instance with synthetic data.

## Goal

Build a usable company intelligence workspace: ingest documents and structured data, connect a GitHub App, explore and query the actual FalkorDB graph, configure agents, inspect source evidence, and review proposed work. Target Graph Hacks Track 1 (agents that act on connected data) and Track 3 (company brain). The event deadline is October 18, 11:59 PM IST.

## Decisions already made

- Python 3.11 virtual environment, FastAPI backend, React/TypeScript frontend.
- FalkorDB in Docker with persistent storage. Hosted database deployment is explicitly deferred by the user; credentials and TLS settings are configurable.
- OpenRouter free models only. LangChain chat-model interface and FakeListChatModel tests. The graph remains usable when a model fails.
- GitHub App installation authentication with read-only contents, issues, pull requests, and metadata. Short-lived installation tokens are minted on demand. GitHub CLI is a local sign-in option, not the data connector credential.
- No default seeded company in the product. Users create workspaces and ingest their own data.

## Phase 1 — Local platform foundation

Status: implemented and verified locally.

- [x] `.venv`, Python dependencies, Docker Compose and pinned FalkorDB image.
- [x] Persistent local control database for accounts, workspaces, sources, jobs, connections, agents, runs, reviews, and audit events.
- [x] Password accounts and local GitHub CLI sign-in; HttpOnly session cookies.
- [x] Workspace authorization and isolated FalkorDB graph per workspace.
- [x] Administrative configuration with encrypted connector secrets and key redaction.
- Gate: authenticated users see only authorized workspace data; admin endpoints reject members.

## Phase 2 — Arbitrary supported data ingestion

Status: implemented; document/structured ingestion and versioning verified.

- [x] File upload and pasted text: MD, TXT, CSV, JSON, PDF, DOCX, RST, LOG, YAML/YML.
- [x] Explicit limits: 10 MB per upload, 500,000 extracted characters, 300 PDF pages. Scanned PDFs require OCR before import.
- [x] Durable queued/running/completed/failed jobs; visible progress and retries; unfinished jobs resume on process restart.
- [x] Stable source IDs, content hashes, active/historical document versions, source passages, and re-upload deduplication.
- [x] CSV/JSON records and declared JSON nodes/edges become entities and graph relationships.
- [x] Optional AI enrichment with exact-source-quote validation and a visible passage budget (default 6; API maximum 30).
- [x] Source inspector, history, text editing, and archive with retained evidence.
- [x] Each advertised format parses a generated representative file; tested errors: blank/scanned PDF, empty text, invalid JSON, corrupt PDF/DOCX (clear message), unsupported type. Browser upload of each format not repeated.
- [x] Tested: a queued job resumes after app restart; a failed job shows its message and can be retried to success.
- Gate: upload unrelated user data and query its nodes, edges, and current/historical provenance without changing code.

## Phase 3 — GitHub App connector

Status: installed and live sync verified.

- [x] Manifest registration with backend code exchange and encrypted RSA private key storage.
- [x] Session-bound setup state and selected-repository installation flow.
- [x] RS256 app JWTs and on-demand installation tokens; no installation token persisted.
- [x] Repository browser and configurable import of documentation, issues, pull requests, authors, and assignees.
- [x] Manual incremental re-sync with source version retention and explicit item limits.
- [x] User completed real GitHub App creation and installation.
- [x] Live public `FalkorDB/falkordb` import: 7 sources, 51 nodes, 53 relationships before optional enrichment; graph query and retrieval succeeded.
- [x] Repository paging tested against a mocked GitHub API (50-per-page requests, installation payload unwrapped, 107 repositories across 3 pages, page clamped). Browser check of the Load-more button against a live installation with more than 50 repositories is still outstanding.
- [ ] Optional later: automatic webhook/scheduled sync, installation lifecycle events, deleted-source reconciliation, and multi-installation management.
- Gate: live repository access and ingestion use installation authentication; approved repository access remains controlled in GitHub.

## Phase 4 — Graph workspace and administration

Status: implemented; browser and query rendering verified.

- [x] Product navigation: Overview, Sources, Connectors, Graph explorer, Agents, Review queue, Activity, Administration.
- [x] Real Cytoscape graph with zoom, pan, fit, label/search filters, node inspector, neighbor expansion, and node pagination.
- [x] Read-only Cypher console; returned graph objects render a subgraph and raw query rows remain inspectable.
- [x] Database-enforced read-only command, 2 second query timeout, capped API results.
- [x] Account administration, integration settings, and audit history.
- Gate: query an actual ingested source and inspect its relationships in the browser.

## Phase 5 — Agents and reviewed actions

Status: core agent/review flow implemented; deterministic, LangChain fake-model and live free-model retrieval verified. Advanced analysis remains incomplete.

- [x] Editable agent definitions and instructions; researcher, impact analyst, and knowledge curator defaults.
- [x] Bounded model-selected tool catalogue: source search, entity discovery, relationship expansion, source history.
- [x] Graph retrieval fallback when a free model is unavailable or produces invalid output.
- [x] Source citations, recorded relationship paths, tool trace, and persistent run history.
- [x] Evidence-backed proposed review tasks; approving creates a Task node linked to its source, with idempotent review handling.
- [x] Live free OpenRouter answer with evidence citations; bounded live enrichment also completed successfully.
- [x] Generic relationship-change comparison per source and conflict candidates (same subject + predicate, different targets across current sources, with quotes). Heuristic: candidates for review, not proof; text-only contradictions without extracted relationships are not detected. UI panel and relationship changes browser-verified on a scratch instance; relationship changes compare all earlier versions with the current one, not a selected version.
- [ ] Add counterfactual analysis over arbitrary user-selected entities once the product core is stable.
- Gate: a question over ingested data yields real passages/paths; a validated proposal creates a graph task only after review.

## Phase 5A — Finish partially implemented analysis and task features

Status: backend code exists; these features are not complete product flows.

- [x] Source-version text reconstruction and comparison API with bounded unified diff, line-change counts and related entity IDs.
- [x] Source-history "Compare with current" control and coloured diff in the source inspector (browser-verified on a scratch instance).
- [x] Tested: historical reconstruction across overlapping passages, line counts, unknown-hash rejection, cross-workspace 404.
- [x] Bounded dependency-impact traversal API and agent tool; simulation reports that it does not mutate graph state.
- [x] "Preview impact" in the graph node inspector shows assumption, hops and paths (browser-verified on a scratch instance).
- [x] Tested: direction, predicate filter, depth limit, no graph mutation.
- [x] Task listing and status-update endpoints with audit events.
- [x] Task list with status selector in the Review queue (browser-verified on a scratch instance); persistence, validation and cross-workspace rejection tested.
- [x] End-to-end scenario test on newly ingested data (source change → diff → impacted entities → agent evidence from the current version only → reviewed task → status update). The agent step uses a LangChain fake model; a live-model run of this scenario has not been done.
- Gate: all three features are usable from the product, backed by targeted tests and demonstrated on user-ingested data. Dependency traversal alone does not satisfy generic contradiction detection or broad counterfactual reasoning.

## Phase 6 — Quality and packaging

- [x] Python compilation, meaningful pytest coverage, production TypeScript/frontend build.
- [x] Tests cover real uploads, versioning, graph query writes rejected, account isolation, secret redaction, source retrieval, LangChain planning, review task persistence, app JWT/state/token behavior, and the original temporal fixture.
- [x] Browser check of CLI sign-in, GitHub App registration/installation, repository list, graph rendering, and query-rendered subgraph.
- [x] Verify live free-model response and bounded enrichment; record actual outcomes in this checkpoint.
- [x] Document current product setup, architecture, environment template, data formats and limits; README includes the live graph screenshot and verification notes.
- [x] Documentation updated for diff, impact, conflict candidates and tasks (README, architecture).
- [ ] Run final browser verification of upload → graph query → live agent → review → task lifecycle, with failures and partial coverage visible.
- [ ] Record a demo video covering first source → connector → graph → agent → reviewed task. A screenshot is not a video.
- [x] Secret/working-tree review on October 17: tracked files and full history contain no `.env`, `.data`, keys or database files; pattern scan for API keys/private keys found none (one UI placeholder string). Repeat immediately before the public release.

## Phase 7 — Hosted delivery and submission

Await user decisions at the point required; local work continues independently.

- [ ] Hosted FalkorDB target and application host (user requested this later).
- [ ] HTTPS, hosted authentication, secure cookies, and deployment origin configuration before exposing the service publicly.
- [ ] Public repository publishing and final submission under both tracks.
- [ ] README demo/deployment links, graph model and queries, limitations, evaluation evidence, and AI-assistant disclosure.
- [ ] User confirms registration and completes final event submission when the artifact is ready.

## Next execution order

1. Finish Phase 5A UI controls and targeted tests for the existing backend additions.
2. Implement generic evidence-backed decision comparison/contradiction detection and define/test the remaining counterfactual behavior over arbitrary data.
3. Close ingestion recovery/format checks and repository pagination verification; demonstrate the complete change-to-task scenario.
4. Refresh docs, run the final browser flow and secret/working-tree review, then record the demo video.
5. Prepare the public repository and both-track submission materials. Confirm event requirements against the official rules before submitting.
6. When the user is ready for hosting, select deployment targets, migrate to hosted FalkorDB, configure public-service authentication/settings and verify the deployed flow.

Automatic webhook/scheduled sync, deletion reconciliation and multi-installation management remain optional follow-ups in this plan. Hosting remains explicitly deferred; neither status should be mistaken for a completed feature.

## Scope guardrails

The local product is functional; it is not yet a claim of production SaaS readiness. Automatic sync, full repository mirroring/deletion reconciliation, OCR, large-scale retrieval indexing, multi-installation tenancy, and hosted authentication remain explicit follow-ups. Current GitHub imports are bounded and report the configured limit. AI extraction is opt-in and reports partial coverage. Only permitted/public/synthetic sources should be used for the hackathon submission in accordance with the event rules.

## References

- [Hackathon rules](https://www.wemakedevs.org/hackathons/falkordb/rules)
- [GitHub App manifest registration](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest)
- [GitHub installation authentication](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation)
- [Architecture](architecture.md)
