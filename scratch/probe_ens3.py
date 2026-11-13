# Range取得を並列化した場合の所要時間を測る探索用スクリプト
import json, sys, time
from concurrent.futures import ThreadPoolExecutor
import requests
B = "https://data.ecmwf.int/forecasts/20261113/12z/ifs/0p25/enfo/20261113120000-{}h-enfo-ef"
H = {"User-Agent": "Mozilla/5.0 (compatible; WeekToSeason/0.1)"}
rows = [json.loads(l) for l in requests.get(B.format(132) + ".index", headers=H, timeout=60).text.splitlines() if l.strip()]
sel = [x for x in rows if x["param"] == "gh" and x.get("levelist") == "500"]
def get(x):
    r = requests.get(B.format(132) + ".grib2", headers=dict(H, Range=f"bytes={x['_offset']}-{x['_offset']+x['_length']-1}"), timeout=120)
    return len(r.content)
for w in (int(a) for a in sys.argv[1:]):
    t0 = time.time()
    with ThreadPoolExecutor(w) as ex:
        tot = sum(ex.map(get, sel))
    print(f"並列{w}: {tot/1e6:.1f}MB {time.time()-t0:.1f}秒", flush=True)
