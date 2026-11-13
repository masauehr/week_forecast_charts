# 気象業務支援センターのページを文字コード変換して、リンク一覧と本文を表示する探索用スクリプト
import re, sys
import requests
H = {"User-Agent": "Mozilla/5.0 (compatible; WeekToSeason/0.1)"}
def get(url):
    r = requests.get(url, headers=H, timeout=60)
    for enc in ("cp932", "utf-8", "euc-jp"):
        try:
            return r.content.decode(enc)
        except UnicodeDecodeError:
            continue
    return r.content.decode("utf-8", "replace")
t = get(sys.argv[1])
print(len(t))
for m in re.finditer(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', t, re.S):
    label = re.sub(r"<[^>]+>|\s+", " ", m.group(2)).strip()
    if label: print(label[:50], "->", m.group(1))
