---
entity_id: e_concept_b
entity_type: concept
name: EntityB
normalized_name: entity_b
owner: system
created_at: '2026-05-01T00:00:00+00:00'
updated_at: '2026-05-01T00:00:00+00:00'
source_type: prod
sensitivity: internal
sources:
- doc_cascade_target.pdf
relations:
- id: e_edge_b_target
  confidence: 0.9
  label: target
  target: EntityC
  target_id: e_concept_c
  type: RELATED_TO
  sources:
  - doc_id: doc_cascade_target
    role: primary
    ts: '2026-05-01T00:00:00+00:00'
    weight: 0.9
    valid_from: null
    valid_until: null
  validity:
    from: null
    to: null
  status:
    active: true
    superseded_by: null
    superseded_at: null
  mutation_type: active
---

## Summary
EntityB — single relation sourced from doc_cascade_target. CASCADE removal of that doc drops this relation entirely (no other sources).
