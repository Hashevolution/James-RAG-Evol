# Cloudflare Quick Tunnel 로 외부 데모 공개하기

> 대상 시나리오: **1~2명의 신뢰 가능한 외부인** 에게 단기간 JAMES
> 웹 UI 를 보여주기 위한 임시 공개. 영구 배포·다중 사용자 운영은
> 대상이 아닙니다.
> 전제: `SECURITY.md` 가 명시하듯 JAMES 는 **production-ready 가
> 아닙니다.** 본 가이드는 데모용 임시 노출에 한정됩니다.

---

## 1. 동작 원리

```
3자 브라우저
   │ HTTPS (Cloudflare TLS)
   ▼
*.trycloudflare.com (랜덤 호스트)
   │ 암호화 터널 (outbound only, NAT/방화벽 변경 불필요)
   ▼
cloudflared (호스트 머신)
   │ HTTP
   ▼
127.0.0.1:8000  ← server_llmwiki.py  (바인딩 변경 불필요)
```

핵심:

- **공유기 포트포워딩 불필요**: `cloudflared` 가 Cloudflare 엣지로
  outbound TLS 연결만 만듭니다.
- **JAMES 코드 변경 불필요**: `uvicorn` 은 `127.0.0.1:8000` 그대로
  바인딩한 채, 터널만이 유일한 외부 경로가 됩니다.
- **rate limit / audit 정확성 유지**: `server_llmwiki.py` 의
  `get_client_ip` (line 443) 가 이미 `X-Forwarded-For` 를 신뢰하므로,
  Cloudflare 가 주입한 헤더로 실제 클라이언트 IP 가 기록됩니다.
  단, 이 헤더 신뢰는 **터널이 유일한 입구일 때만 안전합니다**
  (8000 포트가 외부에서 직접 닿으면 헤더 스푸핑 가능 → 본 가이드는
  127.0.0.1 바인딩 유지를 전제).

---

## 2. 사전 준비

- 호스트 머신에 JAMES 가 정상 기동 (`python server_llmwiki.py` →
  `http://localhost:8000` 접속 가능)
- Linux/macOS 셸 권한
- 인터넷 outbound 가능 (대부분 환경에서 가능)
- Cloudflare 계정 / 도메인 **불필요** (Quick Tunnel 사용)

---

## 3. cloudflared 설치

### Linux (Debian/Ubuntu)

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
cloudflared --version
```

### macOS

```bash
brew install cloudflared
```

### 기타 OS

공식 문서 참고: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

---

## 4. JAMES 측: 데모용 계정 발급

3자에게는 **항상 별도 계정** 을 발급합니다 (공용 계정 금지 — 감사
추적 불가).

권장 역할: `external` (가장 낮은 권한). 데모 시나리오에 따라
`employee` 도 허용 가능하나, `manager` 이상 금지.

계정 생성은 운영자가 `/signup/` 또는 admin 계정으로 직접 수행한 뒤,
다음을 3자에게 전달:

- 데모 URL (다음 단계에서 생성)
- username
- 1회용 초기 비밀번호 (3자가 첫 로그인 후 즉시 변경 안내)
- 데모 종료 예정 시각

---

## 5. Quick Tunnel 기동

JAMES 서버가 떠 있는 상태에서 별도 터미널에서 실행:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

수초 후 출력에 다음과 같은 라인이 나타납니다:

```
Your quick Tunnel has been created! Visit it at:
https://random-words-here.trycloudflare.com
```

이 URL 을 3자에게 전달하면 즉시 접속 가능합니다. 터미널을 닫거나
`Ctrl+C` 를 누르면 URL 은 즉시 무효화됩니다.

### 백그라운드 실행 (선택)

데모 세션을 길게 유지해야 한다면:

```bash
nohup cloudflared tunnel --url http://127.0.0.1:8000 > /tmp/cf-tunnel.log 2>&1 &
# URL 확인:
grep trycloudflare /tmp/cf-tunnel.log
```

종료:

```bash
pkill -f "cloudflared tunnel"
```

---

## 6. 데모 종료 후 정리 (체크리스트)

- [ ] `cloudflared` 프로세스 종료 (URL 즉시 무효화)
- [ ] 데모 계정 비활성화 또는 삭제
- [ ] `james_audit.db` 의 해당 사용자 활동 검토
- [ ] 데모 중 업로드된 문서가 있다면 삭제 정책 결정
- [ ] (선택) `cloudflared.log` 보존 또는 삭제

---

## 7. Quick Tunnel 의 한계 — 이것이 데모 전용인 이유

| 한계 | 영향 |
|---|---|
| **인증 게이트 없음** | URL 을 아는 사람은 누구나 JAMES 로그인 화면에 도달. JAMES 의 JWT 로그인이 유일한 방어선. |
| **URL 이 무작위·공개** | 비밀이 아닌 "obscurity". 검색엔진에 노출되면 누구나 발견 가능. URL 을 공개 채널(트위터·블로그)에 절대 게시 금지. |
| **Cloudflare Access 정책 적용 불가** | Quick Tunnel 은 zone 에 묶이지 않아 이메일 OTP 같은 사전 인증 게이트를 걸 수 없음. |
| **HTTP 스트리밍 idle timeout** | Cloudflare 기본 100초. LLM 응답이 100초를 넘기면 끊길 수 있음. |
| **WebSocket 지원** | 가능하지만 연결 재수립 빈도가 로컬보다 높음. |
| **세션 지속성 없음** | `cloudflared` 가 죽으면 URL 도 사라짐 → 매번 새 URL. |

3명 이상이거나 반복 데모라면 **다음 단계로 이행** 을 검토:

1. 도메인을 Cloudflare 에 연결 → Named Tunnel
2. **Cloudflare Access (Zero Trust)** 로 이메일 OTP 인증 게이트
3. JAMES 에서 다중 데모 계정 운영 + 역할 격리

이 단계는 본 가이드 범위 밖이며, 그 시점에는
`docs/cloudflare-tunnel-production.md` 같은 별도 가이드로 분리하는
것이 적절합니다.

---

## 8. 보안 점검 요약

데모 직전 확인:

- [ ] `uvicorn` 이 `127.0.0.1:8000` 으로만 바인딩되어 있는지
      (`server_llmwiki.py:4659`) — `0.0.0.0` 으로 바꾸지 말 것
- [ ] 3자 계정의 역할이 `admin`/`manager` 가 아닌지
- [ ] `.env` 등 비밀 파일이 `frontend/` `static/` 에 노출되지 않는지
- [ ] `james_audit.db` 가 정상 기록 중인지
      (`SELECT * FROM audit ORDER BY ts DESC LIMIT 10`)
- [ ] 호스트 머신의 다른 로컬 서비스(예: Ollama 11434)는 별도
      바인딩으로 터널 외부에서 닿지 않는지 확인

데모 중 모니터링:

```bash
# 실시간 audit 로그
sqlite3 james_audit.db "SELECT ts,user_role,endpoint,security_event FROM audit ORDER BY ts DESC LIMIT 20;"
```
