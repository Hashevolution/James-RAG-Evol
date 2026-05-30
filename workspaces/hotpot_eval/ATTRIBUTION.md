# Dataset Attribution — MultiHop-RAG

**Source**: HuggingFace `yixuantt/MultiHopRAG`
**License**: CC-BY-4.0
**Citation**:

> Tang, Yixuan and Yang, Yi. "MultiHop-RAG: Benchmarking Retrieval-Augmented Generation for Multi-Hop Queries." Findings of EMNLP, 2024. https://huggingface.co/datasets/yixuantt/MultiHopRAG

## Use within JAMES

The MultiHop-RAG corpus (609 news articles, predominantly
English-language news from 2023-09 to 2023-12) is ingested into
this workspace's `wiki/` via the standard JAMES pipeline
(`scripts/ingest_pipeline.py`). The 2,556 query set is converted
into step7-format fixture by `scripts/hotpot/build_fixture.py`
and consumed by `scripts/qvt_ablation_matrix.py` for the α-5
ablation matrix.

Per CC-BY-4.0, this attribution file MUST stay alongside any
redistributed corpus snapshot. Production wiki (project root
`./wiki/`) is unaffected by this benchmark workspace — see
`workspaces/hotpot_eval/README.md`.
