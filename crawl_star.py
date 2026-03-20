"""
star.moe.go.kr 생기부 정보 크롤러
매일 07:00 / 12:00 / 18:00 KST 실행
"""

import asyncio
import os
import re
from datetime import date, datetime
import httpx
import anthropic
from playwright.async_api import async_playwright

SOURCES = {
    "2026_기재요령": "https://star.moe.go.kr/web/contents/m21100.do",
    "Q&A_최신": "https://star.moe.go.kr/web/contents/m30102.do",
    "공지사항": "https://star.moe.go.kr/web/contents/m40100.do",
    "FAQ": "https://star.moe.go.kr/web/contents/m302001.do",
    "도움자료": "https://star.moe.go.kr/web/contents/m20900.do",
}

async def fetch_rendered(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox"])
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        try:
            await page.goto(url, wait_until="networkidle", timeout=45000)
            await page.evaluate("""['header','footer','nav','.gnb','.lnb'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))""")
            content = await page.inner_text("main, #container, body")
        except Exception as e:
            content = f"크롤링 오류: {e}"
        finally:
            await browser.close()
    return content[:6000]

async def crawl_all():
    results = {}
    for name, url in SOURCES.items():
        print(f"  📡 크롤링: {name}")
        results[name] = await fetch_rendered(url)
    return results

def summarize(raw):
    client_kwargs = {"api_key": os.environ["ANTHROPIC_API_KEY"]}
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if base_url:
        client_kwargs["base_url"] = base_url
    client = anthropic.Anthropic(**client_kwargs)
    now = datetime.now()
    today_str = now.strftime("%Y년 %m월 %d일")
    time_str = now.strftime("%H:%M")
    combined = "\n\n".join(f"=== {k} ===\n{v}" for k, v in raw.items())
    prompt = f"""오늘({today_str} {time_str}) 학교생활기록부 종합지원포털 수집 내용입니다.

{combined}

AXIOM 생기부 멘토링 운영자를 위한 일일 브리핑 작성하세요.

⚠️ 반드시 준수:
- 표(테이블) 절대 금지. 불릿(-) 사용
- Q&A 항목마다 링크 포함: [제목](https://star.moe.go.kr/web/contents/m30102.do)
- 제목에 이모지 넣지 말 것 (## 헤더에만)

# 생기부 브리핑 {today_str} ({time_str})

## 🎯 오늘의 핵심 3가지
- (핵심 1)
- (핵심 2)
- (핵심 3)

## 📑 2026 기재요령 주요 내용
- (항목별 핵심 내용)

## ❓ 오늘의 Q&A 동향
- [질문 요약](https://star.moe.go.kr/web/contents/m30102.do) — 답변 핵심
  (최근 Q&A 5건 이상, 각 링크 포함)

## 💡 멘토링 실전 팁
- (바로 쓸 수 있는 팁 3개)

## ⚠️ 자주 하는 실수
- (흔히 틀리는 것)

## 🔗 참고 링크
- 2026 기재요령: https://star.moe.go.kr/web/contents/m21100.do
- Q&A: https://star.moe.go.kr/web/contents/m30102.do
- 공지사항: https://star.moe.go.kr/web/contents/m40100.do
- 도움자료: https://star.moe.go.kr/web/contents/m20900.do

내용 없으면 "새로운 내용 없음" 표기."""
    msg = client.messages.create(model="claude-opus-4-5", max_tokens=3000,
                                  messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text

def parse_rich_text(text):
    parts = []
    pattern = re.compile(r'\*\*(.+?)\*\*|\[([^\]]+)\]\((https?://[^\)]+)\)')
    last = 0
    for m in pattern.finditer(text):
        if m.start() > last:
            parts.append({"type": "text", "text": {"content": text[last:m.start()]}})
        if m.group(1):
            parts.append({"type": "text", "text": {"content": m.group(1)},
                          "annotations": {"bold": True}})
        else:
            parts.append({"type": "text",
                          "text": {"content": m.group(2), "link": {"url": m.group(3)}}})
        last = m.end()
    if last < len(text):
        parts.append({"type": "text", "text": {"content": text[last:]}})
    return parts or [{"type": "text", "text": {"content": text}}]

def md_to_notion_blocks(md):
    blocks = []
    for line in md.split("\n"):
        s = line.rstrip()
        if not s:
            blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}})
        elif s.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1",
                            "heading_1": {"rich_text": parse_rich_text(s[2:].strip())}})
        elif s.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                            "heading_2": {"rich_text": parse_rich_text(s[3:].strip())}})
        elif s.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3",
                            "heading_3": {"rich_text": parse_rich_text(s[4:].strip())}})
        elif re.match(r'^[ \t]*[-*] ', s):
            content = re.sub(r'^[ \t]*[-*] ', '', s)
            blocks.append({"object": "block", "type": "bulleted_list_item",
                            "bulleted_list_item": {"rich_text": parse_rich_text(content.strip())}})
        elif re.match(r'^\d+\. ', s):
            content = re.sub(r'^\d+\. ', '', s)
            blocks.append({"object": "block", "type": "numbered_list_item",
                            "numbered_list_item": {"rich_text": parse_rich_text(content.strip())}})
        elif s.startswith("> "):
            blocks.append({"object": "block", "type": "quote",
                            "quote": {"rich_text": parse_rich_text(s[2:].strip())}})
        elif s.startswith("---"):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif s.startswith("|") and "|" in s[1:]:
            cells = [c.strip() for c in s.strip("|").split("|")]
            cells = [c for c in cells if c and not re.match(r'^[-:]+$', c)]
            if cells:
                blocks.append({"object": "block", "type": "paragraph",
                                "paragraph": {"rich_text": parse_rich_text(" · ".join(cells))}})
        else:
            blocks.append({"object": "block", "type": "paragraph",
                            "paragraph": {"rich_text": parse_rich_text(s)}})
    return blocks[:100]

def notion_headers():
    return {"Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
            "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def get_or_create_section(axiom_id):
    hdrs = notion_headers()
    r = httpx.get(f"https://api.notion.com/v1/blocks/{axiom_id}/children?page_size=50",
                  headers=hdrs, timeout=20)
    r.raise_for_status()
    for block in r.json().get("results", []):
        if block.get("type") == "child_page" and "생기부 정보" in block["child_page"].get("title", ""):
            return block["id"]
    res = httpx.post("https://api.notion.com/v1/pages", headers=hdrs, timeout=20,
                     json={"parent": {"page_id": axiom_id}, "icon": {"emoji": "📚"},
                           "properties": {"title": {"title": [{"text": {"content": "4. 생기부 정보"}}]}}})
    res.raise_for_status()
    return res.json()["id"]

def create_notion_page(summary, parent_id):
    hdrs = notion_headers()
    now = datetime.now()
    title = f"생기부 브리핑 {now.strftime('%Y.%m.%d')} {now.strftime('%H:%M')}"
    r = httpx.post("https://api.notion.com/v1/pages", headers=hdrs, timeout=30,
                   json={"parent": {"page_id": parent_id}, "icon": {"emoji": "📋"},
                         "properties": {"title": {"title": [{"text": {"content": title}}]}},
                         "children": md_to_notion_blocks(summary)})
    r.raise_for_status()
    return r.json().get("url", r.json()["id"])

async def main():
    print(f"🚀 생기부 브리핑 | {datetime.now().strftime('%Y-%m-%d %H:%M KST')}")
    raw = await crawl_all()
    summary = summarize(raw)
    section_id = get_or_create_section(os.environ["NOTION_AXIOM_PAGE_ID"])
    url = create_notion_page(summary, section_id)
    print(f"✅ 완료! → {url}")

if __name__ == "__main__":
    asyncio.run(main())
