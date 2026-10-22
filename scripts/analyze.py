"""Compare exporter vs importer records and raise flags.

Reads data/raw/records.csv, writes docs/data/mirror.json for the dashboard.

Flags (each one is a question to ask, not an accusation):
  VALUE_GAP        exporter and importer values differ by more than VALUE_GAP_PCT
  IMPORT_BELOW     importer recorded LESS value than exporter. Normally the
                   importer's figure is higher (it includes freight/insurance),
                   so this direction is unusual.
  WEIGHT_GAP       tonnage differs by more than WEIGHT_GAP_PCT
  PRICE_GAP        price per tonne differs by more than PRICE_GAP_PCT
  ESTIMATED_WEIGHT one side's tonnage is an estimate, not a measured figure
  MISSING_EXPORTER exporter did not report this period
  MISSING_IMPORTER importer did not report this period
"""

import csv
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import (COMMODITIES, PAIRS, PRICE_GAP_PCT,  # noqa: E402
                    VALUE_GAP_PCT, WEIGHT_GAP_PCT)

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "records.csv"
OUT = ROOT / "docs" / "data" / "mirror.json"
COUNTRY = {496: {"mn": "Монгол", "en": "Mongolia"},
           156: {"mn": "Хятад", "en": "China"}}


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def pct(a, b):
    return None if not b else round((a - b) / b * 100, 1)


def main():
    recs = defaultdict(dict)  # (freq, period, hs) -> {(reporter, flow): row}
    with RAW.open() as f:
        for r in csv.DictReader(f):
            recs[(r["freq"], r["period"], r["hs"])][(int(r["reporter"]), r["flow"])] = r

    # Only report periods where at least one side has data, and fill the
    # whole range so gaps in reporting are visible.
    rows = []
    for exporter, importer in PAIRS:
        for (freq, period, hs), sides in sorted(recs.items()):
            ex = sides.get((exporter, "X"))
            im = sides.get((importer, "M"))
            if not ex and not im:
                continue
            ex_v, im_v = num(ex and ex["value_usd"]), num(im and im["value_usd"])
            ex_t = (num(ex and ex["net_kg"]) or 0) / 1000 or None
            im_t = (num(im and im["net_kg"]) or 0) / 1000 or None
            ex_est = bool(ex) and ex["kg_estimated"] == "True"
            im_est = bool(im) and im["kg_estimated"] == "True"

            flags = []
            if not ex:
                flags.append("MISSING_EXPORTER")
            if not im:
                flags.append("MISSING_IMPORTER")
            gap_v = gap_v_pct = gap_t_pct = ex_p = im_p = price_gap_pct = None
            if ex_v and im_v:
                gap_v = im_v - ex_v
                gap_v_pct = pct(im_v, ex_v)
                if abs(gap_v_pct) > VALUE_GAP_PCT:
                    flags.append("VALUE_GAP")
                if gap_v < 0 and abs(gap_v_pct) > VALUE_GAP_PCT:
                    flags.append("IMPORT_BELOW")
            if ex_est or im_est:
                flags.append("ESTIMATED_WEIGHT")
            if ex_t and im_t and not (ex_est or im_est):
                gap_t_pct = pct(im_t, ex_t)
                if abs(gap_t_pct) > WEIGHT_GAP_PCT:
                    flags.append("WEIGHT_GAP")
            if ex_v and ex_t:
                ex_p = ex_v / ex_t
            if im_v and im_t and not im_est:
                im_p = im_v / im_t
            if ex_p and im_p and not ex_est:
                price_gap_pct = pct(im_p, ex_p)
                if abs(price_gap_pct) > PRICE_GAP_PCT:
                    flags.append("PRICE_GAP")

            rows.append({
                "freq": freq, "period": period, "hs": hs,
                "exporter": exporter, "importer": importer,
                "ex_value": ex_v, "im_value": im_v,
                "ex_tonnes": ex_t, "im_tonnes": im_t,
                "ex_price": ex_p and round(ex_p, 1), "im_price": im_p and round(im_p, 1),
                "gap_value": gap_v, "gap_value_pct": gap_v_pct,
                "gap_tonnes_pct": gap_t_pct, "price_gap_pct": price_gap_pct,
                "flags": flags,
            })

    out = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
        "source": "UN Comtrade (comtradeplus.un.org)",
        "commodities": COMMODITIES,
        "commodity_order": list(COMMODITIES),
        "countries": {str(k): v for k, v in COUNTRY.items()},
        "thresholds": {"value_gap_pct": VALUE_GAP_PCT, "weight_gap_pct": WEIGHT_GAP_PCT,
                       "price_gap_pct": PRICE_GAP_PCT},
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))

    flagged = [r for r in rows if set(r["flags"]) & {"VALUE_GAP", "WEIGHT_GAP", "PRICE_GAP"}]
    print(f"{len(rows)} rows, {len(flagged)} flagged -> {OUT}")
    for r in flagged:
        print(f"  {r['freq']} {r['period']} {r['hs']}: value gap {r['gap_value_pct']}%  "
              f"{','.join(r['flags'])}")


if __name__ == "__main__":
    main()
