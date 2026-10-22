"""Download mirror-trade records from UN Comtrade into data/raw/records.csv.

With an API key (environment variable COMTRADE_KEY) the full data API is used.
Without one, the public preview API is used (slower, one period per request).

Usage:
    python scripts/fetch_comtrade.py            # annual + monthly, all years
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
from config import COMMODITIES, FIRST_YEAR, PAIRS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "records.csv"
FIELDS = ["freq", "period", "hs", "reporter", "partner", "flow",
          "net_kg", "value_usd", "kg_estimated", "fetched"]

KEY = os.environ.get("COMTRADE_KEY", "").strip()
BASE = ("https://comtradeapi.un.org/data/v1/get/C/{freq}/HS" if KEY
        else "https://comtradeapi.un.org/public/v1/preview/C/{freq}/HS")


def get(freq, reporter, partner, flow, period):
    params = {
        "reporterCode": reporter, "partnerCode": partner, "flowCode": flow,
        "cmdCode": ",".join(COMMODITIES), "period": period,
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
    this_year = dt.date.today().year
    years = range(FIRST_YEAR, this_year + 1)
    if freq == "A":
        return [str(y) for y in years]
    return [f"{y}{m:02d}" for y in years for m in range(1, 13)
            if dt.date(y, m, 1) < dt.date.today()]


def load_existing():
    if not RAW.exists():
        return {}
    with RAW.open() as f:
        return {(r["freq"], r["period"], r["hs"], r["reporter"], r["flow"]): r
                for r in csv.DictReader(f)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--annual", action="store_true")
    ap.add_argument("--refresh-from", type=int, default=None,
                    help="re-download periods from this year on (default: last 2 years)")
    args = ap.parse_args()

    rows = load_existing()
    refresh_from = args.refresh_from or dt.date.today().year - 2
    freqs = ["A"] if args.annual else ["A", "M"]
    today = dt.date.today().isoformat()

    for freq in freqs:
        for per in periods(freq):
            year = int(per[:4])
            for exporter, importer in PAIRS:
                for reporter, partner, flow in ((exporter, importer, "X"),
                                                (importer, exporter, "M")):
                    have = any(k[0] == freq and k[1] == per and k[3] == str(reporter)
                               and k[4] == flow for k in rows)
                    if have and year < refresh_from:
                        continue
                    data = get(freq, reporter, partner, flow, per)
                    if data is None:
                        continue
                    for d in data:
                        key = (freq, per, str(d["cmdCode"]), str(reporter), flow)
                        rows[key] = {
                            "freq": freq, "period": per, "hs": d["cmdCode"],
                            "reporter": reporter, "partner": partner, "flow": flow,
                            "net_kg": d.get("netWgt") or "",
                            "value_usd": d.get("primaryValue") or "",
                            "kg_estimated": bool(d.get("isNetWgtEstimated")),
                            "fetched": today,
                        }
                    print(f"{freq} {per} reporter={reporter} {flow}: {len(data)} rows")
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
