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
  var afterGlow = new Map();       // legacy time-based glow (briefly used by re-fire)
  var hoverEl = null;

  // [#4-2 e/j, 2026-05-09] path persistence — replaces the old time-based
  // afterGlow expiry. Once a question's path is shown it stays lit until
  // (a) another question is asked, (b) user clicks a history entry to
  // switch, or (c) closeAnswer() resets to default mode. No 4.2s timer.
  var activePathEdges = new Set();   // edge keys currently lit
  var activePathNodes = new Set();   // node ids currently labeled (path-traversed)
  var activeAnswerId  = null;        // which entry in answerHistory is active

  // [#4-2 c-label/f] always-visible name labels. Hubs are always shown.
  // Path-traversed nodes are shown while the path is active. Both share
  // the same Sprite-text mechanism so nothing duplicates.
  var labelSprites    = new Map();   // node id → THREE.Sprite (or null)

  // [#4-2 h/i] in-memory question history. Decision C-3 — session-volatile,
  // never persisted (page refresh on /admin/graph is uncommon and the
  // history is observability scaffolding, not a save target).
  var answerHistory   = [];          // [{id, question, answer, paths, ts}]
  var historyCounter  = 0;           // monotonic id source

  // [PR mobile-loop-search, 2026-05-09] persistent pulse loop.
  // After activatePath / exploreFromNode runs, sprite pulses replay
  // every PULSE_LOOP_MS until the next question or another node click
  // resets the active set. User feedback: pulses dying after one
  // pass loses the "this is the live path" signal.
  var pulseLoopTimer  = null;
  var pulseLoopEdges  = [];          // [{src: node, tgt: node}]
  var PULSE_LOOP_MS   = 3200;        // re-fire interval — 1 cycle then breath

  // [PR camera-glow, 2026-05-09] node halos — soft glowing sprite
  // around each active path node, scale + opacity pulsing on a sine
  // so the node "breathes". Replaces the static "active node" feel
  // with the wrap-around glow the user described.
  var nodeHalos       = new Map();   // nodeId → THREE.Sprite

  // Spacing constant — radius scales with sqrt(N).
  var SPHERE_K  = 24;
  var PULSE_MS  = 650;
  var GLOW_MS   = 4200;
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
    if (!apiKey) { setLoginError('API key required (set on chat page or paste here)'); return; }
    try {
      var r = await fetch(API + '/login/', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ username: id, password: pw, api_key: apiKey }),
      });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok) { setLoginError(j.detail || ('Login failed (' + r.status + ')')); return; }
      var tok  = j.access_token || j.token || '';
      var role = j.role || 'external';
      if (!tok)              { setLoginError('No token returned'); return; }
      if (role !== 'admin')  { setLoginError('Admin role required (got: ' + role + ')'); return; }
      token = tok;
      localStorage.setItem('james_token', token);
      localStorage.setItem('james_role',  role);
      hideLogin();
      bootstrap();
    } catch (e) {
      setLoginError(String(e));
    }
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
      // activePathEdges (no expiry) is the primary "lit" state.
      // afterGlow (time-based) is preserved as a brief visual "echo" on
      // a fresh re-fire so the user sees animation, but the path stays
      // visually lit afterward via activePathEdges.
      // [#4-1 d] hub-touching links carry slightly more presence.
      .linkColor(function (l) {
        var k = edgeKey(linkSrc(l), linkTgt(l));
        if (activePathEdges.has(k) ||
            (afterGlow.has(k) && afterGlow.get(k) > performance.now())) {
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
        if (activePathEdges.has(k) ||
            (afterGlow.has(k) && afterGlow.get(k) > performance.now())) {
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
      setTimeout(function () { spawnPulse(node, item.neighbor); }, stepMs);
      stepMs += STEP_GAP / 2;   // slightly faster than path replay
      loopEdges.push({ src: node, tgt: item.neighbor });
    });

    // Re-trigger force-graph render so links re-color.
    if (graph) {
      graph.linkColor(graph.linkColor());
      graph.linkWidth(graph.linkWidth());
    }

    renderNeighborPanel(node, neighbors);

    // [PR mobile-loop-search] keep the neighborhood lit — pulses re-
    // fire every PULSE_LOOP_MS until next click clears.
    setTimeout(function () { startPulseLoop(loopEdges); }, stepMs + 400);
  }

  function renderNeighborPanel(centerNode, neighbors) {
    var panel = document.getElementById('neighbor-panel');
    if (!panel) return;
    panel.style.display = 'block';
    var rows = neighbors.slice(0, 50).map(function (item) {
      var rel = (item.edge && item.edge.type) || 'RELATED_TO';
      var arrow = item.direction === 'out' ? '→' : '←';
      // Pre-compute the safe id for inline onclick (id is system-generated
      // hex, but use JSON.stringify defense regardless).
      var idJs = JSON.stringify(item.neighbor.id);
      return '<div class="np-item" onclick="onNeighborClick(' + idJs + ')">' +
             '<span class="np-arrow">' + arrow + '</span>' +
             '<span class="np-name">' + escapeHtml(item.neighbor.name || '?') + '</span>' +
             '<span class="np-rel">' + escapeHtml(rel) + '</span>' +
             '</div>';
    }).join('');
    if (neighbors.length === 0) {
      rows = '<div class="np-empty">연결된 이웃 없음</div>';
    }
    panel.innerHTML =
      '<button class="np-close" onclick="closeNeighborPanel()" ' +
      'title="닫기">×</button>' +
      '<div class="np-title">🔗 ' + escapeHtml(centerNode.name || '?') + '</div>' +
      '<div class="np-meta">' + neighbors.length + '개 직접 연결' +
      (neighbors.length > 50 ? ' (50개까지 표시)' : '') + '</div>' +
      '<div class="np-list">' + rows + '</div>';
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

  // ─── [PR explorer] Query reasoning overlay ──────────────────────
  // Same vibe as the chat page brain animation, simplified — no
  // /trace/poll polling, just a steady "추론 중" pulse during the
  // /query/ inflight wait. Once paths arrive, activatePath takes
  // over with sprite pulses on graph edges (already wired).
  function showReasoningOverlay() {
    var ov = document.getElementById('query-reasoning-overlay');
    if (!ov) return;
    ov.innerHTML =
      '<span class="qr-brain" aria-hidden="true">' +
      '<svg viewBox="0 0 24 24" width="22" height="22">' +
      '<path d="M5 7 Q5 4 8 4 L16 4 Q19 4 19 7 L19 16 Q19 19 16 19 ' +
      'L8 19 Q5 19 5 16 Z" fill="none" stroke="currentColor" ' +
      'stroke-width="1.4"/>' +
      '<line x1="12" y1="2" x2="12" y2="4" stroke="currentColor" ' +
      'stroke-width="1.4"/>' +
      '<circle cx="12" cy="2" r="1" fill="currentColor"/>' +
      '<circle class="qr-neuron qr-n1" cx="8.5"  cy="8"  r="1.6" ' +
      'fill="currentColor"/>' +
      '<circle class="qr-neuron qr-n2" cx="15.5" cy="8"  r="1.6" ' +
      'fill="currentColor"/>' +
      '<circle class="qr-neuron qr-n3" cx="12"   cy="14" r="1.6" ' +
      'fill="currentColor"/>' +
      '</svg></span>' +
      '<span class="qr-text">JAMES 추론 중</span>';
    ov.style.display = 'inline-flex';
  }

  function hideReasoningOverlay() {
    var ov = document.getElementById('query-reasoning-overlay');
    if (!ov) return;
    ov.style.display = 'none';
    ov.innerHTML = '';
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
    listEl.innerHTML = rows.map(function (n) {
      var idJs = JSON.stringify(n.id);
      return '<div class="tsd-row" onclick="onSearchRowClick(' + idJs + ')">' +
             '<span class="tsd-type">' + escapeHtml(n.type || '?') + '</span>' +
             '<span class="tsd-name">' + escapeHtml(n.name || '?') + '</span>' +
             '<span class="tsd-deg">' + (n.degree || 0) + '</span>' +
             '</div>';
    }).join('');
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

  // ─── Path-string parser ────────────────────────────────────
  // Format produced by core/graph_engine.py:expand_dynamic:
  //   "Name1 -[REL_TYPE(w=0.8)]→ Name2 -[REL_TYPE(w=0.6)]→ Name3"
  // We extract consecutive (src, rel, tgt) hops, in order.
  function parsePath(pathStr) {
    if (!pathStr || typeof pathStr !== 'string') return [];
    var hops = [];
    // Normalize the arrow — split on "→".
    var tokens = pathStr.split('→');
    if (tokens.length < 2) return [];

    // For each gap, the left side ends with " -[REL(w=W)]" and the
    // right side starts with " <Name>". The first token is " <Source>".
    var leftName = stripBracket(tokens[0]).trim();
    for (var i = 1; i < tokens.length; i++) {
      var seg = tokens[i];
      // Right side: name up to next " -[" (or end).
      var nextBracket = seg.indexOf('-[');
      var rightName, restAfter;
      if (nextBracket >= 0) {
        rightName = seg.slice(0, nextBracket).trim();
        restAfter = seg.slice(nextBracket);
      } else {
        rightName = seg.trim();
        restAfter = '';
      }
      // The relation that produced this hop is on the LEFT of the arrow,
      // i.e. embedded in tokens[i-1] (or in the previous restAfter).
      var prevSeg = i === 1 ? tokens[0] : tokens[i - 1];
      var rel = extractRelation(prevSeg);
      if (leftName && rightName) {
        hops.push({
          srcName: leftName,
          tgtName: rightName,
          rel:     rel.type,
          weight:  rel.weight,
        });
      }
      // Next hop's left-name = current right-name.
      leftName = rightName;
    }
    return hops;
  }

  function stripBracket(s) {
    // Drop a trailing " -[REL(w=W)]" suffix if present.
    var idx = s.lastIndexOf('-[');
    if (idx < 0) return s;
    return s.slice(0, idx);
  }
  function extractRelation(seg) {
    // Find the LAST -[REL(w=W)] in this segment (since the arrow follows it).
    var m = /-\[\s*([A-Z_]+)\s*\(\s*w\s*=\s*([\d.]+)\s*\)\s*\]\s*$/.exec(seg.trim());
    if (m) return { type: m[1], weight: parseFloat(m[2]) || 0 };
    return { type: 'RELATED_TO', weight: 0.7 };
  }

  // Resolve a hop's name pair → node ids using the snapshot index.
  function resolveHop(hop) {
    var s = nameIdx.get(normalizeName(hop.srcName)) || [];
    var t = nameIdx.get(normalizeName(hop.tgtName)) || [];
    if (!s.length || !t.length) return null;
    // If multiple matches, prefer the pair that has a registered edge.
    for (var i = 0; i < s.length; i++) {
      for (var j = 0; j < t.length; j++) {
        if (edgeIdx.has(edgeKey(s[i].id, t[j].id))) {
          return { src: s[i], tgt: t[j], hasEdge: true };
        }
      }
    }
    // Otherwise return the first pair (sprite still flies, edge isn't lit).
    return { src: s[0], tgt: t[0], hasEdge: false };
  }

  // ─── [#4-2 c-label/f] Sprite text labels ───────────────────────
  // Canvas-rendered text → Three.Sprite. Cheap (one canvas per node,
  // disposed when label hidden). Only hubs + path-traversed nodes get
  // labels; this keeps the visible label count to typically <30, which
  // avoids the readability mess of labeling all 185 nodes.
  function createTextSprite(text, color) {
    if (typeof THREE === 'undefined') return null;
    var canvas = document.createElement('canvas');
    canvas.width = 256; canvas.height = 64;
    var ctx = canvas.getContext('2d');
    ctx.font = 'bold 24px Inter, "Pretendard", system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    // Drop-shadow for readability against any background.
    ctx.shadowColor = 'rgba(0,0,0,0.85)';
    ctx.shadowBlur = 6;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 0;
    ctx.fillStyle = color || '#ffffff';
    ctx.fillText(text || '?', 128, 32);
    var tex = new THREE.CanvasTexture(canvas);
    tex.minFilter = THREE.LinearFilter;     // canvas isn't power-of-two
    var mat = new THREE.SpriteMaterial({
      map:        tex,
      transparent: true,
      depthTest:   false,                    // always on top of edges
      depthWrite:  false,
    });
    var sprite = new THREE.Sprite(mat);
    sprite.scale.set(36, 9, 1);              // wide, thin
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

  // ─── [#4-2 e/j] Path activation & reset ─────────────────────────
  // activate(answerEntry) lights the entry's edges + collects nodes for
  // labeling. Replays the sprite pulse animation. Persists until
  // another activate() or clearActivePath().
  function activatePath(entry) {
    if (!entry) return;
    clearActivePath(/*skipRefresh*/true);
    activeAnswerId = entry.id;
    var hopsAll = [];
    (entry.paths || []).forEach(function (p) {
      var hops = parsePath(p);
      hops.forEach(function (h) {
        var resolved = resolveHop(h);
        if (!resolved) return;
        hopsAll.push(resolved);
        if (resolved.hasEdge) {
          activePathEdges.add(edgeKey(resolved.src.id, resolved.tgt.id));
        }
        activePathNodes.add(resolved.src.id);
        activePathNodes.add(resolved.tgt.id);
      });
    });
    refreshLabels();
    refreshNodeHalos();   // [PR camera-glow] halos around path nodes
    // Replay sprite pulses for visual cue (but the lit edges persist).
    var stepMs = 0;
    var lastTgt = null;
    var loopEdges = [];
    hopsAll.forEach(function (resolved) {
      setTimeout(function () { spawnPulse(resolved.src, resolved.tgt); }, stepMs);
      stepMs += STEP_GAP;
      lastTgt = resolved.tgt;
      loopEdges.push({ src: resolved.src, tgt: resolved.tgt });
    });
    if (graph) {
      graph.linkColor(graph.linkColor());
      graph.linkWidth(graph.linkWidth());
    }
    // Camera nudge to terminal node so the user sees where the path ends.
    if (lastTgt) {
      setTimeout(function () { pulseTerminalNode(lastTgt); }, stepMs + 200);
    }
    // [PR mobile-loop-search] keep the path alive — replays pulses
    // every PULSE_LOOP_MS until next question or node click clears.
    setTimeout(function () { startPulseLoop(loopEdges); }, stepMs + 400);
  }

  function clearActivePath(skipRefresh) {
    activePathEdges.clear();
    activePathNodes.clear();
    activeAnswerId = null;
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

    // [PR camera-glow] use the soft gradient texture for a comet-like
    // wrap-around glow instead of the hard square sprite.
    var color = getCss('--brand-2', '#4fc3f7');
    var tex = getGlowTexture(color);
    var spriteMat = new THREE.SpriteMaterial({
      map:         tex,
      color:       0xffffff,        // texture carries the color
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
      sprite:  sprite,
      src:     srcNode,
      tgt:     tgtNode,
      startMs: performance.now(),
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
        live.push(p);
      }
    }
    pulses = live;

    // Drop expired afterglow keys so links re-render in their idle color.
    if (afterGlow.size) {
      var dirty = false;
      afterGlow.forEach(function (until, key) {
        if (until <= now) { afterGlow.delete(key); dirty = true; }
      });
      if (dirty && graph) {
        // Cheap re-trigger so linkColor/linkWidth re-evaluate.
        graph.linkColor(graph.linkColor());
      }
    }
    // [#4-2 c-label/f] keep labels glued to their nodes per frame.
    tickLabelPositions();
    // [PR camera-glow] halo position-track + sine pulse per frame.
    tickNodeHalos();
    requestAnimationFrame(pulseTick);
  }

  function pulseTerminalNode(node) {
    if (!node || !graph || typeof THREE === 'undefined') return;
    // No-op if node is invisible / pre-layout. The sprite at the node
    // location is already implicit via the existing graph render; we
    // settle for a brief camera focus hint.
    onNodeClick(node);
  }

  function animatePaths(paths) {
    if (!Array.isArray(paths) || !paths.length) return;
    var allHops = [];
    var lastTgt = null;
    paths.forEach(function (p) {
      var hops = parsePath(p);
      hops.forEach(function (h) { allHops.push(h); });
      if (hops.length) lastTgt = hops[hops.length - 1].tgtName;
    });

    var stepMs = 0;
    allHops.forEach(function (h) {
      var resolved = resolveHop(h);
      if (!resolved) return;
      var key = edgeKey(resolved.src.id, resolved.tgt.id);
      setTimeout(function () {
        spawnPulse(resolved.src, resolved.tgt);
        if (resolved.hasEdge) {
          afterGlow.set(key, performance.now() + GLOW_MS);
          if (graph) graph.linkColor(graph.linkColor());
        }
      }, stepMs);
      stepMs += STEP_GAP;
    });

    // Camera nudge to the terminal entity so the user sees the endpoint.
    if (lastTgt) {
      var nodes = nameIdx.get(normalizeName(lastTgt));
      if (nodes && nodes.length) {
        setTimeout(function () { pulseTerminalNode(nodes[0]); }, stepMs + 200);
      }
    }
  }

  // ─── Query ─────────────────────────────────────────────────
  window.askQuestion = async function () {
    var box = document.getElementById('qbox');
    var btn = document.getElementById('ask-btn');
    var q = (box.value || '').trim();
    if (!q) return;
    // [#4-2 j] new question → clear current path before new one fires.
    clearActivePath();
    btn.disabled = true;
    btn.textContent = '...';
    // [PR explorer] reasoning overlay during the inflight wait —
    // mirrors the brain-pulse vibe of the chat page so the user knows
    // JAMES is thinking, not stuck.
    showReasoningOverlay();
    try {
      var r = await fetch(API + '/query/', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          api_key:     apiKey,
          question:    q,
          session_id:  'graph-viz',
        }),
      });
      var j = await r.json();
      var entry;
      if (!r.ok) {
        entry = recordAnswer(q, '[' + r.status + '] ' + (j.detail || 'error'), []);
      } else {
        entry = recordAnswer(q, j.answer || '(empty)', j.graph_paths || []);
      }
      renderAnswerCard(entry);
      activatePath(entry);
    } catch (e) {
      var errEntry = recordAnswer(q, String(e), []);
      renderAnswerCard(errEntry);
    } finally {
      hideReasoningOverlay();
      btn.disabled = false;
      btn.textContent = t('graph.ask') || 'Ask';
      box.value = '';                     // clear input for next question
    }
  };

  // [#4-2 h] push a new entry into in-memory history. Returns the entry.
  function recordAnswer(q, a, paths) {
    historyCounter += 1;
    var entry = {
      id:       'h' + historyCounter,
      question: q,
      answer:   a,
      paths:    Array.isArray(paths) ? paths.slice() : [],
      ts:       Date.now(),
    };
    answerHistory.unshift(entry);          // newest first
    return entry;
  }

  // [#4-2 g] render the current answer in the card body. Card has a
  // collapse toggle (g) and a history list (h). The list items are
  // clickable (i).
  function renderAnswerCard(entry) {
    var card = document.getElementById('answer-card');
    if (!card) return;
    card.style.display = 'block';
    card.classList.remove('ac-collapsed');   // expand on every new answer
    document.getElementById('ac-q').textContent = entry.question || '';
    document.getElementById('ac-a').textContent = entry.answer  || '';
    var pathsEl = document.getElementById('ac-paths');
    if (pathsEl) {
      pathsEl.innerHTML = '';
      (entry.paths || []).slice(0, 8).forEach(function (p) {
        var d = document.createElement('div');
        d.textContent = '• ' + p;
        pathsEl.appendChild(d);
      });
    }
    renderHistoryList();
  }

  // [#4-2 h/i] history list rendering. Each item shows the question
  // preview + a click handler that re-activates the entry.
  function renderHistoryList() {
    var listEl = document.getElementById('ac-history');
    if (!listEl) return;
    listEl.innerHTML = '';
    if (answerHistory.length <= 1) return;
    var hdr = document.createElement('div');
    hdr.className = 'ac-history-hdr';
    hdr.textContent = '이전 질문 (' + (answerHistory.length - 1) + ')';
    listEl.appendChild(hdr);
    answerHistory.slice(1).forEach(function (e) {   // skip [0] (current)
      var row = document.createElement('div');
      row.className = 'ac-history-row';
      row.dataset.id = e.id;
      if (activeAnswerId === e.id) row.classList.add('active');
      row.title = e.question + '\n\n' + (e.answer || '').slice(0, 140);
      row.textContent = '▸ ' + (e.question.length > 38
        ? e.question.slice(0, 38) + '...'
        : e.question);
      row.addEventListener('click', function () { onHistoryClick(e.id); });
      listEl.appendChild(row);
    });
  }

  // [#4-2 i] history item click → swap card content + re-fire path.
  function onHistoryClick(entryId) {
    var entry = answerHistory.find(function (e) { return e.id === entryId; });
    if (!entry) return;
    // Move clicked entry to top so renderHistoryList shows current state.
    answerHistory = answerHistory.filter(function (e) { return e.id !== entryId; });
    answerHistory.unshift(entry);
    renderAnswerCard(entry);
    activatePath(entry);
  }

  // [#4-2 g] collapse/expand toggle. CSS rule on .ac-collapsed hides
  // body sections; the title row stays visible.
  window.toggleAnswerCard = function () {
    var card = document.getElementById('answer-card');
    if (!card) return;
    card.classList.toggle('ac-collapsed');
    var btn = document.getElementById('ac-toggle');
    if (btn) btn.textContent = card.classList.contains('ac-collapsed') ? '▲' : '▼';
  };

  // [#4-2 j] close the card AND reset to default graph mode (no lit
  // path). History is preserved — close just hides the card.
  window.closeAnswer = function () {
    document.getElementById('answer-card').style.display = 'none';
    clearActivePath();
  };

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

  function start() {
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
