# ENS の索引を調べる探索用スクリプト（実装ではない）
import json, collections
import requests
from datetime import datetime, timedelta, timezone

BASE = "https://data.ecmwf.int/forecasts"
H = {"User-Agent": "Mozilla/5.0 (compatible; WeekToSeason/0.1)"}
now = datetime.now(timezone.utc)
cands = []
for d in range(0, 3):
    for hh in (12, 0):
        t = (now - timedelta(days=d)).replace(hour=hh, minute=0, second=0, microsecond=0)
        if t < now: cands.append(t)
cands.sort(reverse=True)
for init in cands:
    url = f"{BASE}/{init:%Y%m%d}/{init:%H}z/ifs/0p25/enfo/{init:%Y%m%d%H}0000-{{}}h-enfo-ef"
    ok = [s for s in (0, 120, 240, 360) if requests.head(url.format(s) + ".index", headers=H, timeout=30).status_code == 200]
    print(init, "存在するstep:", ok)
    if 360 in ok:
        break
step = 120
r = requests.get(url.format(step) + ".index", headers=H, timeout=60)
rows = [json.loads(l) for l in r.text.splitlines() if l.strip()]
print("行数", len(rows)); print("例", rows[0])
cnt = collections.Counter((x["param"], x.get("levtype"), x.get("levelist")) for x in rows)
print("param種:", sorted({k[0] for k in cnt}))
nums = sorted({x.get("number") for x in rows if x.get("number") is not None})
print("number数", len(nums), nums[:3], nums[-2:], "type", collections.Counter(x["type"] for x in rows))
sel = [x for x in rows if (x["param"], x.get("levtype"), x.get("levelist")) in (("gh","pl","500"), ("t","pl","850"), ("msl","sfc",None))]
print("対象行", len(sel), "合計MB", sum(x["_length"] for x in sel) / 1e6)
for k in (("gh","pl","500"), ("t","pl","850"), ("msl","sfc",None)):
    ss = [x for x in sel if (x["param"], x.get("levtype"), x.get("levelist")) == k]
    print(k, len(ss), sum(x["_length"] for x in ss) / 1e6, "MB")
print("全体MB", sum(x["_length"] for x in rows) / 1e6)
print(url.format(step) + ".grib2")
