#!/usr/bin/env python3
"""Знімає копію авторського тексту М. Ю. Кузьміна з топіків DOU.

Зберігає стартовий допис і коментарі автора топіка, присутні в HTML-сторінці
(без JavaScript; коментарі, які DOU довантажує динамічно, можуть бути відсутні).
Коментарі інших учасників не копіюються — на них лише посилання на оригінал.

Використання: python3 docs/sources/fetch_dou.py 35914 36556 38994 43177
"""
import datetime as dt
import hashlib
import sys
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

OUT = Path(__file__).resolve().parent / "author" / "dou"
UA = {"User-Agent": "Mozilla/5.0 (kuzmin-machine source archiver)"}


def text_of(node) -> str:
    for br in node.find_all("br"):
        br.replace_with("\n")
    for a in node.find_all("a"):
        href = a.get("href", "")
        if href.startswith("http") and a.get_text(strip=True):
            a.replace_with(f"[{a.get_text(strip=True)}]({href})")
    parts = []
    for el in node.find_all(["p", "li", "pre", "h2", "h3", "blockquote"], recursive=True):
        if el.find_parent(["li", "blockquote", "pre"]) not in (None,) and el.name != "pre":
            continue
        t = el.get_text("", strip=False).strip()
        if not t:
            continue
        if el.name == "li":
            t = "- " + t
        elif el.name == "pre":
            t = "```\n" + t + "\n```"
        elif el.name == "blockquote":
            t = "> " + t.replace("\n", "\n> ")
        parts.append(t)
    return "\n\n".join(parts) if parts else node.get_text("\n", strip=True)


def fetch(topic: str) -> None:
    url = f"https://dou.ua/forums/topic/{topic}/"
    html = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("article.b-typo_post h1").get_text(strip=True)
    author = soup.select_one(".author").get_text(strip=True)
    date = soup.select_one(".date").get_text(strip=True)
    body = soup.select_one("article.b-typo_post")
    body.select_one("h1").decompose()
    comments = soup.select(".comment")
    own = []
    for c in comments:
        head = c.select_one(".b-post-author")
        name = head.select_one(".avatar").get_text(strip=True) if head and head.select_one(".avatar") else ""
        if name != author:
            continue
        when = head.select_one(".comment-link")
        cid = c.get("id", "").replace("comment_", "")
        own.append((when.get_text(strip=True) if when else "?", cid, text_of(c.select_one(".comment_text"))))
    today = dt.date.today().isoformat()
    lines = [
        f"# {title}",
        "",
        f"* **Автор:** {author}",
        f"* **Опубліковано:** {date}",
        f"* **Джерело:** <{url}>",
        f"* **Дата доступу:** {today}. SHA-256 отриманого HTML: `{hashlib.sha256(html).hexdigest()}`",
        f"* **Обсяг копії:** стартовий допис і {len(own)} коментар(ів) автора з {len(comments)} коментарів у статичному HTML. "
        "Коментарі інших учасників не скопійовано.",
        "* **Статус:** первинне джерело, лише для читання. Копія для дослідницьких потреб проєкту (рішення Р7, MIGRATION-REGISTER). "
        "Права на текст належать автору.",
        "",
        "---",
        "",
        "## Стартовий допис",
        "",
        text_of(body),
    ]
    if own:
        lines += ["", "## Коментарі автора", ""]
        for when, cid, txt in own:
            lines += [f"### {when} — [#{cid}]({url}#{cid})", "", txt, ""]
    (OUT / f"dou-{topic}.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"{topic}: {title} — коментарів автора {len(own)} / {len(comments)}")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for t in sys.argv[1:]:
        fetch(t)
