# RAB → Hugging Face — upload checklist

> **Outward-facing action.** Publishing to HF pushes content to a public
> service that may cache or index it even if later deleted. Complete this
> checklist deliberately. The script defaults to a **dry run**; nothing
> is pushed without `--execute`.

Two artifacts:
- **Dataset** — `eval/rab/hf_dataset/` → `datasets/<owner>/rab-replayable-audit-benchmark`
- **Space** — `eval/rab/hf_space/` → `spaces/<owner>/rab-demo`

---

## 0. Decisions to lock first (operator)

- [ ] **Owner / repo ids.** Default assumes owner `JamesLabs`
      (the authenticated HF account). If the org or name differs, update
      the `--dataset-repo` / `--space-repo` flags **and** the
      `JamesLabs/...` references in both `README.md` files.
- [ ] **License = CC-BY-4.0** for the fixtures/artifacts (matches the
      RAB Zenodo pre-registration). App + loader code stays MIT. Confirm
      this is still the intended split (`docs/LICENSE_PLAN.md`).
- [ ] **Trademark.** "JAMES" wordmark is **not yet registered**
      (`LICENSE_PLAN.md §6`). Publishing a public repo/Space under the
      name is fine under MIT/CC-BY but exposes an unregistered mark —
      acknowledge before proceeding.
- [ ] **Public vs. private first.** Recommended: upload `--private`,
      eyeball on the Hub, then flip to public from repo settings.

## 1. Pre-flight (local)

- [ ] On a clean, pushed branch (`git status` clean).
- [ ] Validate artifacts: `python eval/rab/hf_publish/publish_to_hf.py --what both`
      → both folders report `[ok]`.
- [ ] (If `datasets` installed) loader smoke test:
      `python -c "from datasets import load_dataset; \
      d=load_dataset('eval/rab/hf_dataset','S1',split='test',trust_remote_code=True); \
      print(len(d), d[0])"` → 40 rows.
- [ ] (If `gradio` installed) Space smoke test: `cd eval/rab/hf_space && python app.py`
      → loads at localhost, all four tabs render.
- [ ] Confirm bundled data matches the current spec: `scenario_sha` /
      `log_sha` in `hf_space/data/james-S1.result.json` still correspond
      to the committed scenario + log (re-copy from `reports/rab/` if a
      newer measurement exists).

## 2. Auth

- [ ] Create a **write** token at https://huggingface.co/settings/tokens
      (role: Write; or fine-grained scoped to the two repos).
- [ ] `export HF_TOKEN=hf_...`  (or `hf auth login`). Never commit it.

## 3. Upload

- [ ] Dry run again with final repo ids:
      `python eval/rab/hf_publish/publish_to_hf.py --what both \
      --dataset-repo <owner>/rab-replayable-audit-benchmark \
      --space-repo <owner>/rab-demo`
- [ ] Execute (private first):
      `HF_TOKEN=... python eval/rab/hf_publish/publish_to_hf.py --what both --execute --private \
      --dataset-repo <owner>/... --space-repo <owner>/...`

## 4. Post-upload verification

- [ ] Dataset page renders the card; the dataset viewer shows S1/S2 configs.
- [ ] `load_dataset("<owner>/rab-replayable-audit-benchmark","S1",
      split="test", trust_remote_code=True)` → 40 rows, correct schema.
- [ ] Space builds (check the build logs) and the four tabs work; the
      gap-structure table shows baseline0 → JAMES.
- [ ] "does NOT certify compliance" disclaimer is visible on both pages.
- [ ] Flip to public (if the dry private upload looked right).

## 5. Cross-linking (optional but recommended)

- [ ] Dataset card ↔ Space ↔ Zenodo DOI (`10.5281/zenodo.20625533`) all
      link to each other and to the GitHub source.
- [ ] Add the HF links to `reports/promo-assets/launch-tracker.md` so the
      `LICENSE_PLAN.md` T1 adoption-signal monitoring can pick them up.

## Rollback

`HfApi().delete_repo(repo_id, repo_type=...)` removes a repo, but assume
anything pushed publicly may already be cached/indexed. This is why
step 0 recommends a private-first upload.
