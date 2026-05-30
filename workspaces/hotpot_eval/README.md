# α-5 Benchmark Workspace — MultiHop-RAG

External-benchmark workspace for the α-5 ablation matrix. Completely
isolated from the production wiki (`./wiki/`, `./chroma_db_bge_m3/`).

## Activation

```bash
export JAMES_WORKSPACE=./workspaces/hotpot_eval
source workspaces/hotpot_eval/.env
```

Then run any JAMES script. All data directories (`WIKI_DIR`,
`CHROMA_DIR`, `RAW_DIR`, `UPLOAD_DIR`) resolve under this workspace via
`core/plugins/workspace.py::get_workspace_root()`. The production
workspace at the repo root is untouched.

## Restore production

```bash
unset JAMES_WORKSPACE
```

That's it. Production state is byte-identical because the workspace
abstraction (config.py:74) returns the project root when the env is
unset.

## Layout

```
workspaces/hotpot_eval/
├── .env                          # think=OFF + bge-m3 (this workspace's defaults)
├── README.md                     # this file
├── ATTRIBUTION.md                # MultiHop-RAG license / attribution (Step 2)
├── raw/                          # MultiHop-RAG corpus (609 articles after Step 2)
├── uploads/                      # uploaded-doc staging (mirrors prod)
├── wiki/
│   ├── entity/
│   │   ├── prod/                 # populated by Step 7 (ingest pipeline)
│   │   └── test/
│   └── media/
├── chroma_db_bge_m3/             # populated by Step 7
├── eval/
│   ├── multihop_rag_queries.json # fixture (Step 3)
│   └── qvt/
│       └── baseline_<sha>.json   # Step 8 output
└── reports/research-runs/
    └── qvt-ablation-cells-hotpot/ # Step 9 per-cell JSONs
```

## Source of truth

- Plan: `~/.claude/plans/quiet-hugging-iverson.md` (post-#614 reset)
- Prior cycle: PR #608 (A3), #609 (A2), #611 (A3 v2), #612 (α-5 prep),
  #613 (α-5 prereq), #614 (step7 v7 — now internal canary only)
- Dataset: Tang & Yang 2024 "MultiHop-RAG" (EMNLP 2024). 2,556 multi-hop
  QA over 609 news articles. CC-BY-4.0.

## Restore

Git tag `v0.4-pre-hotpot` marks the commit before this workspace was
created. Roll back with `git reset --hard v0.4-pre-hotpot` if needed
(but the workspace itself is removable just by `rm -rf workspaces/
hotpot_eval/` since it lives entirely inside this directory).
