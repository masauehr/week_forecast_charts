# em/es/cf/ep の存在と、Z500全メンバーの実ダウンロード時間を測る探索用スクリプト
import json, time
import requests
B = "https://data.ecmwf.int/forecasts/20261113/12z/ifs/0p25/enfo/20261113120000-{}h-enfo-{}"
H = {"User-Agent": "Mozilla/5.0 (compatible; WeekToSeason/0.1)"}
rows = [json.loads(l) for l in requests.get(B.format(120, "ef") + ".index", headers=H, timeout=60).text.splitlines() if l.strip()]
sel = sorted([x for x in rows if x["param"] == "gh" and x.get("levelist") == "500"], key=lambda x: x["_offset"])
t0 = time.time(); tot = 0
for x in sel:
    r = requests.get(B.format(120, "ef") + ".grib2", headers=dict(H, Range=f"bytes={x['_offset']}-{x['_offset']+x['_length']-1}"), timeout=120)
    tot += len(r.content)
print("gh500 50メンバー", tot / 1e6, "MB", round(time.time() - t0, 1), "秒 (メンバーごと個別Range)")
