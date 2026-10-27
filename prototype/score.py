"""Score and rank proposals from extracted facts. No AI is used in this file.

Steps (same as the diagram):
  1. Suspicious-text check  -> "flagged" (held for a person)
  2. Mandatory pass/fail    -> "ineligible"
  3. Weighted scoring       -> "ranked", using the admin's criteria file

Usage:
  python score.py                                  # uses sample_facts.json
  python score.py --facts facts/                   # uses the output of extract.py
  python score.py --check ../ranking.json          # also compares with the expected ranking
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).parent


# ---------- loading ----------

def load_facts(path: Path) -> dict:
    """Read facts from one JSON file (all proposals) or a folder (one file per proposal)."""
    if path.is_dir():
        return {f.stem: json.loads(f.read_text()) for f in sorted(path.glob("*.json"))}
    data = json.loads(path.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def value(facts: dict, field: str):
    """Return a field's value, or None if it was not stated / unclear / unverified."""
    f = facts["fields"].get(field) or {}
    return f.get("value") if f.get("status") == "stated" else None


# ---------- step 1 and 2: checks ----------

def mandatory_failures(facts: dict, criteria: dict) -> list[str]:
    """Return the labels of the mandatory criteria this proposal fails."""
    failed = []
    for rule in criteria["mandatory"]:
        for check in rule["checks"]:
            v = value(facts, check["field"])
            ok = v is not None
            if ok and "equals" in check:
                ok = v == check["equals"]
            if ok and "min" in check:
                ok = v >= check["min"]
            if not ok:
                failed.append(rule["label"])
                break
    return failed


# ---------- step 3: scoring ----------

def best_values(pool: dict, criteria: dict) -> dict:
    """Best value of each scored field among the eligible, unflagged proposals."""
    best = {}
    for c in criteria["weighted"]:
        fields = c.get("fields") or [c["field"]]
        for field in fields:
            vals = [value(f, field) for f in pool.values()]
            vals = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if not vals:
                continue
            if c["method"] == "lower_is_better_under_limit":
                vals = [v for v in vals if v <= c["limit"]]
                best[field] = min(vals) if vals else None
            else:
                best[field] = max(vals)
    return best


def criterion_points(facts: dict, c: dict, best: dict) -> tuple[float, str | None]:
    """Points for one criterion, plus a note if something was missing."""
    w = c["weight"]
    method = c["method"]

    if method == "higher_is_better":
        v, b = value(facts, c["field"]), best.get(c["field"])
        if v is None:
            return 0.0, f"{c['id']} not stated"
        return w * v / b if b else 0.0, None

    if method == "lower_is_better_under_limit":
        # money or weeks saved under the admin's limit, compared with the biggest saving
        v, b, limit = value(facts, c["field"]), best.get(c["field"]), c["limit"]
        if v is None:
            return 0.0, f"{c['id']} not stated"
        if v > limit:
            return 0.0, f"{c['id']} over the limit"
        if b is None or limit == b:
            return float(w), None
        return w * (limit - v) / (limit - b), None

    if method == "average_higher_is_better":
        parts, missing = [], []
        for field in c["fields"]:
            v, b = value(facts, field), best.get(field)
            if v is None:
                missing.append(field)
                parts.append(0.0)
            else:
                parts.append(v / b if b else 0.0)
        note = f"{', '.join(missing)} not stated" if missing else None
        return w * sum(parts) / len(parts), note

    if method == "checklist":
        ticked = [f for f in c["fields"] if value(facts, f) is True]
        return w * len(ticked) / len(c["fields"]), None

    raise ValueError(f"Unknown scoring method: {method}")


def score(facts: dict, criteria: dict, best: dict) -> tuple[float, dict, list[str]]:
    breakdown, notes = {}, []
    for c in criteria["weighted"]:
        pts, note = criterion_points(facts, c, best)
        breakdown[c["id"]] = round(pts, 2)
        if note:
            notes.append(note)
    return round(sum(breakdown.values()), 1), breakdown, notes


# ---------- putting it together ----------

def rank(all_facts: dict, criteria: dict) -> list[dict]:
    flagged, ineligible, pool = {}, {}, {}
    for pid, facts in all_facts.items():
        if facts.get("suspicious_content"):
            flagged[pid] = facts
        elif fails := mandatory_failures(facts, criteria):
            ineligible[pid] = fails
        else:
            pool[pid] = facts

    best = best_values(pool, criteria)
    scored = []
    for pid, facts in pool.items():
        total, breakdown, notes = score(facts, criteria, best)
        scored.append((pid, total, breakdown, notes))
    scored.sort(key=lambda x: x[1], reverse=True)

    results = []
    for i, (pid, total, breakdown, notes) in enumerate(scored, start=1):
        strongest = max(breakdown, key=lambda k: breakdown[k] / weight(criteria, k))
        reason = f"Passes all mandatory checks; strongest on {strongest}"
        if notes:
            reason += f"; {'; '.join(notes)} (0 points, clarification requested)"
        results.append({"proposal": pid, "rank": i, "status": "ranked", "score": total,
                        "reason": reason + ".", "breakdown": breakdown})

    for pid, facts in flagged.items():
        ref, _, _ = score(facts, criteria, best)  # reference only, never used to rank
        why = facts["suspicious_content"][0]["reason"].rstrip(". ")
        results.append({"proposal": pid, "rank": None, "status": "flagged", "score": None,
                        "reason": f"{why}; held for human review (on facts alone it would score {ref})."})

    for pid, fails in ineligible.items():
        results.append({"proposal": pid, "rank": None, "status": "ineligible", "score": None,
                        "reason": f"Fails mandatory criterion: {'; '.join(fails)}."})
    return results


def weight(criteria: dict, cid: str) -> float:
    return next(c["weight"] for c in criteria["weighted"] if c["id"] == cid)


def compare(results: list[dict], expected_path: Path) -> bool:
    expected = {r["proposal"]: r for r in json.loads(expected_path.read_text())}
    ok = True
    for r in results:
        e = expected.get(r["proposal"], {})
        same = all(r[k] == e.get(k) for k in ("rank", "status", "score"))
        ok &= same
        print(f"  {r['proposal']}: {'match' if same else 'DIFFERENT'}"
              + ("" if same else f"  got {r['rank']}/{r['status']}/{r['score']}, expected {e.get('rank')}/{e.get('status')}/{e.get('score')}"))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--facts", default=HERE / "sample_facts.json", type=Path)
    ap.add_argument("--criteria", default=HERE / "criteria.json", type=Path)
    ap.add_argument("--out", default=HERE / "output" / "ranking.json", type=Path)
    ap.add_argument("--check", type=Path, help="expected ranking.json to compare against")
    args = ap.parse_args()

    criteria = json.loads(args.criteria.read_text())
    results = rank(load_facts(args.facts), criteria)

    print(f"Category: {criteria['category']} (criteria {criteria['version']})\n")
    for r in results:
        rank_txt = r["rank"] if r["rank"] else "-"
        score_txt = r["score"] if r["score"] is not None else "-"
        print(f"{r['proposal']}  rank {rank_txt:<2} {r['status']:<11} score {score_txt:<5} {r['reason']}")
        if "breakdown" in r:
            print(f"   breakdown: {r['breakdown']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps([{k: v for k, v in r.items() if k != "breakdown"} for r in results], indent=2))
    print(f"\nSaved to {args.out}")

    if args.check:
        print(f"\nComparing with {args.check}:")
        print("All match." if compare(results, args.check) else "Differences found.")


if __name__ == "__main__":
    main()