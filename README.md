# 📋 생기부 정보 자동 브리핑 봇

> 매일 오전 7시, star.moe.go.kr에서 최신 학생부 정보를 크롤링하여
> Claude로 A4 1장 분량으로 요약한 뒤 Notion에 자동으로 페이지를 생성합니다.

---

## 📂 파일 구조

```
star-notion-bot/
├── .github/
│   └── workflows/
│       └── daily_crawl.yml   ← GitHub Actions 스케줄러
├── crawl_star.py             ← 메인 스크립트
├── requirements.txt
└── README.md
```

---

## ⚙️ 1단계: Notion 통합(Integration) 토큰 발급

1. https://www.notion.so/my-integrations 접속
2. **"+ New integration"** 클릭
3. 이름: `star-briefinig-bot` (아무 이름 가능)
4. Workspace: AXIOM이 있는 워크스페이스 선택
5. **Submit** → `secret_xxxxx` 형태의 토큰 복사

### AXIOM 페이지에 통합 연결
1. Notion에서 **AXIOM** 메인 페이지 열기
2. 우상단 `···` 메뉴 → **Connections** → 방금 만든 통합 추가
3. URL에서 페이지 ID 복사:
   - `https://notion.so/AXIOM-<페이지ID>?v=...`
   - 페이지 ID = URL의 32자리 hex (하이픈 제외)
   - 예: `https://notion.so/abc123def456...` → ID는 `abc123def456...`

---

## ⚙️ 2단계: GitHub Secrets 설정

GitHub 레포 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret 이름 | 값 |
|------------|-----|
| `ANTHROPIC_API_KEY` | `sk-ant-...` |
| `NOTION_TOKEN` | `secret_...` (Notion 통합 토큰) |
| `NOTION_AXIOM_PAGE_ID` | AXIOM 페이지 ID (32자리) |

---

## ⚙️ 3단계: GitHub 레포 생성 & 코드 업로드

```bash
# 새 레포 만들기 (GitHub 웹에서 먼저 생성)
git init
git add .
git commit -m "초기 세팅: 생기부 브리핑 봇"
git remote add origin https://github.com/<your-username>/star-notion-bot.git
git push -u origin main
```

---

## ▶️ 4단계: 첫 실행 테스트

GitHub → **Actions** 탭 → **"📋 Daily 생기부 정보 브리핑"** → **"Run workflow"** 클릭

성공하면 Notion AXIOM 페이지 하위에 **"4. 생기부 정보"** 섹션이 생기고
오늘 날짜의 브리핑 페이지가 만들어집니다! 🎉

---

## 🕖 실행 시간

- **자동**: 매일 오전 7:00 KST
- **수동**: GitHub Actions에서 "Run workflow" 클릭

---

## 📊 브리핑 구성 (A4 1장)

```
# 📋 생기부 브리핑 YYYY.MM.DD

## 🎯 오늘의 핵심 포인트
## 📑 2026 기재요령 주요 내용  
## ❓ Q&A 트렌드 분석
## 💡 멘토링 실전 활용 팁
## ⚠️ 주의사항 / 자주 하는 실수
## 🔗 오늘의 참고 링크
```

---

## 🛠️ 로컬 테스트

```bash
pip install -r requirements.txt
playwright install chromium

export ANTHROPIC_API_KEY=sk-ant-...
export NOTION_TOKEN=secret_...
export NOTION_AXIOM_PAGE_ID=...

python crawl_star.py
```

---

## ❓ 트러블슈팅

**Q: Actions가 실행은 되는데 Notion 페이지가 안 생겨요**
→ AXIOM 페이지에 Notion 통합이 연결되어 있는지 확인 (1단계 마지막 부분)

**Q: `playwright install` 오류**
→ `playwright install-deps chromium` 먼저 실행

**Q: Notion 페이지 ID를 어디서 찾나요?**
→ AXIOM 페이지를 브라우저에서 열고 URL 확인:
  `https://notion.so/workspace/Title-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
  마지막 32자리가 ID
