"""RAB — Replayable-Audit Benchmark — Hugging Face loading script.

Exposes the published RAB scenario fixtures as a `datasets.Dataset`,
one row per driver op, preserving op order. The benchmark semantics
depend on order, so each scenario is a single `test` split and must not
be shuffled.

This script only reads the JSON fixtures bundled next to it under
`scenarios/`. No network access, no code execution beyond JSON parsing.
`trust_remote_code=True` is required by `datasets` for any loading
script; it does not grant this script extra capability.

The driver + deterministic scorer that turn these fixtures into AC / RF
/ PC scores live in the source repository, not here:
https://github.com/Hashevolution/James-RAG-Evol  (eval/rab/).
"""

import json
import os

import datasets

_DESCRIPTION = (
    "RAB — Replayable-Audit Benchmark. Deterministic, LLM-judge-free "
    "scenario fixtures for measuring the auditability (not answer "
    "quality) of RAG / agent systems: Audit Completeness (AC), Replay "
    "Fidelity (RF), Provenance Coverage (PC). Anchored on EU AI Act "
    "Articles 10/12/19. RAB does not certify regulatory compliance."
)

_HOMEPAGE = "https://github.com/Hashevolution/James-RAG-Evol"
_LICENSE = "cc-by-4.0"
_CITATION = """\
@software{rab_replayable_audit_benchmark,
  title        = {RAB --- Replayable-Audit Benchmark for RAG / agent systems},
  author       = {Seo, Ji Won},
  organization = {JAMES (Hashevolution)},
  year         = {2026},
  version      = {SPEC v0.1.1},
  doi          = {10.5281/zenodo.20625533},
  url          = {https://github.com/Hashevolution/James-RAG-Evol}
}
"""

# Scenario config name -> bundled fixture filename.
_SCENARIO_FILES = {
    "S1": "s1_lifecycle_small.json",
    "S2": "s2_lifecycle_large.json",
}

# args sub-keys promoted to flat columns for convenience. The lossless
# source of truth is always `args_json`.
_FLAT_ARG_KEYS = ("doc_id", "old_doc_id", "title", "text")


class RabConfig(datasets.BuilderConfig):
    def __init__(self, scenario_file, **kwargs):
        super().__init__(**kwargs)
        self.scenario_file = scenario_file


class Rab(datasets.GeneratorBasedBuilder):
    """Replayable-Audit Benchmark scenario fixtures."""

    VERSION = datasets.Version("0.1.1")

    BUILDER_CONFIGS = [
        RabConfig(
            name="S1",
            version=datasets.Version("0.1.1"),
            description="lifecycle-small — 40 deterministic ops, K=10 checkpoints",
            scenario_file=_SCENARIO_FILES["S1"],
        ),
        RabConfig(
            name="S2",
            version=datasets.Version("0.1.1"),
            description="lifecycle-large — 400 deterministic ops, K=40 checkpoints",
            scenario_file=_SCENARIO_FILES["S2"],
        ),
    ]
    DEFAULT_CONFIG_NAME = "S1"

    def _info(self):
        features = datasets.Features(
            {
                "scenario": datasets.Value("string"),
                "spec": datasets.Value("string"),
                "op_id": datasets.Value("string"),
                "op": datasets.Value("string"),
                "checkpoint": datasets.Value("bool"),
                "doc_id": datasets.Value("string"),
                "old_doc_id": datasets.Value("string"),
                "title": datasets.Value("string"),
                "text": datasets.Value("string"),
                "query": datasets.Value("string"),
                "args_json": datasets.Value("string"),
            }
        )
        return datasets.DatasetInfo(
            description=_DESCRIPTION,
            features=features,
            homepage=_HOMEPAGE,
            license=_LICENSE,
            citation=_CITATION,
        )

    def _split_generators(self, dl_manager):
        # Fixtures are bundled with the script; resolve relative to it so
        # the dataset works both on the Hub and from a local checkout.
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, "scenarios", self.config.scenario_file)
        return [
            datasets.SplitGenerator(
                name=datasets.Split.TEST,
                gen_kwargs={"filepath": path},
            )
        ]

    def _generate_examples(self, filepath):
        with open(filepath, encoding="utf-8") as fh:
            scenario = json.load(fh)

        scenario_id = scenario.get("scenario", "")
        spec = scenario.get("spec", "")

        for idx, op in enumerate(scenario["ops"]):
            args = op.get("args", {}) or {}
            row = {
                "scenario": scenario_id,
                "spec": spec,
                "op_id": op.get("op_id", ""),
                "op": op.get("op", ""),
                "checkpoint": bool(op.get("checkpoint", False)),
                "query": args.get("q", ""),
                "args_json": json.dumps(args, ensure_ascii=False, sort_keys=True),
            }
            for key in _FLAT_ARG_KEYS:
                row[key] = args.get(key, "")
            # `op_id` is unique within a scenario; use it as the example key.
            yield op.get("op_id", idx), row
