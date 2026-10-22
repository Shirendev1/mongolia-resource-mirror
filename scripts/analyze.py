"""Compare Mongolia's export records with its partners' import records.

Reads data/raw/records.csv, writes docs/data/mirror.json for the dashboard.

Flags (each one is a question to ask, not an accusation):
  VALUE_GAP        exporter and importer values differ by more than VALUE_GAP_PCT
  IMPORT_ABOVE     importer recorded MORE than exporter by more than VALUE_GAP_PCT
                   (goods may have left without being recorded)
  IMPORT_BELOW     importer recorded LESS than exporter. Normally the importer's
                   figure is higher (freight/insurance), so this is unusual.
  WEIGHT_GAP       quantity differs by more than WEIGHT_GAP_PCT
  PRICE_GAP        price per unit differs by more than PRICE_GAP_PCT
  ESTIMATED_WEIGHT one side's quantity is an estimate, not a measured figure
  MISSING_EXPORTER Mongolia did not report this period
  MISSING_IMPORTER the partner did not report this period
  IMPORTER_ZERO    the partner reported its trade with Mongolia but recorded none
                   of this good, although Mongolia recorded an export
"""

import csv
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import (COMMODITIES, COUNTRIES, MONGOLIA, NOTES, PAIRS,  # noqa: E402
                    PRICE_GAP_PCT, VALUE_GAP_PCT, WEIGHT_GAP_PCT)

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "records.csv"
OUT = ROOT / "docs" / "data" / "mirror.json"


def num(x):
    try:
        v = float(x)
        return v if v else None
    except (TypeError, ValueError):
        return None


def pct(a, b):
    return None if not b else round((a - b) / b * 100, 1)


def main():
    # (freq, period, hs) -> {(reporter, partner, flow): row}
    recs = defaultdict(dict)
    with RAW.open() as f:
        for r in csv.DictReader(f):
            recs[(r["freq"], r["period"], r["hs"])][
                (int(r["reporter"]), int(r["partner"]), r["flow"])] = r

    rows = []
    for pair in PAIRS:
        partner = pair["partner"]
        for (freq, period, hs), sides in sorted(recs.items()):
            if hs not in pair["hs"]:
                continue
            ex = sides.get((MONGOLIA, partner, "X"))
            im = sides.get((partner, MONGOLIA, "M"))
            if not ex and not im:
                continue
            if not ex and not num(im["value_usd"]):
                continue  # nothing recorded on either side
            per_unit = 1000 if COMMODITIES[hs]["unit"] == "t" else 1
            ex_v, im_v = num(ex and ex["value_usd"]), num(im and im["value_usd"])
            ex_q = (num(ex and ex["net_kg"]) or 0) / per_unit or None
            im_q = (num(im and im["net_kg"]) or 0) / per_unit or None
            ex_est = bool(ex) and ex["kg_estimated"] == "True"
            im_est = bool(im) and im["kg_estimated"] == "True"

            flags = []
            if not ex:
                flags.append("MISSING_EXPORTER")
            if not im:
                flags.append("MISSING_IMPORTER")
            gap_v = gap_v_pct = gap_q_pct = ex_p = im_p = price_gap_pct = None
            if ex_v and im_v:
                gap_v = im_v - ex_v
                gap_v_pct = pct(im_v, ex_v)
                if abs(gap_v_pct) > VALUE_GAP_PCT:
                    flags.append("VALUE_GAP")
                    flags.append("IMPORT_BELOW" if gap_v < 0 else "IMPORT_ABOVE")
            elif ex_v and im and not im_v:
                # partner reported the flow but with (near) zero value
                gap_v, gap_v_pct = -ex_v, -100.0
                flags += ["VALUE_GAP", "IMPORT_BELOW", "IMPORTER_ZERO"]
            if ex_est or im_est:
                flags.append("ESTIMATED_WEIGHT")
            if ex_q and im_q and not (ex_est or im_est):
                gap_q_pct = pct(im_q, ex_q)
                if abs(gap_q_pct) > WEIGHT_GAP_PCT:
                    flags.append("WEIGHT_GAP")
            if ex_v and ex_q and not ex_est:
                ex_p = ex_v / ex_q
            if im_v and im_q and not im_est:
                im_p = im_v / im_q
            if ex_p and im_p:
                price_gap_pct = pct(im_p, ex_p)
                if abs(price_gap_pct) > PRICE_GAP_PCT:
                    flags.append("PRICE_GAP")

            rows.append({
                "freq": freq, "period": period, "hs": hs,
                "exporter": MONGOLIA, "importer": partner,
                "ex_value": ex_v, "im_value": im_v,
                "ex_qty": ex_q, "im_qty": im_q,
                "ex_price": ex_p and round(ex_p, 1), "im_price": im_p and round(im_p, 1),
                "gap_value": gap_v, "gap_value_pct": gap_v_pct,
                "gap_qty_pct": gap_q_pct, "price_gap_pct": price_gap_pct,
                "flags": flags,
            })

    views = [{"hs": hs, "partner": p["partner"]} for p in PAIRS for hs in p["hs"]
             if any(r["hs"] == hs and r["importer"] == p["partner"] for r in rows)]
    order = list(COMMODITIES)
    views.sort(key=lambda v: (order.index(v["hs"]), v["partner"] != 156))

    out = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
        "source": "UN Comtrade (comtradeplus.un.org)",
        "commodities": COMMODITIES,
        "countries": {str(k): v for k, v in COUNTRIES.items()},
        "notes": NOTES,
        "views": views,
        "thresholds": {"value_gap_pct": VALUE_GAP_PCT, "weight_gap_pct": WEIGHT_GAP_PCT,
                       "price_gap_pct": PRICE_GAP_PCT},
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))

    flagged = [r for r in rows if r["freq"] == "A" and
               set(r["flags"]) & {"VALUE_GAP", "WEIGHT_GAP", "PRICE_GAP"}]
    print(f"{len(rows)} rows, {len(views)} views, {len(flagged)} annual rows flagged -> {OUT}")
    for r in flagged:
        print(f"  {r['period']} {r['hs']} ->{r['importer']}: value gap {r['gap_value_pct']}%  "
              f"{','.join(r['flags'])}")


if __name__ == "__main__":
    main()
