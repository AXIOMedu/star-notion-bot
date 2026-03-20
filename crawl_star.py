"""
star.moe.go.kr 생기부 정보 크롤러
매일 07:00 KST 실행 → Claude 요약 → Notion 페이지 생성
"""

import asyncio
import json
import os
import re
from datetime import date, datetime
import httpx
import anthropic
from playwright.async_api import async_playwright

# ─── 크롤링 대상 URL ────────────────────────────────────────────────────────
SOURCES = {
    "2026_기재요령": "https://star.moe.go.kr/web/contents/m21100.do",
    "Q&A_최신": "https://star.moe.go.kr/web/contents/m30102.do",
    "공지사항": "https://star.moe.go.kr/web/contents/m40100.do",
    "FAQ": "https://star.moe.go.kr/web/contents/m302001.do",
}

# ─── Playwright로 JS 렌더링된 페이지 텍스트 추출 ────────────────────────────
async def fetch_rendered(url: str, wait_selector: str | None = None) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        try:
            await page.goto(url, wait_until="networkidle", timeout=45_000)
            if wait_selector:
                await page.wait_for_selector(wait_selector, timeout=15_000)
            # Remove nav/header/footer noise
            await page.evaluate("""
                ['header','footer','nav','.gnb','.lnb','.skip-navi'].forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => el.remove());
                });
            """)
            content = await page.inner_text("main, #container, body")
        except Exception as e:
            content = f"크롤링 오류: {e}"
        finally:
            await browser.close()
    return content[:6_000]  # 소스당 최대 6000자

# ─── 전체 소스 크롤링 ────────────────────────────────────────────────────────
async def crawl_all() -> dict[str, str]:
    tasks = {
        name: fetch_rendered(url)
        for name, url in SOURCES.items()
    }
    results = {}
    for name, coro in tasks.items():
        print(f"  📡 크롤링: {name}")
        results[name] = await coro
    return results

# ─── Claude로 A4 1장 브리핑 생성 ────────────────────────────────────────────
def summarize(raw: dict[str, str]) -> str:
    # 학교 지원 API는 ANTHROPIC_BASE_URL 환경변수로 커스텀 엔드포인트 사용
    client_kwargs = {"api_key": os.environ["ANTHROPIC_API_KEY"]}
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if base_url:
        client_kwargs["base_url"] = base_url
    client = anthropic.Anthropic(**client_kwargs)
    today_str = date.today().strftime("%Y년 %m월 %d일")
    combined = "\n\n".join(f"=== {k} ===\n{v}" for k, v in raw.items())

    prompt = f"""오늘({today_str}) 교육부 학교생활기록부 종합지원포털에서 수집한 내용입니다.

{combined}

──────────────────────────────────────────────────
생기부 멘토링 서비스 운영자를 위한 **A4 1장 분량 일일 브리핑**을 작성해주세요.

아래 형식을 정확히 따라주세요:

# 📋 생기부 정보 브리핑 ({today_str})

## 🎯 오늘의 핵심 포인트
(3줄 이내, 오늘 꼭 알아야 할 것)

## 📑 2026 기재요령 주요 내용
(새로운 변경사항, 주의사항, 항목별 핵심 내용)

## ❓ Q&A 트렌드 분석
(오늘 올라온 또는 최근 자주 나오는 질문 유형, 학생/학부모 관심사)

## 💡 멘토링 실전 활용 팁
(AXIOM 멘토들이 오늘 상담 시 바로 쓸 수 있는 포인트 2-3개)

## ⚠️ 주의사항 / 자주 하는 실수
(멘토나 학생들이 흔히 틀리는 부분)

## 🔗 오늘의 참고 링크
- 기재요령: https://star.moe.go.kr/web/contents/m21100.do
- Q&A: https://star.moe.go.kr/web/contents/m30102.do
- 공지사항: https://star.moe.go.kr/web/contents/m40100.do

──────────────────────────────────────────────────
실제 크롤링된 내용 기반으로, 현장에서 바로 활용할 수 있도록 구체적으로 작성해주세요.
내용이 부족하면 해당 섹션에 "오늘 새로운 내용 없음"으로 표기하세요."""

    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2_500,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

# ─── Markdown → Notion blocks 변환 ──────────────────────────────────────────
def parse_rich_text(text: str) -> list[dict]:
    """**bold** 인라인 처리"""
    parts = []
    pattern = re.compile(r'\*\*(.+?)\*\*')
    last = 0
    for m in pattern.finditer(text):
        if m.start() > last:
            parts.append({"type": "text", "text": {"content": text[last:m.start()]}})
        parts.append({
            "type": "text",
            "text": {"content": m.group(1)},
            "annotations": {"bold": True}
        })
        last = m.end()
    if last < len(text):
        parts.append({"type": "text", "text": {"content": text[last:]}})
    return parts or [{"type": "text", "text": {"content": text}}]


def md_to_notion_blocks(md: str) -> list[dict]:
    blocks = []
    for line in md.split("\n"):
        s = line.rstrip()
        if not s:
            blocks.append({"object": "block", "type": "paragraph",
                            "paragraph": {"rich_text": []}})
            continue
        if s.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1",
                            "heading_1": {"rich_text": parse_rich_text(s[2:].strip())}})
        elif s.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                            "heading_2": {"rich_text": parse_rich_text(s[3:].strip())}})
        elif s.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3",
                            "heading_3": {"rich_text": parse_rich_text(s[4:].strip())}})
        elif re.match(r'^[-*] ', s):
            blocks.append({"object": "block", "type": "bulleted_list_item",
                            "bulleted_list_item": {"rich_text": parse_rich_text(s[2:].strip())}})
        elif re.match(r'^\d+\. ', s):
            text = re.sub(r'^\d+\. ', '', s)
            blocks.append({"object": "block", "type": "numbered_list_item",
                            "numbered_list_item": {"rich_text": parse_rich_text(text.strip())}})
        elif s.startswith("---") or s.startswith("───"):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        else:
            blocks.append({"object": "block", "type": "paragraph",
                            "paragraph": {"rich_text": parse_rich_text(s)}})
    return blocks[:100]  # Notion API 한 번에 최대 100 블록

# ─── Notion API ──────────────────────────────────────────────────────────────
def notion_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }


def get_or_create_gigi_section(axiom_page_id: str) -> str:
    """AXIOM 하위에서 '4. 생기부 정보' 페이지 ID를 찾거나 새로 만든다."""
    hdrs = notion_headers()

    # 자식 블록 조회
    r = httpx.get(
        f"https://api.notion.com/v1/blocks/{axiom_page_id}/children?page_size=50",
        headers=hdrs,
        timeout=20,
    )
    r.raise_for_status()
    for block in r.json().get("results", []):
        if block.get("type") == "child_page":
            title = block["child_page"].get("title", "")
            if "생기부 정보" in title:
                print(f"  ✅ 기존 섹션 발견: {title} ({block['id']})")
                return block["id"]

    # 없으면 생성
    print("  📂 '4. 생기부 정보' 섹션 신규 생성...")
    res = httpx.post(
        "https://api.notion.com/v1/pages",
        headers=hdrs,
        timeout=20,
        json={
            "parent": {"page_id": axiom_page_id},
            "icon": {"emoji": "📚"},
            "properties": {
                "title": {"title": [{"text": {"content": "4. 생기부 정보"}}]}
            },
        },
    )
    res.raise_for_status()
    page_id = res.json()["id"]
    print(f"  ✅ 섹션 생성 완료: {page_id}")
    return page_id


def create_notion_page(summary: str, parent_id: str) -> str:
    hdrs = notion_headers()
    today = date.today()
    title = f"📋 생기부 브리핑 {today.strftime('%Y.%m.%d')} ({today.strftime('%a')})"
    blocks = md_to_notion_blocks(summary)

    payload = {
        "parent": {"page_id": parent_id},
        "icon": {"emoji": "📋"},
        "cover": None,
        "properties": {
            "title": {"title": [{"text": {"content": title}}]}
        },
        "children": blocks,
    }
    r = httpx.post(
        "https://api.notion.com/v1/pages",
        headers=hdrs,
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("url", data["id"])

# ─── 메인 ────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 55)
    print(f"🚀 생기부 정보 브리핑 시작 | {datetime.now().strftime('%Y-%m-%d %H:%M KST')}")
    print("=" * 55)

    # 1. 크롤링
    print("\n[1/4] star.moe.go.kr 크롤링...")
    raw = await crawl_all()

    # 2. Claude 요약
    print("\n[2/4] Claude로 A4 1장 요약 생성...")
    summary = summarize(raw)
    print(f"  → 요약 완료 ({len(summary)}자)")

    # 3. 섹션 확인/생성
    print("\n[3/4] Notion 섹션 확인...")
    axiom_id = os.environ["NOTION_AXIOM_PAGE_ID"]
    section_id = get_or_create_gigi_section(axiom_id)

    # 4. 페이지 생성
    print("\n[4/4] Notion 페이지 생성...")
    page_url = create_notion_page(summary, section_id)
    print(f"\n✅ 완료! → {page_url}")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
