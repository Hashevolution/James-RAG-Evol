# Promo screenshots — visual assets for external channels

These six screenshots are reusable across every promotional channel
(README, dev.to articles, X/Twitter, LinkedIn, GeekNews, Reddit,
Hashnode). They are captured from the running JAMES instance and live
under MIT alongside the rest of the repository — feel free to use
them for any open-source RAG / Graph-RAG / Gemma 4 write-up that
references PROJECT JAMES.

## File index

| File | Captured screen | Strongest signal | Primary placement |
|---|---|---|---|
| `01-memory-status.jpg` | `/admin/memory` — preferences / patterns / goals / card-turns / session-summary counters | Persistent memory system is real (1946 prefs, 224 card-turns, 59 session summaries) | dev.to "Trust signals" section; X follow-up tweet on data substrate |
| `02-intent-engineering.jpg` | Entity detail panel for `Intent Engineering` over the 3D graph background | Typed ontology relations rendered as first-class entities | dev.to "Architecture" supporting image; Reddit secondary |
| `03-chat-graph-paths.jpg` | Chat UI showing a Korean response with `그래프 경로 47개 보기` (47 traversed graph paths) | Graph-RAG is doing real work — paths surfaced per response | dev.to "Demo" section primary image; Reddit / Show HN body |
| `04-personality-radar.jpg` | `/admin/personality` — 11-trait personality radar with character summary | The Personality 11 traits differentiator visualised | dev.to intro article §"Personality system"; LinkedIn follow-up |
| `05-knowledge-tracker.jpg` | `/admin/knowledge` — Self-evolution 80%, Agent Capability 20%, per-domain LV cards (Business 14, Science/AI 17, General 25, etc.) | Self-evolution scaffold accumulating real per-domain learning | dev.to "Self-evolution" section; LinkedIn / X follow-up on growth |
| `06-3d-graph.jpg` | `/admin/graph` — 3D ontology graph (Three.js, force-directed) centred on `Context Engineering` | Single highest-impact visual; "real product" signal in under 1 s | README hero; dev.to cover (intro article); X first-tweet attachment; GeekNews body image |

## Naming and ordering

Files are numbered `01–06` so they sort in a consistent narrative arc
(memory → ontology → response → personality → learning → graph). The
order is the recommended walkthrough order if a writer wants to chain
them in a single article or thread.

## License + usage

MIT (inherits from repo root `LICENSE`). Attribution appreciated but
not required. If you publish a write-up that uses one or more of these
images, a link back to `https://github.com/Hashevolution/James-RAG-Evol`
is the polite hat-tip.

## How to refresh

Each image is captured from the running app at the routes noted
above. To re-capture after a UI change:

1. `python server_llmwiki.py`
2. Navigate to the listed route
3. Capture with platform tool (ShareX / macOS screenshot / Flameshot)
4. Save with the same filename so all downstream channel references
   stay valid
