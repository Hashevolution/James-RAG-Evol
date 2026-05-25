/**
 * PROJECT JAMES — Reasoning Graph (v0.2 Axis 3 Observability)
 *
 * Renders every wiki entity as a point inside a soft-ball sphere and
 * every ontology relation as a connecting line. When the user submits
 * a query, the response's `graph_paths` strings are parsed client-side
 * and the entities/edges that the reasoner traversed are pulsed with
 * a moving sprite + fading afterglow on the corresponding 3D edges.
 *
 * Backend dependencies:
 *   GET  /admin/graph/snapshot?source_type=prod  (admin_api_key)
 *   POST /query/                                  (any role, returns graph_paths)
 *   POST /login/                                  (admin login)
 *
 * No bundler — all globals: THREE, ForceGraph3D, d3 (from CDN).
 */

(function () {
  'use strict';

  // ─── State ─────────────────────────────────────────────────
  var API     = '';                // same-origin
  // Two-channel auth (matches admin.js pattern):
  //   apiKey  — verifies request envelope (server's JAMES_API_KEY env var).
  //             Populated by the chat page first-run prompt; we may also
  //             ask for it inline if the user lands here directly.
  //   token   — JWT from POST /login/. Used in Authorization: Bearer to
  //             prove admin role. _require_admin() needs BOTH.
  var apiKey  = localStorage.getItem('james_api_key') || '';
  var token   = localStorage.getItem('james_token')   || '';
  var graph   = null;              // ForceGraph3D instance
  var data    = { nodes: [], links: [] };
  var nodeIdx = new Map();         // id → node ref
  var nameIdx = new Map();         // normalized name → [node refs]
  var edgeIdx = new Map();         // 's|t' → link ref
  var pulses  = [];                // active sprites being tweened
  var hoverEl = null;

  // [#4-2 e/j, 2026-05-09] path persistence — once a path is shown it
  // stays lit until (a) another node is clicked or (b) clearActivePath
  // resets to default. [W2 2026-05-10] question-driven paths 제거 —
  // exploreFromNode (이웃 lighting) 가 유일한 path activator.
  var activePathEdges = new Set();   // edge keys currently lit
  var activePathNodes = new Set();   // node ids currently labeled (path-traversed)

  // [#4-2 c-label/f] always-visible name labels. Hubs are always shown.
  // Path-traversed nodes are shown while the path is active. Both share
  // the same Sprite-text mechanism so nothing duplicates.
  var labelSprites    = new Map();   // node id → THREE.Sprite (or null)

  // [PR mobile-loop-search, 2026-05-09] persistent pulse loop.
  // After activatePath / exploreFromNode runs, sprite pulses replay
  // every PULSE_LOOP_MS until the next question or another node click
  // resets the active set. User feedback: pulses dying after one
  // pass loses the "this is the live path" signal.
  var pulseLoopTimer  = null;
  var pulseLoopEdges  = [];          // [{src: node, tgt: node}]
  // [Stage E.1, 2026-05-24] re-fire interval bumped per UX feedback —
  // was 3200ms (one cycle then a long breath). 2000ms keeps the
  // "this is the live path" signal continuously visible without
  // looking frantic. PULSE_MS is the in-flight duration (450ms), so
  // 2000ms still leaves a ~1.5s gap between cycles.
  var PULSE_LOOP_MS   = 2000;

  // [PR camera-glow, 2026-05-09] node halos — soft glowing sprite
  // around each active path node, scale + opacity pulsing on a sine
  // so the node "breathes". Replaces the static "active node" feel
  // with the wrap-around glow the user described.
  var nodeHalos       = new Map();   // nodeId → THREE.Sprite

  // Spacing constant — radius scales with sqrt(N).
  var SPHERE_K  = 24;
  // [Stage E.1, 2026-05-24] pulse speed bump per UX feedback — was 650.
  // 450 keeps the eye-trail readable while making the flow feel "live".
  var PULSE_MS  = 450;
  var STEP_GAP  = 220;             // gap between consecutive edge pulses

  // [#4-1, 2026-05-09] Hub detection — top 10% by degree AND degree ≥ 5.
  // Per decision C-2 (option C-3 from review): both conditions must hold
  // so the "강조 노드" set stays small enough to read. With ~185 entities,
  // top 10% = ~18, intersect with degree ≥ 5 typically lands at 5-12 hubs.
  var HUB_TOP_PCT      = 0.10;
  var HUB_MIN_DEGREE   = 5;
  var hubIds           = new Set();
  var hubDegreeCutoff  = 0;        // computed each load — degree value at top 10% rank

  // ─── Type → color ──────────────────────────────────────────
  function typeColor(t) {
    switch ((t || '').toLowerCase()) {
      case 'person':   return getCss('--t-person',   '#4fc3f7');
      case 'org':      return getCss('--t-org',      '#f59e0b');
      case 'concept':  return getCss('--t-concept',  '#a5b4fc');
      case 'document': return getCss('--t-document', '#94a3b8');
      case 'event':    return getCss('--t-event',    '#fb7185');
      default:         return '#94a3b8';
    }
  }
  function getCss(name, fallback) {
    try {
      var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return v || fallback;
    } catch (e) { return fallback; }
  }

  // ─── Utilities ─────────────────────────────────────────────
  function normalizeName(s) {
    if (!s) return '';
    return s.toString().trim().toLowerCase();
  }
  function edgeKey(s, t) { return s + '|' + t; }

  // ─── Auth ──────────────────────────────────────────────────
  function showLogin() {
    var modal = document.getElementById('login-modal');
    if (modal) modal.classList.add('show');
  }
  function hideLogin() {
    var modal = document.getElementById('login-modal');
    if (modal) modal.classList.remove('show');
  }
  function setLoginError(msg) {
    var el = document.getElementById('login-error');
    if (el) el.textContent = msg || '';
  }
  window.doLogin = async function () {
    var id = document.getElementById('login-id').value.trim();
    var pw = document.getElementById('login-pw').value;
    var keyInput = document.getElementById('login-apikey');
    var keyVal = keyInput ? keyInput.value.trim() : '';
    setLoginError('');
    if (keyVal) { apiKey = keyVal; localStorage.setItem('james_api_key', apiKey); }
    var res = await Auth.login({ username: id, password: pw, apiKey: apiKey, requireRole: 'admin' });
    if (!res.ok) { setLoginError(res.error); return; }
    token = res.token;
    hideLogin();
    bootstrap();
  };

  // ─── Snapshot fetch ────────────────────────────────────────
  async function fetchSnapshot(source) {
    var url = API + '/admin/graph/snapshot?source_type=' +
              encodeURIComponent(source) + '&api_key=' + encodeURIComponent(apiKey);
    var r = await fetch(url, {
      headers: { 'Authorization': 'Bearer ' + token },
    });
    if (r.status === 401 || r.status === 403) {
      // JWT expired or non-admin — drop the token, keep apiKey.
      token = '';
      localStorage.removeItem('james_token');
      localStorage.removeItem('james_role');
      showLogin();
      throw new Error('auth required');
    }
    if (!r.ok) throw new Error('snapshot ' + r.status);
    return r.json();
  }

  function buildIndices() {
    nodeIdx.clear();
    nameIdx.clear();
    edgeIdx.clear();
    data.nodes.forEach(function (n) {
      nodeIdx.set(n.id, n);
      var k = normalizeName(n.name);
      if (!nameIdx.has(k)) nameIdx.set(k, []);
      nameIdx.get(k).push(n);
    });
    data.links.forEach(function (l) {
      var s = typeof l.source === 'object' ? l.source.id : l.source;
      var t = typeof l.target === 'object' ? l.target.id : l.target;
      edgeIdx.set(edgeKey(s, t), l);
    });
    computeHubs();
    // [#4-2] hubs may have changed after a fresh snapshot — labels follow.
    refreshLabels();
  }

  // [#4-1] 핵심 엔티티(hub) 식별: top 10% by degree AND degree ≥ 5.
  // hubIds set을 채우고 hubDegreeCutoff를 계산. 노드 렌더링 시 이 셋을
  // 참조해서 크기/색상/(추후 #4-2) 라벨을 결정한다.
  function computeHubs() {
    hubIds.clear();
    hubDegreeCutoff = 0;
    if (!data.nodes || !data.nodes.length) return;
    // Sort degrees descending, pick top 10% rank index — its degree is
    // the cutoff. Then intersect with absolute floor HUB_MIN_DEGREE.
    var degs = data.nodes.map(function (n) { return n.degree || 0; });
    degs.sort(function (a, b) { return b - a; });
    var rankIdx = Math.max(0, Math.floor(degs.length * HUB_TOP_PCT) - 1);
    var topPctCutoff = degs[rankIdx] || 0;
    hubDegreeCutoff = Math.max(topPctCutoff, HUB_MIN_DEGREE);
    data.nodes.forEach(function (n) {
      if ((n.degree || 0) >= hubDegreeCutoff) hubIds.add(n.id);
    });
  }

  function isHub(n) {
    if (!n) return false;
    return hubIds.has(typeof n === 'object' ? n.id : n);
  }

  // ─── Graph init / refresh ──────────────────────────────────
  function initGraph() {
    var el = document.getElementById('graph-canvas');
    var w  = el.clientWidth, h = el.clientHeight;

    graph = ForceGraph3D()(el)
      .backgroundColor('rgba(0,0,0,0)')
      .width(w).height(h)
      .nodeId('id')
      .nodeLabel(function () { return ''; })   // we render our own tooltip
      // [#4-1 c-color] hubs render in solid type color, non-hubs slightly
      // desaturated so the hubs visually pop without changing palette.
      .nodeColor(function (n) {
        var c = typeColor(n.type);
        if (isHub(n)) return c;            // full saturation
        return c;                           // (force-graph applies node opacity later)
      })
      // [#4-1] non-hubs slightly less opaque → hubs read as primary.
      .nodeOpacity(0.92)
      // [#4-1 c-size] hubs grow ~1.7x, non-hubs unchanged. nodeVal feeds
      // a sphere-volume-proportional scale → 1.7x val ≈ 1.2x apparent
      // radius, enough to read but not crowd neighbors.
      .nodeRelSize(3)
      .nodeVal(function (n) {
        var base = Math.max(1, Math.sqrt((n.degree || 0) + 1));
        return isHub(n) ? base * 1.7 : base;
      })
      // [#4-1 a / #4-2 e] base link visibility + persistent path lit.
      // activePathEdges (no expiry) is the "lit" state — set by
      // exploreFromNode after a node click, cleared on closeNeighborPanel.
      // [#4-1 d] hub-touching links carry slightly more presence.
      .linkColor(function (l) {
        var k = edgeKey(linkSrc(l), linkTgt(l));
        if (activePathEdges.has(k)) {
          return getCss('--accent', '#6366f1');
        }
        var hubTouch = isHub(l.source) || isHub(l.target);
        return hubTouch
          ? 'rgba(190, 200, 220, 0.6)'
          : 'rgba(170, 180, 200, 0.4)';
      })
      .linkOpacity(0.7)
      .linkWidth(function (l) {
        var k = edgeKey(linkSrc(l), linkTgt(l));
        if (activePathEdges.has(k)) {
          return 1.4;                       // slightly bolder for active
        }
        var hubTouch = isHub(l.source) || isHub(l.target);
        return hubTouch ? 0.8 : 0.55;
      })
      .linkDirectionalParticles(0)
      .onNodeHover(onNodeHover)
      .onNodeClick(onNodeClick);

    // [#4-1 b] Subtle volumetric depth via Three.js exponential fog.
    // Distant nodes/links fade gently → 평면(2D 와이어프레임) 느낌이
    // 줄고 sphere의 깊이가 살아남. 가시성은 보존 (fog density ≈ 0.0008,
    // 매우 가벼움). 평면 검출/메시 렌더링은 너무 비싸서 채택 안 함;
    // fog가 사용자가 말한 "복잡도 증가하지 않는 입체감" 트레이드오프.
    try {
      var THREE_NS = (typeof THREE !== 'undefined') ? THREE
                  : (graph.scene && graph.scene().fog && graph.scene().fog.constructor)
                    ? null : null;
      if (THREE_NS && graph.scene) {
        graph.scene().fog = new THREE_NS.FogExp2(0x0c0d10, 0.0008);
      }
    } catch (_) { /* fog optional, do not block render */ }

    // ── Custom forces: link strength ∝ min(deg(s), deg(t)),
    //    plus a soft radial spring that nudges nodes toward a sphere shell.
    var sim = graph.d3Force('link');
    if (sim && sim.strength) {
      sim.strength(function (l) {
        var ds = (typeof l.source === 'object' ? l.source.degree : 0) || 1;
        var dt = (typeof l.target === 'object' ? l.target.degree : 0) || 1;
        var base = 0.3;
        return base * Math.min(Math.min(ds, dt), 8) / 8;
      });
    }
    var charge = graph.d3Force('charge');
    if (charge && charge.strength) charge.strength(-90);

    graph.d3Force('radial', radialBallForce());
  }

  // d3-force-3d: custom radial-ball force that pulls nodes toward a sphere
  // surface of radius R. Uses graph.d3 if exposed, else THREE math directly.
  function radialBallForce() {
    var k = 0.04;
    var nodes = [];
    function force(alpha) {
      var R = SPHERE_K * Math.sqrt(Math.max(nodes.length, 1));
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        var d = Math.sqrt((n.x || 0) * (n.x || 0) + (n.y || 0) * (n.y || 0) + (n.z || 0) * (n.z || 0));
        if (d < 1e-3) {
          // Kick a stationary node off the origin.
          n.vx += (Math.random() - 0.5) * 0.5;
          n.vy += (Math.random() - 0.5) * 0.5;
          n.vz += (Math.random() - 0.5) * 0.5;
          continue;
        }
        var diff = (R - d);
        var s = k * alpha * diff / d;
        n.vx += (n.x || 0) * s;
        n.vy += (n.y || 0) * s;
        n.vz += (n.z || 0) * s;
      }
    }
    force.initialize = function (_nodes) { nodes = _nodes; };
    return force;
  }

  function linkSrc(l) { return typeof l.source === 'object' ? l.source.id : l.source; }
  function linkTgt(l) { return typeof l.target === 'object' ? l.target.id : l.target; }

  async function loadAndRender(source) {
    setStatus(t('graph.loading') || 'Loading entities...');
    try {
      var snap = await fetchSnapshot(source);
      data = {
        nodes: snap.nodes.map(function (n) { return Object.assign({}, n); }),
        links: snap.edges.map(function (e) {
          return {
            source: e.s, target: e.t,
            type:   e.type, weight: e.weight, conf: e.conf,
          };
        }),
      };
      buildIndices();

      if (!graph) initGraph();
      graph.graphData(data);

      // [Knowledge Cascade Phase E UI] graph editor 가 본 instance 에
      // linkClick 핸들러를 attach 할 수 있게 hook. graph_editor.js 는
      // 본 graph.js 이후에 로드되므로 window.GraphEditor 가 이미 정의돼 있다.
      if (window.GraphEditor && typeof window.GraphEditor.onSnapshotLoaded === 'function') {
        try { window.GraphEditor.onSnapshotLoaded(graph, data, { apiKey: apiKey, token: token }); }
        catch (_e) { /* never block graph render */ }
      }
      // [Cycle 12 PR-O6b] node editor — edge editor 와 동일 패턴.
      if (window.GraphNodeEditor && typeof window.GraphNodeEditor.onSnapshotLoaded === 'function') {
        try { window.GraphNodeEditor.onSnapshotLoaded(graph, data, { apiKey: apiKey, token: token, api: API }); }
        catch (_e) { /* never block graph render */ }
      }

      var meta = snap.meta || {};
      var statBox = document.getElementById('stat-box');
      if (statBox) {
        statBox.innerHTML =
          '<div><strong>' + (meta.node_count || 0) + '</strong> nodes</div>' +
          '<div><strong>' + (meta.edge_count || 0) + '</strong> edges</div>' +
          '<div>source: ' + (meta.source_type || source) + '</div>' +
          (meta.truncated ? '<div style="color:var(--warn)">⚠ truncated to ' + meta.edge_hard_cap + ' edges</div>' : '');
      }
      setOverlayCounts(meta);
      setStatus('');
    } catch (e) {
      if (String(e.message || '').indexOf('auth') < 0) {
        setStatus(t('graph.error') || 'Failed to load graph: ' + e);
      }
    }
  }

  function setStatus(s) {
    var el = document.getElementById('overlay-status');
    if (el) el.textContent = s || '';
  }
  function setOverlayCounts(meta) {
    var el = document.getElementById('overlay-counts');
    if (!el) return;
    if (!meta) { el.textContent = ''; return; }
    el.innerHTML =
      'N=' + (meta.node_count || 0) + ' &middot; E=' + (meta.edge_count || 0) +
      ' &middot; #' + (meta.snapshot_hash || '');
  }

  // ─── Hover / click ─────────────────────────────────────────
  function onNodeHover(node, prevNode) {
    var tip = document.getElementById('hover-tip');
    if (!tip) return;
    if (!node) { tip.style.display = 'none'; hoverEl = null; return; }
    hoverEl = node;
    tip.innerHTML =
      '<div class="tt-name">' + escapeHtml(node.name || node.id) + '</div>' +
      '<div class="tt-meta">' + escapeHtml(node.type || '') +
      ' &middot; degree ' + (node.degree || 0) + '</div>';
    tip.style.display = 'block';
  }

  // Track mouse so the tooltip follows it.
  document.addEventListener('mousemove', function (e) {
    var tip = document.getElementById('hover-tip');
    if (!tip || !hoverEl) return;
    var stage = document.querySelector('.stage');
    var rect = stage.getBoundingClientRect();
    tip.style.left = (e.clientX - rect.left + 14) + 'px';
    tip.style.top  = (e.clientY - rect.top  + 14) + 'px';
  });

  function onNodeClick(node) {
    if (!node || !graph) return;
    // [PR camera-glow, 2026-05-09] camera centering — move closer +
    // longer animation so the user clearly sees the screen travel to
    // the picked node. Previous setting felt subtle when the click
    // came from the search drawer or neighbor panel rather than a
    // direct 3D click.
    var distance = 110;        // closer view of the node
    var ratio = 1;
    var d = Math.hypot(node.x || 1, node.y || 1, node.z || 1);
    if (d > 0) ratio = (d + distance) / d;
    graph.cameraPosition(
      { x: (node.x || 0) * ratio,
        y: (node.y || 0) * ratio,
        z: (node.z || 0) * ratio },
      node,
      1200,                    // slower, more visible move
    );
    // [PR explorer, 2026-05-09] click → neighborhood explorer.
    // Lights up the clicked node, animates pulses to its direct
    // neighbors, opens a side panel with their names. Clicking a name
    // in the panel recurs the same animation from that neighbor.
    exploreFromNode(node);
  }

  // ─── [PR explorer] Neighborhood explorer ────────────────────────
  // 1) compute direct neighbors of the clicked node
  // 2) activate edges + nodes for visual highlight (uses #4-2 path
  //    persistence machinery — same Set semantics)
  // 3) replay sprite pulses from center → each neighbor (staggered)
  // 4) render a side panel with neighbor names; click → recurse
  function getNeighbors(node) {
    if (!node) return [];
    var nodeId = node.id;
    var out = [];
    var seenIds = new Set();
    data.links.forEach(function (l) {
      var sId = linkSrc(l);
      var tId = linkTgt(l);
      if (sId === nodeId && !seenIds.has(tId)) {
        var n = nodeIdx.get(tId);
        if (n) { out.push({ neighbor: n, edge: l, direction: 'out' });
                 seenIds.add(tId); }
      } else if (tId === nodeId && !seenIds.has(sId)) {
        var n2 = nodeIdx.get(sId);
        if (n2) { out.push({ neighbor: n2, edge: l, direction: 'in' });
                  seenIds.add(sId); }
      }
    });
    return out;
  }

  function exploreFromNode(node) {
    if (!node) return;
    var neighbors = getNeighbors(node);

    // Reset prior path lighting (neighborhood explorer takes over).
    clearActivePath(/*skipRefresh*/true);
    activePathNodes.add(node.id);
    neighbors.forEach(function (item) {
      activePathNodes.add(item.neighbor.id);
      // Edge key direction-aware — we store edges as (src,tgt) per
      // edgeIdx; pick the matching direction.
      var k1 = edgeKey(node.id, item.neighbor.id);
      var k2 = edgeKey(item.neighbor.id, node.id);
      if (edgeIdx.has(k1)) activePathEdges.add(k1);
      else if (edgeIdx.has(k2)) activePathEdges.add(k2);
    });
    refreshLabels();
    refreshNodeHalos();   // [PR camera-glow] halo center + neighbors

    // Sprite pulses outward — staggered so the eye can follow flow.
    var stepMs = 0;
    var loopEdges = [];
    neighbors.forEach(function (item) {
      // [Stage E.1, 2026-05-24] direction contract — the pulse must travel
      // along the data edge's source → target axis, NOT always away from
      // the clicked node. getNeighbors() already tags each item with
      // direction ('out' = node→neighbor, 'in' = neighbor→node); honoring
      // it makes the lit pulse match the arrowhead the user sees.
      var pulseSrc = (item.direction === 'in') ? item.neighbor : node;
      var pulseTgt = (item.direction === 'in') ? node : item.neighbor;
      setTimeout(function () { spawnPulse(pulseSrc, pulseTgt); }, stepMs);
      stepMs += STEP_GAP / 2;   // slightly faster than path replay
      loopEdges.push({ src: pulseSrc, tgt: pulseTgt });
    });

    // Re-trigger force-graph render so links re-color.
    if (graph) {
      graph.linkColor(graph.linkColor());
      graph.linkWidth(graph.linkWidth());
    }

    renderNeighborPanel(node, neighbors);

    // [W2 2026-05-10] 노드 요약 패널 — neighbor-panel 상단에 엔티티
    // 본문 발췌·메타 표시. 질문 입력 (askQuestion) + 자동 질문
    // (suggested-questions) 은 모두 제거됨 — graph 페이지를 순수 탐색기
    // 로 단순화. 질문은 /chat 페이지에서.
    fetchAndRenderEntitySummary(node);

    // [PR mobile-loop-search] keep the neighborhood lit — pulses re-
    // fire every PULSE_LOOP_MS until next click clears.
    setTimeout(function () { startPulseLoop(loopEdges); }, stepMs + 400);
  }

  function renderNeighborPanel(centerNode, neighbors) {
    var panel = document.getElementById('neighbor-panel');
    if (!panel) return;
    panel.style.display = 'block';
    // [PR click-fix, 2026-05-09] use data-id + addEventListener instead
    // of inline onclick. The previous inline form interpolated
    // JSON.stringify(id) (which produces "double-quoted" output) into
    // a double-quoted HTML attribute → attribute parser broke at the
    // first inner ", onclick handler never registered. Direct 3D
    // node click worked because force-graph registers via callback,
    // not HTML attribute. Bug surfaced as "panel click does nothing".
    var rowsHtml;
    if (neighbors.length === 0) {
      rowsHtml = '<div class="np-empty">연결된 이웃 없음</div>';
    } else {
      rowsHtml = neighbors.slice(0, 50).map(function (item) {
        var rel = (item.edge && item.edge.type) || 'RELATED_TO';
        var arrow = item.direction === 'out' ? '→' : '←';
        return '<div class="np-item" data-neighbor-id="' +
               escapeHtml(item.neighbor.id) + '">' +
               '<span class="np-arrow">' + arrow + '</span>' +
               '<span class="np-name">' + escapeHtml(item.neighbor.name || '?') + '</span>' +
               '<span class="np-rel">' + escapeHtml(rel) + '</span>' +
               '</div>';
      }).join('');
    }
    panel.innerHTML =
      '<button class="np-close" data-action="close-neighbor" ' +
      'title="닫기">×</button>' +
      '<div class="np-title">🔗 ' + escapeHtml(centerNode.name || '?') + '</div>' +
      '<div class="np-meta">' + neighbors.length + '개 직접 연결' +
      (neighbors.length > 50 ? ' (50개까지 표시)' : '') + '</div>' +
      '<div class="np-list">' + rowsHtml + '</div>';

    // Wire programmatic click handlers — bypass HTML-attribute
    // quoting issues (and works identically across mouse/touch).
    var closeBtn = panel.querySelector('[data-action="close-neighbor"]');
    if (closeBtn) {
      closeBtn.addEventListener('click', function () { closeNeighborPanel(); });
    }
    panel.querySelectorAll('[data-neighbor-id]').forEach(function (row) {
      row.addEventListener('click', function () {
        var id = row.getAttribute('data-neighbor-id');
        if (id) onNeighborClick(id);
      });
    });
  }

  window.onNeighborClick = function (neighborId) {
    var n = nodeIdx.get(neighborId);
    if (!n) return;
    // Camera move + recursive explore.
    onNodeClick(n);
  };

  window.closeNeighborPanel = function () {
    var panel = document.getElementById('neighbor-panel');
    if (panel) panel.style.display = 'none';
    clearActivePath();
  };

  // ─── [W2 2026-05-10] 노드 요약 패널 ────────────────────────────
  // 사용자가 그래프 노드를 클릭하면 /admin/entities/<id> 를 호출해서
  // 엔티티 본문 발췌·타입·sensitivity 를 neighbor-panel 상단에 표시.
  // 이전엔 자동 질문 chip 을 띄웠지만 W2 에서 graph 페이지를 순수
  // 탐색기로 단순화 — 질문 입력은 /chat 으로 이관.
  //
  // 동시에 여러 노드 클릭이 들어오면 마지막 요청만 반영 (race 방지).
  var _summaryReqSeq = 0;

  function fetchAndRenderEntitySummary(node) {
    var box = document.getElementById('neighbor-panel');
    if (!box || !node || !node.id) return;
    // 즉시 로딩 표시 — 패널이 그려지자마자 사용자가 응답을 기다리는
    // 중임을 알 수 있게.
    renderEntitySummaryPlaceholder(node);
    var seq = ++_summaryReqSeq;
    var key = encodeURIComponent(apiKey || '');
    var url = API + '/admin/entities/' + encodeURIComponent(node.id) +
              '?api_key=' + key;
    // [PR-O1, 2026-05-15] /admin/entities/<id> 는 admin.data 게이트라
    // Bearer JWT 필수. snapshot fetch (fetchSnapshot) 와 동일 패턴.
    // 헤더 누락 시 항상 403 — "요약 불러오지 못했습니다 403" 라이브 차단.
    fetch(url, {
      credentials: 'same-origin',
      headers: { 'Authorization': 'Bearer ' + token },
    })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        if (seq !== _summaryReqSeq) return;   // outdated — drop
        renderEntitySummary(data);
      })
      .catch(function (e) {
        if (seq !== _summaryReqSeq) return;
        renderEntitySummaryError(node, e);
      });
  }

  function _summaryHostEl() {
    // neighbor-panel 안의 .np-summary 엘리먼트를 prepend/replace.
    var panel = document.getElementById('neighbor-panel');
    if (!panel) return null;
    var host = panel.querySelector('.np-summary');
    if (!host) {
      host = document.createElement('div');
      host.className = 'np-summary';
      // np-title 다음에 삽입 — neighbor-panel 의 헤더는 close 버튼 +
      // np-title + np-meta + np-list 순서로 그려지므로 np-meta 전에 넣기.
      var meta = panel.querySelector('.np-meta');
      if (meta && meta.parentNode === panel) {
        panel.insertBefore(host, meta);
      } else {
        panel.appendChild(host);
      }
    }
    return host;
  }

  function renderEntitySummaryPlaceholder(node) {
    var host = _summaryHostEl();
    if (!host) return;
    host.innerHTML =
      '<div class="np-summary-meta">' +
        '<span class="np-summary-type">' +
        escapeHtml((node.type || 'unknown').toUpperCase()) +
        '</span>' +
      '</div>' +
      '<div class="np-summary-loading">▸ 요약 불러오는 중…</div>';
  }

  function renderEntitySummaryError(node, err) {
    var host = _summaryHostEl();
    if (!host) return;
    host.innerHTML =
      '<div class="np-summary-meta">' +
        '<span class="np-summary-type">' +
        escapeHtml((node.type || 'unknown').toUpperCase()) +
        '</span>' +
      '</div>' +
      '<div class="np-summary-body np-empty-body">' +
        '요약을 불러오지 못했습니다 — ' + escapeHtml(String(err)) +
      '</div>';
  }

  // [Cycle 12 PR-O6b] entity_type 코드 → 표시 라벨. i18n.js 의
  // `graph.legend.<type>` 키 (인물/조직/개념/문서) 를 우선 사용.
  function _etypeLabel(etype) {
    var key = 'graph.legend.' + String(etype || '').toLowerCase();
    if (typeof t === 'function') {
      var v = t(key);
      if (v && v !== key) return v;
    }
    return String(etype || 'unknown').toUpperCase();
  }

  function renderEntitySummary(data) {
    var host = _summaryHostEl();
    if (!host || !data) return;
    var etype = data.entity_type || 'unknown';
    var sens  = data.sensitivity || 'internal';
    var body  = (data.body || '').trim();

    // 본문 발췌 — 너무 길면 첫 ~360자 + 말줄임. body 가 frontmatter 없는
    // 순수 문서 텍스트라 그대로 잘라도 안전.
    var excerpt;
    if (body.length === 0) {
      excerpt = '<div class="np-summary-body np-empty-body">' +
                '본문 비어있음 (메타데이터만 존재)</div>';
    } else {
      var trimmed = body.length > 360
        ? body.slice(0, 360).trimEnd() + '…'
        : body;
      excerpt = '<div class="np-summary-body">' +
                escapeHtml(trimmed) +
                '</div>';
    }

    host.innerHTML =
      '<div class="np-summary-meta">' +
        '<span class="np-summary-type">' + escapeHtml(_etypeLabel(etype)) + '</span>' +
        '<span class="np-summary-sens sens-' + escapeHtml(sens) + '">' +
          escapeHtml(sens.toUpperCase()) +
        '</span>' +
      '</div>' +
      excerpt +
      // [Cycle 12 PR-O6b] np-summary-actions placeholder — node editor
      // 가 admin + edit-mode-ON 일 때 "노드 편집" 버튼을 여기에 주입.
      '<div class="np-summary-actions" id="np-summary-actions"></div>';

    // node editor 에게 summary 가 새로 그려졌음을 알린다.
    if (window.GraphNodeEditor &&
        typeof window.GraphNodeEditor.onEntitySummaryRendered === 'function') {
      try { window.GraphNodeEditor.onEntitySummaryRendered(data); }
      catch (_e) { /* never break summary render */ }
    }
  }

  // ─── [PR mobile-loop-search] Top entity search drawer ──────────
  // Click toggle tab → drawer slides down → input + filtered list of
  // entity names. Click a row → camera moves to that node + neighborhood
  // explorer fires. Phone-friendly (replaces the side aside on
  // <720px). ESC closes the drawer.
  window.toggleSearchDrawer = function () {
    var drawer = document.getElementById('search-drawer');
    if (!drawer) return;
    var isOpen = drawer.classList.contains('tsd-open');
    if (isOpen) hideSearchDrawer();
    else showSearchDrawer();
  };

  function showSearchDrawer() {
    var drawer = document.getElementById('search-drawer');
    if (!drawer) return;
    drawer.classList.add('tsd-open');
    var input = document.getElementById('tsd-search');
    if (input) {
      input.value = '';
      _renderSearchList('');
      setTimeout(function () { input.focus(); }, 80);
    }
    var toggle = document.getElementById('tsd-toggle');
    if (toggle) toggle.textContent = '🔎 검색 ▴';
  }

  window.hideSearchDrawer = function () {
    var drawer = document.getElementById('search-drawer');
    if (!drawer) return;
    drawer.classList.remove('tsd-open');
    var toggle = document.getElementById('tsd-toggle');
    if (toggle) toggle.textContent = '🔎 검색 ▾';
  };

  // Render the list rows for query `q` (case-insensitive substring).
  // Empty `q` → top 30 by degree (signal: importance).
  function _renderSearchList(q) {
    var listEl = document.getElementById('tsd-list');
    if (!listEl) return;
    var qNorm = (q || '').toLowerCase().trim();
    var rows;
    if (!qNorm) {
      rows = data.nodes.slice().sort(function (a, b) {
        return (b.degree || 0) - (a.degree || 0);
      }).slice(0, 30);
    } else {
      rows = data.nodes.filter(function (n) {
        return (n.name || '').toLowerCase().indexOf(qNorm) >= 0;
      }).slice(0, 100);
    }
    if (!rows.length) {
      listEl.innerHTML =
        '<div class="tsd-empty">' +
        (qNorm ? '\'' + escapeHtml(qNorm) + '\' 일치 없음' : '엔티티 없음') +
        '</div>';
      return;
    }
    // [PR click-fix, 2026-05-09] data-id + addEventListener instead
    // of inline onclick (same JSON.stringify-into-double-quoted-attr
    // bug as renderNeighborPanel — see that fn's comment).
    listEl.innerHTML = rows.map(function (n) {
      return '<div class="tsd-row" data-search-id="' +
             escapeHtml(n.id) + '">' +
             '<span class="tsd-type">' + escapeHtml(n.type || '?') + '</span>' +
             '<span class="tsd-name">' + escapeHtml(n.name || '?') + '</span>' +
             '<span class="tsd-deg">' + (n.degree || 0) + '</span>' +
             '</div>';
    }).join('');
    // Wire click handlers programmatically.
    listEl.querySelectorAll('[data-search-id]').forEach(function (row) {
      row.addEventListener('click', function () {
        var id = row.getAttribute('data-search-id');
        if (id) onSearchRowClick(id);
      });
    });
  }

  // Click a search row → close drawer + camera nudge + explore neighborhood.
  window.onSearchRowClick = function (nodeId) {
    var n = nodeIdx.get(nodeId);
    if (!n) return;
    hideSearchDrawer();
    // onNodeClick already does camera move + exploreFromNode.
    onNodeClick(n);
  };

  // Wire the search input live-filter.
  function _bindSearchDrawerInput() {
    var input = document.getElementById('tsd-search');
    if (!input || input._tsdBound) return;
    input.addEventListener('input', function (e) {
      _renderSearchList(e.target.value);
    });
    input._tsdBound = true;
    // ESC to close from anywhere.
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        var drawer = document.getElementById('search-drawer');
        if (drawer && drawer.classList.contains('tsd-open')) {
          hideSearchDrawer();
        }
      }
    });
  }

  // [W2 2026-05-10] parsePath / resolveHop / animatePaths 등 path-string
  // 파서 인프라는 askQuestion 답변의 graph_paths 시각화 전용이었음.
  // 질문 인터페이스 제거와 함께 dead code → 제거. 후속 PR 에서 chat 페이지
  // 답변을 graph 페이지에 띄우는 기능이 필요하면 복원.

  // ─── [#4-2 c-label/f] Sprite text labels ───────────────────────
  // Canvas-rendered text → Three.Sprite. Cheap (one canvas per node,
  // disposed when label hidden). Only hubs + path-traversed nodes get
  // labels; this keeps the visible label count to typically <30, which
  // avoids the readability mess of labeling all 185 nodes.
  function createTextSprite(text, color) {
    if (typeof THREE === 'undefined') return null;
    // Soft cap on label length — 28 visible chars is enough for any
    // human-readable entity name. Longer strings (e.g. raw document
    // node IDs like "web_business_경쟁사 대비 AMD 기술적 우위 …") get
    // ellipsized so the sprite quad can't grow without bound.
    var label = String(text || '?');
    if (label.length > 28) label = label.slice(0, 27) + '…';

    // Korean-first fallback chain — canvas glyph fallback is browser-
    // dependent and unreliable on Chromium when the primary font lacks
    // CJK glyphs (Inter has zero Hangul coverage). Native CJK first
    // guarantees Hangul renders on every platform JAMES targets.
    var FONT = 'bold 24px "Malgun Gothic", "Apple SD Gothic Neo", ' +
               '"Noto Sans KR", "Pretendard", Inter, system-ui, sans-serif';
    var canvas = document.createElement('canvas');
    var ctx = canvas.getContext('2d');
    // Measure before sizing — measureText respects ctx.font even on a
    // default-sized canvas, and the result tells us how wide the
    // backing texture has to be to fit the glyphs without clipping.
    ctx.font = FONT;
    var textWidth = ctx.measureText(label).width;
    // Pad both sides for the drop-shadow blur and gutters; quantize to
    // 16px so successive labels with slightly different widths share
    // texture sizes more often. 256 floor keeps short labels at the
    // original visual footprint; 768 ceiling keeps any one label from
    // spanning the viewport.
    var pad = 24;
    var canvasW = Math.min(768,
      Math.max(256, Math.ceil((textWidth + pad * 2) / 16) * 16));
    canvas.width = canvasW;
    canvas.height = 64;
    // Setting canvas.width resets 2D-context state — re-apply.
    ctx.font = FONT;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.shadowColor = 'rgba(0,0,0,0.85)';
    ctx.shadowBlur = 6;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 0;
    ctx.fillStyle = color || '#ffffff';
    ctx.fillText(label, canvasW / 2, 32);
    var tex = new THREE.CanvasTexture(canvas);
    tex.minFilter = THREE.LinearFilter;     // canvas isn't power-of-two
    var mat = new THREE.SpriteMaterial({
      map:        tex,
      transparent: true,
      depthTest:   false,                    // always on top of edges
      depthWrite:  false,
    });
    var sprite = new THREE.Sprite(mat);
    // Scale the sprite plane in proportion to the backing canvas so a
    // longer texture renders the *same* physical glyph size on screen,
    // just over a wider strip. Baseline (256-wide) keeps 36×9.
    var scaleX = 36 * (canvasW / 256);
    sprite.scale.set(scaleX, 9, 1);
    sprite.userData.isLabel = true;
    return sprite;
  }

  // Dispose a sprite's texture+material to avoid leaks on rapid switches.
  function disposeSprite(sp) {
    if (!sp) return;
    try {
      var scene = graph && graph.scene && graph.scene();
      if (scene) scene.remove(sp);
      if (sp.material) {
        if (sp.material.map) sp.material.map.dispose();
        sp.material.dispose();
      }
    } catch (e) {}
  }

  // Recompute which nodes should have visible labels based on current
  // hubIds + activePathNodes. Idempotent; safe to call after any state
  // change. Labels track their node's position via per-frame update.
  function refreshLabels() {
    if (!graph) return;
    var scene = graph.scene && graph.scene();
    if (!scene) return;
    var shouldShow = new Set();
    hubIds.forEach(function (id) { shouldShow.add(id); });
    activePathNodes.forEach(function (id) { shouldShow.add(id); });

    // Remove labels for nodes no longer in shouldShow.
    labelSprites.forEach(function (sprite, nodeId) {
      if (!shouldShow.has(nodeId)) {
        disposeSprite(sprite);
        labelSprites.delete(nodeId);
      }
    });
    // Add labels for nodes newly in shouldShow.
    shouldShow.forEach(function (nodeId) {
      if (labelSprites.has(nodeId)) return;
      var n = nodeIdx.get(nodeId);
      if (!n) return;
      var color = activePathNodes.has(nodeId)
        ? getCss('--brand-2', '#4fc3f7')      // path-traversed: cyan accent
        : '#f5f7fa';                           // hub: bright white-ish
      var sp = createTextSprite(n.name || '?', color);
      if (!sp) return;
      sp.userData.nodeId = nodeId;
      scene.add(sp);
      labelSprites.set(nodeId, sp);
    });
  }

  // Per-frame: update each label sprite to track its node position
  // (slightly above the node sphere). Called from pulseTick.
  function tickLabelPositions() {
    if (!labelSprites.size) return;
    labelSprites.forEach(function (sp, nodeId) {
      var n = nodeIdx.get(nodeId);
      if (!n || !sp) return;
      sp.position.set((n.x || 0), (n.y || 0) + 7, (n.z || 0));
    });
  }

  // [W2 2026-05-10] activatePath (질문 답변 경로 활성화) 제거. 이제
  // exploreFromNode (이웃 lighting) 만이 active path 를 사용한다.
  // clearActivePath 는 closeNeighborPanel/exploreFromNode 가 호출.

  function clearActivePath(skipRefresh) {
    activePathEdges.clear();
    activePathNodes.clear();
    stopPulseLoop();
    refreshNodeHalos();              // [PR camera-glow] kill halos
    if (!skipRefresh) {
      refreshLabels();
      if (graph) {
        graph.linkColor(graph.linkColor());
        graph.linkWidth(graph.linkWidth());
      }
    }
  }

  // [PR camera-glow] Sync nodeHalos with activePathNodes. Add halos
  // for newly-active nodes, dispose for nodes that left the active set.
  function refreshNodeHalos() {
    if (!graph) return;
    var scene = graph.scene && graph.scene();
    if (!scene || typeof THREE === 'undefined') return;
    var color = getCss('--brand-2', '#4fc3f7');
    // Add halos for newly-active nodes.
    activePathNodes.forEach(function (nodeId) {
      if (nodeHalos.has(nodeId)) return;
      var n = nodeIdx.get(nodeId);
      if (!n) return;
      var tex = getGlowTexture(color);
      if (!tex) return;
      var mat = new THREE.SpriteMaterial({
        map:         tex,
        color:       0xffffff,
        transparent: true,
        opacity:     0.55,
        blending:    THREE.AdditiveBlending,
        depthWrite:  false,
      });
      var sp = new THREE.Sprite(mat);
      sp.scale.set(20, 20, 1);
      sp.userData.isHalo = true;
      sp.userData.nodeId = nodeId;
      sp.userData.bornMs = performance.now();
      scene.add(sp);
      nodeHalos.set(nodeId, sp);
    });
    // Remove halos for nodes that left the active set.
    nodeHalos.forEach(function (sp, nodeId) {
      if (!activePathNodes.has(nodeId)) {
        disposeSprite(sp);
        nodeHalos.delete(nodeId);
      }
    });
  }

  // [PR camera-glow] Per-frame halo update — position-tracking + sine
  // pulse. Called from pulseTick alongside tickLabelPositions.
  function tickNodeHalos() {
    if (!nodeHalos.size) return;
    var now = performance.now();
    nodeHalos.forEach(function (sp, nodeId) {
      var n = nodeIdx.get(nodeId);
      if (!n || !sp) return;
      sp.position.set(n.x || 0, n.y || 0, n.z || 0);
      // Per-halo phase offset (born time) so halos pulse out of sync —
      // looks more organic than uniform breathing.
      var t = ((now - (sp.userData.bornMs || 0)) / 1800) % 1;   // 1.8s period
      var phase = Math.sin(t * Math.PI * 2);
      // Scale 17..23, opacity 0.4..0.7 — gentle wrap-around feel.
      var s = 20 + 3 * phase;
      sp.scale.set(s, s, 1);
      sp.material.opacity = 0.55 + 0.15 * phase;
    });
  }

  // [PR mobile-loop-search] persistent pulse loop. Replays sprite
  // pulses on the active edges every PULSE_LOOP_MS until cleared.
  // The visual flow stays alive so the user perceives "the path is
  // currently lit", instead of a single one-shot firing that fades.
  function startPulseLoop(edges) {
    stopPulseLoop();
    pulseLoopEdges = (edges || []).filter(function (e) {
      return e && e.src && e.tgt;
    });
    if (!pulseLoopEdges.length) return;
    var fire = function () {
      // Snapshot current — caller may have called stopPulseLoop()
      // between intervals.
      var snap = pulseLoopEdges.slice();
      var stagger = Math.min(STEP_GAP, 220);
      snap.forEach(function (e, i) {
        setTimeout(function () {
          // Re-check every fire — clearActivePath may have hit between
          // setTimeout schedule and execution.
          if (pulseLoopEdges.indexOf(e) >= 0) {
            spawnPulse(e.src, e.tgt);
          }
        }, i * stagger);
      });
    };
    fire();   // immediate first pass
    pulseLoopTimer = setInterval(fire, PULSE_LOOP_MS);
  }

  function stopPulseLoop() {
    if (pulseLoopTimer) {
      clearInterval(pulseLoopTimer);
      pulseLoopTimer = null;
    }
    pulseLoopEdges = [];
  }

  // ─── [PR camera-glow, 2026-05-09] Soft radial-gradient texture ─
  // Cached canvas-based gradient — used as the map for traveling
  // pulse sprites AND for node halos. The "wraps around" feel the
  // user requested comes from a soft falloff at the edge instead of
  // the hard square sprite previously used.
  var _glowTexCache = new Map();
  function _hexToRgba(hex, a) {
    var h = (hex || '').replace('#', '');
    if (h.length === 3) h = h.split('').map(function(c){return c+c}).join('');
    if (h.length !== 6) return 'rgba(79,195,247,' + a + ')';   // fallback
    var r = parseInt(h.substr(0, 2), 16);
    var g = parseInt(h.substr(2, 2), 16);
    var b = parseInt(h.substr(4, 2), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',' + a + ')';
  }
  function getGlowTexture(hexColor) {
    if (typeof THREE === 'undefined') return null;
    if (_glowTexCache.has(hexColor)) return _glowTexCache.get(hexColor);
    var canvas = document.createElement('canvas');
    canvas.width = 128; canvas.height = 128;
    var ctx = canvas.getContext('2d');
    var grad = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
    grad.addColorStop(0,   _hexToRgba(hexColor, 1.0));   // bright core
    grad.addColorStop(0.3, _hexToRgba(hexColor, 0.7));
    grad.addColorStop(0.6, _hexToRgba(hexColor, 0.25));
    grad.addColorStop(1,   _hexToRgba(hexColor, 0));     // soft falloff
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 128, 128);
    var tex = new THREE.CanvasTexture(canvas);
    tex.minFilter = THREE.LinearFilter;
    _glowTexCache.set(hexColor, tex);
    return tex;
  }

  // ─── Pulse animation ───────────────────────────────────────
  function spawnPulse(srcNode, tgtNode) {
    if (!graph || !srcNode || !tgtNode) return;
    if (typeof THREE === 'undefined') return;
    var scene = graph.scene();
    if (!scene) return;

    // [Stage E.1, 2026-05-24] color gradient src→tgt — pulse starts in
    // source-node tint and shifts to target-node tint over its lifetime.
    // Texture stays a neutral white radial; material.color is what we lerp.
    // Reads as "leaving here, arriving there" and pairs with the arrowhead.
    var srcHex = typeColor(srcNode.type) || getCss('--brand-2', '#4fc3f7');
    var tgtHex = typeColor(tgtNode.type) || srcHex;
    var tex = getGlowTexture('#ffffff');   // single shared white texture
    var spriteMat = new THREE.SpriteMaterial({
      map:         tex,
      color:       new THREE.Color(srcHex),   // mutated per-frame in pulseTick
      transparent: true,
      opacity:     0.95,
      blending:    THREE.AdditiveBlending,
      depthWrite:  false,
    });
    var sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(14, 14, 1);    // was 8 — softer, more "fluid light"
    sprite.position.set(srcNode.x || 0, srcNode.y || 0, srcNode.z || 0);
    scene.add(sprite);

    pulses.push({
      sprite:    sprite,
      src:       srcNode,
      tgt:       tgtNode,
      startMs:   performance.now(),
      srcColor:  new THREE.Color(srcHex),
      tgtColor:  new THREE.Color(tgtHex),
    });
  }

  function pulseTick() {
    var now = performance.now();
    var live = [];
    for (var i = 0; i < pulses.length; i++) {
      var p = pulses[i];
      var dt = now - p.startMs;
      var k = dt / PULSE_MS;
      if (k >= 1.0 || !p.src || !p.tgt) {
        // Done — remove.
        try { graph.scene().remove(p.sprite); } catch (e) {}
        if (p.sprite.material) p.sprite.material.dispose();
      } else {
        var x = (p.src.x || 0) * (1 - k) + (p.tgt.x || 0) * k;
        var y = (p.src.y || 0) * (1 - k) + (p.tgt.y || 0) * k;
        var z = (p.src.z || 0) * (1 - k) + (p.tgt.z || 0) * k;
        p.sprite.position.set(x, y, z);
        // Fade-in then fade-out around midpoint.
        var op = 1.0 - Math.abs(k - 0.5) * 1.6;
        p.sprite.material.opacity = Math.max(0, op);
        // [Stage E.1] color lerp — src tint at k=0, tgt tint at k=1.
        if (p.srcColor && p.tgtColor && p.sprite.material.color) {
          p.sprite.material.color.copy(p.srcColor).lerp(p.tgtColor, k);
        }
        live.push(p);
      }
    }
    pulses = live;

    // [#4-2 c-label/f] keep labels glued to their nodes per frame.
    tickLabelPositions();
    // [PR camera-glow] halo position-track + sine pulse per frame.
    tickNodeHalos();
    requestAnimationFrame(pulseTick);
  }

  // [W2 2026-05-10] askQuestion / answer-card / history / activatePath /
  // animatePaths / pulseTerminalNode 등 질문-답변 인프라는 모두 제거.
  // graph 페이지는 순수 탐색기 — 질문은 /chat 페이지에서.
  // activePathEdges/activePathNodes/clearActivePath 는 exploreFromNode 가
  // 사용하므로 유지.

  // ─── Misc ──────────────────────────────────────────────────
  function escapeHtml(s) {
    return String(s || '').replace(/[&<>"']/g, function (c) {
      return ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[c];
    });
  }

  // Fallback for t() in case i18n.js hasn't loaded.
  function t(k) {
    if (typeof window.t === 'function') return window.t(k);
    return null;
  }

  // ─── Bootstrap ─────────────────────────────────────────────
  function bootstrap() {
    initGraph();
    requestAnimationFrame(pulseTick);
    var src = document.getElementById('src-select');
    src.addEventListener('change', function () { loadAndRender(src.value); });

    // [PR mobile-loop-search] wire the top entity search drawer.
    _bindSearchDrawerInput();

    var search = document.getElementById('node-search');
    if (search) {
      search.addEventListener('input', function () {
        var q = normalizeName(search.value);
        if (!q) {
          // Reset opacity.
          if (graph) graph.nodeOpacity(0.92);
          return;
        }
        if (!graph) return;
        graph.nodeOpacity(function (n) {
          return (normalizeName(n.name).indexOf(q) >= 0) ? 1.0 : 0.18;
        });
      });
    }

    // Resize handling.
    window.addEventListener('resize', function () {
      if (!graph) return;
      var el = document.getElementById('graph-canvas');
      graph.width(el.clientWidth).height(el.clientHeight);
    });

    loadAndRender(src.value);
  }

  // ─── Inline-handler migration (CSP-friendly delegation) ───────
  // graph.html no longer uses ``onclick=`` / ``onkeydown=`` inline
  // attributes. Instead, buttons set ``data-action="…"`` and the
  // routing happens here. Key shortcuts (Enter on login fields,
  // Escape on the search drawer input) are also delegated through
  // the document so they keep working without inline handlers.
  function _bindFrontendEvents() {
    document.addEventListener('click', function (e) {
      var t = e.target.closest && e.target.closest('[data-action]');
      if (!t) return;
      switch (t.getAttribute('data-action')) {
        case 'toggle-lang':
          if (typeof window.toggleLang === 'function') window.toggleLang();
          break;
        case 'toggle-search-drawer':
          if (typeof window.toggleSearchDrawer === 'function') window.toggleSearchDrawer();
          break;
        case 'do-login':
          if (typeof window.doLogin === 'function') window.doLogin();
          break;
      }
    });
    document.addEventListener('keydown', function (e) {
      var id = e.target && e.target.id;
      if (!id) return;
      if (e.key === 'Enter' && (id === 'login-pw' || id === 'login-apikey')) {
        if (typeof window.doLogin === 'function') window.doLogin();
      } else if (e.key === 'Escape' && id === 'tsd-search') {
        if (typeof window.hideSearchDrawer === 'function') window.hideSearchDrawer();
      }
    });
  }

  function start() {
    _bindFrontendEvents();
    if (!apiKey || !token) { showLogin(); return; }
    // Probe with a tiny admin request to see if our token still proves admin.
    fetch(API + '/admin/graph/snapshot?source_type=prod&api_key=' +
          encodeURIComponent(apiKey), {
            method: 'GET',
            headers: { 'Authorization': 'Bearer ' + token },
          })
      .then(function (r) {
        if (r.ok) { bootstrap(); return; }
        // 401/403 → token expired or not admin. Clear and re-prompt.
        token = '';
        localStorage.removeItem('james_token');
        localStorage.removeItem('james_role');
        showLogin();
      })
      .catch(function () { showLogin(); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
