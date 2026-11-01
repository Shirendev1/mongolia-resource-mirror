"""Mine-output registry: what comes out of the mine, measured and locked.

Usage:
  python scripts/mine_ledger.py            # ingest + verify + analyze
  python scripts/mine_ledger.py ingest     # add new CSV rows to the ledger
  python scripts/mine_ledger.py verify     # check that nobody edited the ledger
  python scripts/mine_ledger.py analyze    # compare measurements with declarations

Inputs (data/mine/):
  mines.csv         mine_id, name_mn, name_en, license_no, company
  measurements.csv  one row per measurement of a batch (sensor, handheld XRF, lab)
  declarations.csv  what the company declared for each batch

Ledger (data/mine/ledger.jsonl):
  Every measurement and declaration is appended once, with the SHA-256 hash of
  the previous entry. Changing any old entry breaks every hash after it, so an
  edit cannot go unnoticed. A CSV row that is changed after it entered the
  ledger is reported as EDITED_AFTER_LEDGER; the ledger keeps the original.

Flags per batch (each one is a question to ask, not an accusation):
  UNDECLARED_ELEMENT     measured above DECLARE_THRESHOLD but not declared
  DECLARED_BELOW         declared grade lower than measured by > GRADE_GAP_PCT
  SOURCE_GAP             company and independent measurements disagree
  TONNAGE_GAP            declared tonnes differ from measured tonnes
  NO_INDEPENDENT_SAMPLE  only the company measured this batch
  NO_DECLARATION         batch was measured but never declared
  NO_MEASUREMENT         batch was declared but never measured
  EDITED_AFTER_LEDGER    a source row was changed after it was locked
"""

import csv
import datetime as dt
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mine_config import (DECLARE_THRESHOLD, ELEMENTS, GRADE_GAP_PCT,  # noqa: E402
                         INDEPENDENT_SOURCES, METHODS, SOURCE_GAP_PCT,
                         TONNAGE_GAP_PCT)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "mine"
OUT = ROOT / "docs" / "data" / "mine.json"
GENESIS = "0" * 64


# ---------------------------------------------------------------- ledger

def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def entry_hash(seq, kind, record, prev_hash):
    body = canonical({"seq": seq, "kind": kind, "record": record, "prev_hash": prev_hash})
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def read_ledger(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def verify(entries):
    """Return (ok, index of first bad entry or None)."""
    prev = GENESIS
    for i, e in enumerate(entries):
        if e.get("seq") != i or e.get("prev_hash") != prev:
            return False, i
        if entry_hash(e["seq"], e["kind"], e["record"], e["prev_hash"]) != e.get("hash"):
            return False, i
        prev = e["hash"]
    return True, None


def read_csv(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def record_key(kind, rec):
    return (kind, rec["measurement_id"] if kind == "measurement" else rec["batch_id"])


def source_rows(data_dir):
    return [("measurement", read_csv(data_dir / "measurements.csv")),
            ("declaration", read_csv(data_dir / "declarations.csv"))]


def find_edits(data_dir, entries):
    """CSV rows whose content differs from the copy locked in the ledger."""
    locked = {record_key(e["kind"], e["record"]): e["record"] for e in entries}
    return [record_key(kind, rec) for kind, rows in source_rows(data_dir) for rec in rows
            if record_key(kind, rec) in locked and locked[record_key(kind, rec)] != rec]


def ingest(data_dir=DATA, now=None):
    """Append new measurement/declaration rows. Returns (added, edited_keys)."""
    ledger_path = data_dir / "ledger.jsonl"
    entries = read_ledger(ledger_path)
    ok, bad = verify(entries)
    if not ok:
        raise SystemExit(f"Ledger is broken at entry {bad}; refusing to add to it.")
    locked = {record_key(e["kind"], e["record"]): e["record"] for e in entries}
    edited = find_edits(data_dir, entries)

    now = now or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prev = entries[-1]["hash"] if entries else GENESIS
    added = []
    for kind, rows in source_rows(data_dir):
        for rec in rows:
            key = record_key(kind, rec)
            if key in locked:
                continue
            seq = len(entries)
            e = {"seq": seq, "kind": kind, "record": rec, "locked_at": now, "prev_hash": prev}
            e["hash"] = entry_hash(seq, kind, rec, prev)
            entries.append(e)
            locked[key] = rec
            added.append(key)
            prev = e["hash"]

    if added:
        with ledger_path.open("a", encoding="utf-8") as f:
            for e in entries[-len(added):]:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return added, edited


# ---------------------------------------------------------------- analysis

def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def pct(a, b):
    return None if not b else round((a - b) / b * 100, 1)


def average(measurements):
    """Tonnage-weighted average grade of each element across measurements."""
    out = {}
    for el in ELEMENTS:
        pairs = [(num(m.get(el)), num(m.get("tonnes")) or 1.0) for m in measurements]
        pairs = [(v, w) for v, w in pairs if v is not None]
        if pairs:
            out[el] = round(sum(v * w for v, w in pairs) / sum(w for _, w in pairs), 4)
    tonnes = [num(m.get("tonnes")) for m in measurements if num(m.get("tonnes"))]
    out["tonnes"] = max(tonnes) if tonnes else None
    return out


def analyze_batches(entries, mines, edited_keys=()):
    meas, decl = defaultdict(list), {}
    for e in entries:
        r = e["record"]
        if e["kind"] == "measurement":
            meas[r["batch_id"]].append(r)
        else:
            decl[r["batch_id"]] = r
    edited_batches = set()
    for kind, key in edited_keys:
        if kind == "declaration":
            edited_batches.add(key)
        else:
            for b, ms in meas.items():
                if any(m["measurement_id"] == key for m in ms):
                    edited_batches.add(b)

    batches = []
    for batch_id in sorted(set(meas) | set(decl)):
        ms, d = meas.get(batch_id, []), decl.get(batch_id)
        indep = [m for m in ms if m.get("measured_by") in INDEPENDENT_SOURCES]
        comp = [m for m in ms if m.get("measured_by") not in INDEPENDENT_SOURCES]
        indep_avg = average(indep) if indep else None
        comp_avg = average(comp) if comp else None
        ref = indep_avg or comp_avg
        mine_id = (d or ms[0])["mine_id"]
        flags, gaps = [], []

        if not ms:
            flags.append("NO_MEASUREMENT")
        if not d:
            flags.append("NO_DECLARATION")
        if ms and not indep:
            flags.append("NO_INDEPENDENT_SAMPLE")
        if batch_id in edited_batches:
            flags.append("EDITED_AFTER_LEDGER")

        if indep_avg and comp_avg:
            for el in ELEMENTS:
                a, b = indep_avg.get(el), comp_avg.get(el)
                if a and b is not None and abs(pct(b, a)) > SOURCE_GAP_PCT:
                    flags.append("SOURCE_GAP")
                    break

        tonnes = (ref or {}).get("tonnes") or num(d and d.get("tonnes"))
        if ref and d:
            dt_ = num(d.get("tonnes"))
            if ref.get("tonnes") and dt_ and abs(pct(dt_, ref["tonnes"])) > TONNAGE_GAP_PCT:
                flags.append("TONNAGE_GAP")
            for el, meta in ELEMENTS.items():
                measured = ref.get(el)
                declared = num(d.get(el))
                if measured is None or measured < DECLARE_THRESHOLD[el]:
                    continue  # trace amounts are not worth declaring
                gap = None
                if not declared:
                    flags.append("UNDECLARED_ELEMENT")
                    gap = measured
                elif pct(declared, measured) < -GRADE_GAP_PCT:
                    flags.append("DECLARED_BELOW")
                    gap = measured - declared
                if gap is not None:
                    gaps.append({
                        "element": el,
                        "measured": measured, "declared": declared,
                        "contained_gap": round(gap * (tonnes or 0) * meta["factor"], 2),
                    })

        batches.append({
            "batch_id": batch_id, "mine_id": mine_id,
            "mine": mines.get(mine_id, {}).get("name_mn", mine_id),
            "product": d and d.get("product"),
            "export_ref": d and d.get("export_ref"),
            "tonnes": tonnes,
            "measurements": [{
                "id": m["measurement_id"], "at": m.get("measured_at"),
                "method": m.get("method"), "by": m.get("measured_by"),
                "device": m.get("lab_or_device"),
                "grades": {el: num(m.get(el)) for el in ELEMENTS if num(m.get(el)) is not None},
            } for m in ms],
            "independent": indep_avg, "company": comp_avg,
            "declared": d and {el: num(d.get(el)) for el in ELEMENTS if d.get(el) != ""},
            "gaps": gaps,
            "flags": list(dict.fromkeys(flags)),
        })
    return batches


def summarize(batches):
    totals = defaultdict(float)
    for b in batches:
        for g in b["gaps"]:
            totals[g["element"]] += g["contained_gap"]
    return {el: round(v, 2) for el, v in totals.items() if v}


def analyze(data_dir=DATA, out=OUT):
    entries = read_ledger(data_dir / "ledger.jsonl")
    ok, bad = verify(entries)
    mines = {m["mine_id"]: m for m in read_csv(data_dir / "mines.csv")}
    batches = analyze_batches(entries, mines, find_edits(data_dir, entries))
    demo = any(m.get("demo") == "yes" for m in mines.values())
    result = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
        "demo": demo,
        "ledger": {"entries": len(entries), "ok": ok, "broken_at": bad,
                   "head": entries[-1]["hash"] if entries else None},
        "elements": ELEMENTS, "methods": METHODS,
        "thresholds": {"declare": DECLARE_THRESHOLD, "grade_gap_pct": GRADE_GAP_PCT,
                       "source_gap_pct": SOURCE_GAP_PCT, "tonnage_gap_pct": TONNAGE_GAP_PCT},
        "mines": mines,
        "totals_gap": summarize(batches),
        "batches": batches,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "all"
    if cmd in ("ingest", "all"):
        added, edited = ingest()
        print(f"ingest: {len(added)} new entries")
        for k in edited:
            print(f"  WARNING edited after ledger: {k[0]} {k[1]}")
    if cmd in ("verify", "all"):
        ok, bad = verify(read_ledger(DATA / "ledger.jsonl"))
        print("verify: OK" if ok else f"verify: BROKEN at entry {bad}")
        if not ok:
            return 1
    if cmd in ("analyze", "all"):
        r = analyze()
        flagged = [b for b in r["batches"] if b["flags"]]
        print(f"analyze: {len(r['batches'])} batches, {len(flagged)} flagged -> {OUT}")
        for b in flagged:
            print(f"  {b['batch_id']} {','.join(b['flags'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
