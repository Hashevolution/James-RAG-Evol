"""α-5 external benchmark adapters (MultiHop-RAG, Tang & Yang 2024).

This package downloads, builds, and feeds the MultiHop-RAG dataset
into JAMES via the workspace abstraction (config.py:74,
`core/plugins/workspace.py::get_workspace_root`). All artifacts land
under `workspaces/hotpot_eval/`; production state is untouched.

Plan: `~/.claude/plans/quiet-hugging-iverson.md`.
"""
