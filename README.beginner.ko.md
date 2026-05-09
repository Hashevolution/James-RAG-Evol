# 🚀 JAMES 처음 시작 가이드 (10살도 따라할 수 있어요)

> 이 문서는 컴퓨터 잘 모르는 분도 따라할 수 있도록 천천히 한 단계씩 설명해요.
> 막히면 이 문서의 **"막혔어요!" 섹션**을 보세요.

---

## 🤔 JAMES가 뭐예요?

JAMES는 **내 컴퓨터 안에서만 돌아가는 똑똑한 AI**예요.
- 내가 올린 PDF, 사진, 문서를 읽고 기억해요
- 나중에 그것에 대해 물어보면 답을 줘요
- **인터넷에 내 자료를 보내지 않아요** (집 안에서만 동작)

---

## ✅ 시작 전에 확인할 것

### 1. 내 컴퓨터가 충분히 좋은가요?

| 항목 | 최소 | 추천 |
|---|---|---|
| 메모리(RAM) | 16GB | 32GB |
| 저장공간 | 20GB 비어있어야 함 | 50GB |
| 운영체제 | Windows 10/11, macOS, Linux | 동일 |

> 💡 **잘 모르겠다고요?** 윈도우 키 + Pause 키를 같이 누르면 RAM이 보여요.
> 16GB 미만이면 작동하지 않을 수 있어요.

### 2. 인터넷 필요해요? (처음 한 번만)
- 처음 설치할 때만 인터넷 필요해요 (프로그램 다운로드)
- 다 설치한 후엔 인터넷 없어도 동작해요

---

## 📥 1단계: 필요한 것 3개 설치하기

세 가지를 설치해야 해요. **순서대로** 해주세요.

### (1) Python 설치 (프로그래밍 언어)

1. https://www.python.org/downloads/ 열기
2. 가운데 큰 노란색 버튼 **"Download Python 3.13.x"** 누르기 (3.11 이상이면 OK)
3. 다운로드된 파일 더블클릭
4. ⚠️ **중요**: 첫 화면 맨 아래에 **"Add python.exe to PATH"** 체크박스가 있어요. 꼭 체크하세요!
5. **"Install Now"** 누르기
6. 끝나면 **"Close"**

**잘 됐는지 확인:**
- Windows 키 누르고 `cmd` 입력 → 검은 창(명령 프롬프트) 열기
- 검은 창에 입력: `python --version`
- `Python 3.13.0` 같은 게 나오면 성공! ✅

### (2) Ollama 설치 (AI 모델 돌리는 프로그램)

1. https://ollama.com/download 열기
2. 본인 운영체제 클릭 (Windows / macOS / Linux)
3. 다운로드된 파일 더블클릭 → 그냥 따라 설치
4. 설치 끝나면 자동으로 백그라운드에서 동작 시작

**잘 됐는지 확인:**
- 검은 창에 입력: `ollama --version`
- `ollama version 0.x.x` 같은 게 나오면 성공! ✅

### (3) Git 설치 (이 프로젝트 다운로드용)

1. https://git-scm.com/downloads 열기
2. 본인 운영체제 클릭
3. 다운로드 → 그냥 **"Next"** 계속 누르기 (모든 옵션 기본값으로 OK)

**잘 됐는지 확인:**
- 검은 창에 입력: `git --version`
- `git version 2.x.x` 같은 게 나오면 성공! ✅

---

## 📂 2단계: JAMES 다운로드

검은 창(명령 프롬프트)을 열고 다음을 한 줄씩 입력하세요.

### Windows

```powershell
cd %USERPROFILE%\Documents
git clone https://github.com/Hashevolution/James-RAG-Evol-v010
cd James-RAG-Evol-v010
```

### macOS / Linux

```bash
cd ~/Documents
git clone https://github.com/Hashevolution/James-RAG-Evol-v010
cd James-RAG-Evol-v010
```

> 💡 한 줄씩 입력하고 **엔터**를 누르세요.
> 마지막 줄까지 잘 됐다면, 검은 창에 폴더 이름이 보일 거예요.

---

## 🔑 3단계: 비밀 키 만들기 (.env 파일)

JAMES는 보안을 위해 두 가지 비밀번호가 필요해요. **자동으로 만들어보겠습니다.**

### Windows (PowerShell 사용)

검은 창에서:

```powershell
# 1) 비밀번호 자동 생성
$apiKey = -join ((48..57) + (97..122) | Get-Random -Count 24 | ForEach-Object {[char]$_})
$jwtSecret = -join ((48..57) + (97..122) + (65..90) | Get-Random -Count 40 | ForEach-Object {[char]$_})

# 2) .env 파일에 자동 기록
@"
JAMES_API_KEY=$apiKey
JAMES_JWT_SECRET=$jwtSecret
"@ | Out-File -FilePath .env -Encoding utf8

# 3) 만든 API 키 보기 (이거 기억해두세요!)
Write-Host "내 API 키: $apiKey"
```

### macOS / Linux

```bash
# 1) 비밀번호 자동 생성 + .env 작성
API_KEY=$(openssl rand -hex 12)
JWT_SECRET=$(openssl rand -base64 32 | tr -d '\n')
cat > .env <<EOF
JAMES_API_KEY=$API_KEY
JAMES_JWT_SECRET=$JWT_SECRET
EOF

# 2) 만든 API 키 보기
echo "내 API 키: $API_KEY"
```

> ⚠️ 보여진 **API 키는 종이에 적어두세요!** 나중에 로그인할 때 필요해요.

---

## 📦 4단계: 프로그램 부품 설치

검은 창에서:

```powershell
pip install -r requirements.txt
```

> ⏳ 5~15분 정도 걸려요. 빨간 줄이 가끔 나와도 보통 괜찮아요.
> 끝까지 끝나길 기다리세요.

**잘 됐는지 확인:** 마지막에 `Successfully installed ...` 같은 글이 나오면 성공! ✅

---

## 🤖 5단계: AI 모델 다운로드

```powershell
ollama pull gemma3:4b
```

> ⏳ 모델 크기는 약 3GB. 인터넷 속도에 따라 5~30분.
> 진행률 (10%, 50%, 100%) 이 보여요.

**잘 됐는지 확인:** `success` 글자가 나오면 OK! ✅

---

## 🎉 6단계: JAMES 시작!

```powershell
python server_llmwiki.py
```

**잘 됐는지 확인:** 다음과 비슷한 글들이 나오고, **검은 창이 안 닫히면** 성공이에요:

```
[CONFIG] PROJECT JAMES ready
[VECTOR_STORE] VectorStore 초기화 완료
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## 🌐 7단계: 브라우저로 접속!

1. **검은 창은 그대로 둔 채로** (닫지 마세요!)
2. 크롬, 엣지, 사파리 등 브라우저 열기
3. 주소창에 입력: `http://localhost:8000`
4. JAMES 화면이 나오면 성공! 🎉

### 첫 로그인

1. 화면 어딘가에 **로그인 버튼**이 있어요. 누르기
2. **API 키** 칸에 3단계에서 적어둔 키 입력
3. **사용자 이름** 칸: `admin`
4. **비밀번호** 칸: `admin123` (최초 기본값, 나중에 바꿀 수 있어요)
5. **로그인** 버튼

---

## 📤 8단계: 내 PDF 업로드 + 질문해보기

### 파일 올리기

1. JAMES 화면에 **📎 클립 아이콘** 또는 **"파일 추가"** 영역 찾기
2. 본인 PDF 파일 드래그 (끌어다 놓기) 또는 클릭해서 선택
3. **업로드** 누르기
4. ⏳ JAMES가 PDF를 읽고 분석 (1~3분)

> 💡 처음에는 **5~10MB 정도의 작은 PDF** 1개로 시작해보세요.
> 큰 파일은 나중에.

### 질문해보기

1. 화면 아래 **채팅 입력창**에 질문 쓰기
2. 예시: "이 문서의 주요 내용은?"
3. 엔터 또는 **전송** 누르기
4. ⏳ 30초~2분 후 답이 나와요

> 💡 **답이 너무 느리거나 이상하다고요?** 컴퓨터가 작아서 그래요.
> 정상이에요. 아래 "막혔어요!" 섹션을 보세요.

---

## 🕸️ 9단계 (선택): 추론 그래프 보기

JAMES가 PDF 안의 정보들이 서로 어떻게 연결돼 있는지 그림으로 보여줘요.

1. 브라우저에 입력: `http://localhost:8000/admin/graph`
2. **로그인 모달**이 나오면:
   - 사용자 이름 `admin`
   - 비밀번호 `admin123`
   - API 키 (3단계에서 적어둔 것)
3. 동그란 공 안에 점들이 보여요
4. **마우스로 드래그** → 회전!
5. **마우스 휠 스크롤** → 줌인/줌아웃
6. 점에 마우스 올리면 이름 보여요
7. 아래 **질문 입력창**에 질문 → 추론 경로가 청록색으로 빛나요!

---

## ⏹️ 끄는 방법

검은 창(서버가 돌고 있는 창)에서:
- **Ctrl + C** 동시에 누르기
- 끝!

다시 켜려면 **6단계**부터 (`python server_llmwiki.py`).

---

## 🆘 막혔어요! 자주 겪는 문제 10가지

### 1. "python을 찾을 수 없습니다" 또는 "python is not recognized"
→ **Python 설치할 때 "Add to PATH" 체크 안 했어요.**
   해결: Python을 다시 설치하면서 그 박스를 꼭 체크하세요.

### 2. "git을 찾을 수 없습니다"
→ **Git 설치 후 검은 창을 다시 열지 않았어요.**
   해결: 검은 창 닫고 새로 열기.

### 3. "ollama 명령을 찾을 수 없습니다"
→ Ollama 설치 후 컴퓨터 재시작 필요할 수 있어요.

### 4. `pip install` 중 빨간 글씨가 잔뜩 나와요
→ 보통 괜찮아요. 마지막에 `Successfully installed`만 있으면 OK.
   진짜 실패하면 `ERROR:`로 시작하는 줄이 나와요.

### 5. `pip install`이 느려요
→ 정상. 5~15분 걸려요. 빠른 인터넷이면 더 빨라요.

### 6. 답변이 너무 느려요 (1분 넘게 걸림)
→ 컴퓨터가 모델보다 작아서 그래요.
   해결: 더 작은 모델로 바꿔보세요. 검은 창에서:
   ```powershell
   ollama pull gemma3:1b
   ```
   그리고 `.env` 파일에 한 줄 추가:
   ```
   JAMES_LLM_MODEL=gemma3:1b
   ```
   서버 재시작.

### 7. 답변이 이상해요 (말이 안 맞아요)
→ 1b 같은 작은 모델은 한국어가 약해요. 가능하면 4b 이상 사용.

### 8. 브라우저에서 `http://localhost:8000`이 열리지 않아요
→ 6단계 검은 창에 `Uvicorn running on...` 메시지가 진짜 나왔는지 확인.
   안 나왔으면 빨간 에러 메시지를 처음 도와준 사람에게 보여주세요.

### 9. PDF 업로드 후 아무것도 안 일어나요
→ 1~3분 정도 기다려보세요. 큰 PDF는 더 오래 걸려요.
   여전히 변화 없으면 검은 창의 글자들 캡처해서 보여주세요.

### 10. "포트 8000이 이미 사용 중"
→ 서버가 이미 켜져 있어요. 검은 창 두 개 열려있는지 확인.
   하나로 충분해요.

---

## 📋 체크리스트 (전부 ✓ 되면 검증 끝!)

설치 + 시작:
- [ ] Python 설치 + `python --version` 확인
- [ ] Ollama 설치 + `ollama --version` 확인  
- [ ] Git 설치 + `git --version` 확인
- [ ] JAMES 다운로드 (`git clone` 끝남)
- [ ] `.env` 파일 만들기 (API 키 적어둠)
- [ ] `pip install -r requirements.txt` 끝남
- [ ] `ollama pull gemma3:4b` 끝남
- [ ] `python server_llmwiki.py` → `Uvicorn running` 보임

브라우저 사용:
- [ ] `http://localhost:8000` 열림
- [ ] 로그인 성공 (`admin` / `admin123` / API 키)
- [ ] PDF 1개 업로드 성공
- [ ] PDF 내용 질문 → 답 받음
- [ ] `/admin/graph` 그래프 화면 열어봄 (선택)

---

## 💬 피드백 요청 (개발자에게 도움 주세요)

이 가이드를 따라하면서 막힌 부분, 헷갈린 단계, 안 되는 명령어가 있으면
**개발자(이 프로젝트 만든 사람)에게 알려주세요**.

알려주면 좋은 것:
- 몇 단계에서 막혔는지 (예: "5단계 ollama pull에서 실패")
- 검은 창에 나타난 빨간 에러 글자 (사진/캡처)
- 본인의 OS 종류 (Windows 11, macOS Ventura 등)
- "이 단어 무슨 뜻이야?" 같은 질문도 OK

이게 v0.2 검증의 가장 중요한 부분이에요. 잘 모르는 부분이 곧 개선할 부분.

---

## 📚 더 알고 싶다면

- **자세한 영문 README**: [README.md](README.md)
- **자세한 한글 README**: [README.ko.md](README.ko.md)
- **보안 설명**: [SECURITY.md](SECURITY.md)

---

**축하합니다! 🎉 JAMES를 처음 돌려본 분이라면, v0.2의 두 번째 사용자가 된 거예요!**
