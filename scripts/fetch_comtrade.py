"""Download mirror-trade records from UN Comtrade into data/raw/records.csv.

With an API key (environment variable COMTRADE_KEY) the full data API is used.
Without one, the public preview API is used (slower, one period per request).

Usage:
    python scripts/fetch_comtrade.py            # annual + monthly
    python scripts/fetch_comtrade.py --annual   # annual only
"""

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import FIRST_YEAR, MONGOLIA, PAIRS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "records.csv"
FIELDS = ["freq", "period", "hs", "reporter", "partner", "flow",
          "net_kg", "value_usd", "kg_estimated", "fetched"]

KEY = os.environ.get("COMTRADE_KEY", "").strip()
BASE = ("https://comtradeapi.un.org/data/v1/get/C/{freq}/HS" if KEY
        else "https://comtradeapi.un.org/public/v1/preview/C/{freq}/HS")


def get(freq, reporter, partner, flow, period, hs):
    params = {
        "reporterCode": reporter, "partnerCode": partner, "flowCode": flow,
        "cmdCode": ",".join(hs), "period": period,
    }
    url = BASE.format(freq=freq) + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    if KEY:
        req.add_header("Ocp-Apim-Subscription-Key", KEY)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json.load(r)
            if body.get("data") is not None:
                return body["data"]
        except (urllib.error.URLError, json.JSONDecodeError) as e:
            print(f"  retry {attempt + 1}: {e}", file=sys.stderr)
        time.sleep(3 + attempt * 3)
    print(f"  gave up on {url}", file=sys.stderr)
    return None


def periods(freq):
    today = dt.date.today()
    years = range(FIRST_YEAR, today.year + 1)
    if freq == "A":
        return [str(y) for y in years]
    return [f"{y}{m:02d}" for y in years for m in range(1, 13)
            if dt.date(y, m, 1) < today]


def key(r):
    return (r["freq"], str(r["period"]), str(r["hs"]), str(r["reporter"]),
            str(r["partner"]), r["flow"])


def load_existing():
    if not RAW.exists():
        return {}
    with RAW.open() as f:
        return {key(r): r for r in csv.DictReader(f)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--annual", action="store_true")
    ap.add_argument("--refresh-from", type=int, default=None,
                    help="re-download periods from this year on (default: last 2 years)")
    args = ap.parse_args()

    rows = load_existing()
    have = {(k[0], k[1], k[3], k[4], k[5]) for k in rows}
    refresh_from = args.refresh_from or dt.date.today().year - 2
    today = dt.date.today().isoformat()

    for pair in PAIRS:
        partner, hs = pair["partner"], pair["hs"]
        freqs = ["A"] + (["M"] if pair["monthly"] and not args.annual else [])
        for freq in freqs:
            for per in periods(freq):
                for reporter, other, flow in ((MONGOLIA, partner, "X"),
                                              (partner, MONGOLIA, "M")):
                    if ((freq, per, str(reporter), str(other), flow) in have
                            and int(per[:4]) < refresh_from):
                        continue
                    data = get(freq, reporter, other, flow, per, hs)
                    if data is None:
                        continue
                    # A partner that reports its trade with Mongolia but lists none
                    # of these goods recorded zero. Store that as an explicit 0 so it
                    # isn't confused with "has not reported this period yet".
                    missing = [h for h in hs if h not in {str(d["cmdCode"]) for d in data}]
                    if missing and get(freq, reporter, other, flow, per, ["TOTAL"]):
                        data = data + [{"cmdCode": h, "netWgt": 0, "primaryValue": 0}
                                       for h in missing]
                    for d in data:
                        r = {
                            "freq": freq, "period": per, "hs": str(d["cmdCode"]),
                            "reporter": reporter, "partner": other, "flow": flow,
                            "net_kg": d.get("netWgt") if d.get("netWgt") is not None else "",
                            "value_usd": d.get("primaryValue") if d.get("primaryValue") is not None else "",
                            "kg_estimated": bool(d.get("isNetWgtEstimated")),
                            "fetched": today,
                        }
                        rows[key(r)] = r
                    print(f"{freq} {per} {reporter}->{other} {flow}: {len(data)} rows")
                    time.sleep(1.5 if KEY else 3)

    RAW.parent.mkdir(parents=True, exist_ok=True)
    with RAW.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])
    print(f"saved {len(rows)} records -> {RAW}")


if __name__ == "__main__":
    main()
