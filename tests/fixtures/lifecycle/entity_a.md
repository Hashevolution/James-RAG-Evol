---
entity_id: e_concept_a
entity_type: concept
name: EntityA
normalized_name: entity_a
owner: system
created_at: '2026-05-01T00:00:00+00:00'
updated_at: '2026-05-01T00:00:00+00:00'
source_type: prod
sensitivity: internal
sources:
- doc_unrelated.pdf
relations:
- id: e_edge_a_v1
  confidence: 0.9
  label: legacy
  target: EntityC
  target_id: e_concept_c
  type: RELATED_TO
  sources:
  - doc_id: doc_unrelated
    role: primary
    ts: '2026-04-01T00:00:00+00:00'
    weight: 0.9
    valid_from: null
    valid_until: null
  validity:
    from: '2026-04-01T00:00:00+00:00'
    to: '2026-05-15T00:00:00+00:00'
  status:
    active: false
    superseded_by: e_edge_a_v2
    superseded_at: '2026-05-15T00:00:00+00:00'
  mutation_type: superseded
- id: e_edge_a_v2
  confidence: 0.95
  label: revised
  target: EntityC
  target_id: e_concept_c
  type: RELATED_TO
  sources:
  - doc_id: doc_unrelated
    role: primary
    ts: '2026-05-15T00:00:00+00:00'
    weight: 0.95
    valid_from: null
    valid_until: null
  validity:
    from: '2026-05-15T00:00:00+00:00'
    to: null
  status:
    active: true
    superseded_by: null
    superseded_at: null
  mutation_type: active
---

## Summary
EntityA — 2-link supersede chain to EntityC (V1 superseded 2026-05-15 → V2 active).
