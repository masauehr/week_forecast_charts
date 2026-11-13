# ページ本文をテキスト化して表示する探索用スクリプト
import re
import sys

import requests

H = {"User-Agent": "Mozilla/5.0 (compatible; WeekToSeason/0.1)"}
r = requests.get(sys.argv[1], headers=H, timeout=60)
t = r.content.decode("utf-8", "replace")
t = re.sub(r"(?is)<(script|style).*?</\1>", "", t)
t = re.sub(r"(?i)<br\s*/?>|</(p|tr|li|h\d|div|table)>", "\n", t)
t = re.sub(r"(?i)</t[dh]>", " | ", t)
t = re.sub(r"<[^>]+>", "", t)
t = t.replace("&nbsp;", " ")
t = re.sub(r"[ \t　]+", " ", t)
t = re.sub(r"\n\s*\n+", "\n", t)
n = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
print(t[:n])
