# kp_parser.py   →   pip install requests beautifulsoup4
import argparse, json, os, re, time
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

POSTER_SIZE = "268x402"          # или "536x804" для ретины
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9"})
    return s

def fetch(s, url, tries=3):
    for attempt in range(tries):
        r = s.get(url, timeout=30)
        # антибот-заглушка Яндекса вместо контента
        if "var it = " in r.text and len(r.text) < 20000:
            m = re.search(r"var it = (\{.*?\});", r.text, re.S)
            install = json.loads(m.group(1).encode().decode("unicode_escape"))["host"]
            s.get(install, timeout=30)          # забираем cookies
            r = s.get(url, timeout=30)
        if r.ok and ("/film/" in r.text or "/series/" in r.text):
            return r.text
        time.sleep(2 + attempt * 3)
    raise RuntimeError("Не удалось получить " + url)

def parse_page(html):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    # опираемся на структуру, а не на хеши CSS-классов (они меняются при каждом релизе КП)
    for a in soup.select('a[href^="/film/"], a[href^="/series/"]'):
        img = a.find("img")
        if not img:
            continue
        kind, fid = re.match(r"/(film|series)/(\d+)/", a["href"]).groups()
        rating = None
        for sp in a.parent.find_all("span"):
            t = sp.get_text(strip=True)
            if t.isdigit():
                rating = int(t); break
        cap = a.parent.find_next_sibling("a")
        title = (cap.select_one('[class*="title"]').get_text(strip=True)
                 if cap and cap.select_one('[class*="title"]') else img.get("alt", ""))
        sub = (cap.select_one('[class*="subtitle"]').get_text(strip=True)
               if cap and cap.select_one('[class*="subtitle"]') else "")
        y = re.search(r"(19|20)\d{2}", sub)
        path = re.sub(r"^.*?(get-kinopoisk-image/)", r"\1", img.get("src", ""))
        items.append({
            "id": int(fid), "type": kind, "title": title,
            "year": int(y.group(0)) if y else None, "info": sub, "rating": rating,
            "url": f"https://www.kinopoisk.ru/{kind}/{fid}/",
            "poster": "https://avatars.mds.yandex.net/" + re.sub(r"/\d+x\d+$", "/" + POSTER_SIZE, path),
        })
    counts = [int(x) for x in re.findall(r">(\d+)\s+фильмов<", html)]
    pages  = [int(x) for x in re.findall(r"\?page=(\d+)\"", html)]
    return items, max(counts or [0]), max(pages or [1])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alias", default="alexsofari")
    ap.add_argument("--out", default="docs/kp.json")
    ap.add_argument("--delay", type=float, default=0.7)
    ap.add_argument("--limit", type=int, default=0)   # 0 = выгрузить все 759
    a = ap.parse_args()

    base = f"https://www.kinopoisk.ru/user/{a.alias}/movies/voted-watched/"
    s = make_session()
    first, total, pages = parse_page(fetch(s, base))
    seen = {(i["type"], i["id"]): i for i in first}
    for p in range(2, pages + 1):
        time.sleep(a.delay)
        got, _, _ = parse_page(fetch(s, base + f"?page={p}"))
        for i in got:
            seen.setdefault((i["type"], i["id"]), i)
        print(f"страница {p}/{pages}: {len(got)}")

    data = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "profile": f"https://www.kinopoisk.ru/user/{a.alias}/",
            "watched_total": total,
            "items": list(seen.values())[: a.limit or None]}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(data, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print("Сохранено", len(data["items"]), "из", total, "→", a.out)

main()
