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
  var afterGlow = new Map();       // link key → expireAtMs
  var hoverEl = null;

  // Spacing constant — radius scales with sqrt(N).
  var SPHERE_K  = 24;
  var PULSE_MS  = 650;
  var GLOW_MS   = 4200;
  var STEP_GAP  = 220;             // gap between consecutive edge pulses

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
      .nodeColor(function (n) { return typeColor(n.type); })
      .nodeOpacity(0.92)
      .nodeRelSize(3)
      .nodeVal(function (n) { return Math.max(1, Math.sqrt((n.degree || 0) + 1)); })
      .linkColor(function (l) {
        var k = edgeKey(linkSrc(l), linkTgt(l));
        if (afterGlow.has(k) && afterGlow.get(k) > performance.now()) {
          return getCss('--accent', '#6366f1');
        }
        return 'rgba(150,160,180,0.25)';
      })
      .linkOpacity(0.55)
      .linkWidth(function (l) {
        var k = edgeKey(linkSrc(l), linkTgt(l));
        return afterGlow.has(k) && afterGlow.get(k) > performance.now() ? 1.3 : 0.4;
      })
      .linkDirectionalParticles(0)
      .onNodeHover(onNodeHover)
      .onNodeClick(onNodeClick);

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
    // Aim camera at the node.
    var distance = 240;
    var ratio = 1;
    var d = Math.hypot(node.x || 1, node.y || 1, node.z || 1);
    if (d > 0) ratio = (d + distance) / d;
    graph.cameraPosition(
      { x: (node.x || 0) * ratio, y: (node.y || 0) * ratio, z: (node.z || 0) * ratio },
      node, 700,
    );
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

  // ─── Pulse animation ───────────────────────────────────────
  function spawnPulse(srcNode, tgtNode) {
    if (!graph || !srcNode || !tgtNode) return;
    if (typeof THREE === 'undefined') return;
    var scene = graph.scene();
    if (!scene) return;

    var spriteMat = new THREE.SpriteMaterial({
      color:       new THREE.Color(getCss('--brand-2', '#4fc3f7')),
      transparent: true,
      opacity:     0.95,
      blending:    THREE.AdditiveBlending,
      depthWrite:  false,
    });
    var sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(8, 8, 1);
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
    btn.disabled = true;
    btn.textContent = '...';
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
      if (!r.ok) {
        showAnswer(q, '[' + r.status + '] ' + (j.detail || 'error'), []);
        return;
      }
      showAnswer(q, j.answer || '(empty)', j.graph_paths || []);
      animatePaths(j.graph_paths || []);
    } catch (e) {
      showAnswer(q, String(e), []);
    } finally {
      btn.disabled = false;
      btn.textContent = t('graph.ask') || 'Ask';
    }
  };

  function showAnswer(q, a, paths) {
    var card = document.getElementById('answer-card');
    document.getElementById('ac-q').textContent = q;
    document.getElementById('ac-a').textContent = a;
    var pathsEl = document.getElementById('ac-paths');
    pathsEl.innerHTML = '';
    if (paths && paths.length) {
      paths.slice(0, 8).forEach(function (p) {
        var d = document.createElement('div');
        d.textContent = '• ' + p;
        pathsEl.appendChild(d);
      });
    }
    card.style.display = 'block';
  }
  window.closeAnswer = function () {
    document.getElementById('answer-card').style.display = 'none';
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
