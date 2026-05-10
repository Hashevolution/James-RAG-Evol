# JAMES — Demo Recording

Auto-records a 1~2 minute MP4 of the live JAMES web UI:
login → real question → answer with sources → graph viz → admin panel.

## Quick start (on your own PC, where Ollama actually works)

```bash
# one-time setup
pip install playwright
playwright install chromium
sudo apt install ffmpeg     # optional, converts webm → mp4

# start JAMES first
python server_llmwiki.py    # serves on http://localhost:8000

# in another shell:
JAMES_PW=<your-admin-password> python scripts/demo/record_demo.py
```

Output lands in `scripts/demo/recordings/james-demo-<timestamp>.{webm,mp4}`.

## Running it from the cloud (against a tunnel)

```bash
# on your PC:
cloudflared tunnel --url http://localhost:8000
# → grab the https://xxx.trycloudflare.com URL

# in the cloud session:
JAMES_URL=https://xxx.trycloudflare.com \
JAMES_USER=admin \
JAMES_PW=<your-admin-password> \
python scripts/demo/record_demo.py
```

## Customizing

| Env var | Default | What it controls |
|---|---|---|
| `JAMES_URL` | `http://localhost:8000` | Server endpoint |
| `JAMES_USER` | `admin` | Login id |
| `JAMES_PW` | *(empty — login skipped)* | Login password |
| `JAMES_DEMO_QUESTION` | `이 시스템의 핵심 보안 원칙 3가지를 설명하고 출처를 보여주세요.` | Question typed in the chat |

To swap the question for one specific to your dataset (e.g. an internal
policy your wiki actually contains), set `JAMES_DEMO_QUESTION`.

## What the script records

| Scene | Caption shown | Selector(s) used |
|---|---|---|
| Intro | Product one-liner | — |
| Login | "권한 검사" overlay | `#role-badge`, `#login-id`, `#login-pw`, `button.modal-btn.primary` |
| Ask | Types question, sends | `#chat-input`, `#send-btn` |
| Wait | "검색 → 그래프 → LLM 추론 진행 중…" | polls `#messages > div` count |
| Answer | Scrolls + highlights answer | `#messages` |
| Graph | Mouse-wiggle over canvas | `/graph`, `#graph-canvas` |
| Admin | RBAC / audit log view | `/admin` |
| Outro | "PoC 파트너 모집 중" | — |

## Limitations

- Mouse cursor is not recorded by Playwright headless. Captions and pauses
  carry the narrative instead.
- LLM response is awaited up to **90 s**. On slow CPUs with no GPU the
  scene will time out — re-run with a smaller model in `config.py`
  (e.g. `gemma2:2b` instead of `gemma4:e4b`).
- Designed for the v0.2 frontend (`frontend/index.html`, `graph.html`,
  `admin.html`). If those files change selectors, update
  `record_demo.py` accordingly.
