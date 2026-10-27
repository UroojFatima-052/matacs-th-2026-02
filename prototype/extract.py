"""Run the extraction prompt from PROMPTS.md on proposal text files.

This is the ONLY file that calls the AI. For each proposal it:
  1. builds the prompt (fixed system prompt + field list generated from criteria.json)
  2. calls the model once (temperature 0, JSON only)
  3. checks every quote really appears in the proposal text (code, not AI)
  4. runs its own scan for instruction-like text (code, not AI)
  5. saves the facts to facts/<letter>.json

Saved facts are reused: if facts/<letter>.json already exists, the AI is not
called again unless you pass --force. Re-scoring never needs the AI.

Usage:
  python extract.py                 # every samples/*.txt
  python extract.py --only A C      # just these proposals
  python extract.py --dry-run       # print the prompt, no AI call
  python score.py --facts facts/    # then score the result
"""
import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
PROMPT_VERSION = "extract-v1"

# Instruction-like phrases aimed at a machine. Code checks for these itself,
# so we don't rely only on the AI to report them.
SUSPICIOUS_PATTERNS = [
    r"automated (review|system|scoring)", r"\bAI\b.*\b(rank|score|approve)",
    r"rank (this|it|us) first", r"full marks", r"ignore (all |previous |the )?instructions",
    r"pre-?approved", r"system prompt",
]


# ---------- prompt ----------

def load_prompts() -> tuple[str, str]:
    """Read the system prompt and user template from PROMPTS.md, so the file is the single source of truth."""
    text = (HERE.parent / "PROMPTS.md").read_text(encoding="utf-8")
    system = re.search(r"## 1\. System prompt\s+```text\n(.*?)```", text, re.S).group(1).strip()
    user = re.search(r"## 2\. User message.*?```text\n(.*?)```", text, re.S).group(1).strip()
    return system, user


def field_list(criteria: dict) -> str:
    """Turn the admin's field definitions into the {{fields}} list."""
    lines = []
    for name, desc in criteria["fields"].items():
        kind, _, explain = desc.partition(": ")
        lines.append(f"- {name} ({kind})" + (f": {explain}" if explain else ""))
    return "\n".join(lines)


def build_user_message(template: str, criteria: dict, proposal_text: str) -> str:
    return (template
            .replace("{{category_name}}", criteria["category"])
            .replace("{{project_summary}}", criteria["project"])
            .replace("{{criteria_version}}", criteria["version"])
            .replace("{{fields}}", field_list(criteria))
            .replace("{{proposal_text_with_page_numbers}}", proposal_text))


# ---------- AI call ----------

def call_model(system: str, user: str) -> dict:
    from dotenv import load_dotenv
    from google import genai
    from google.genai import types

    load_dotenv(HERE / ".env")
    key = os.getenv("API_KEY")
    if not key or key == "your-api-key-here":
        raise SystemExit("API_KEY missing. Copy .env.example to .env and add your key.")
    client = genai.Client(api_key=key)
    config = types.GenerateContentConfig(
        system_instruction=system, temperature=0, response_mime_type="application/json")

    for attempt in (1, 2):  # one retry on bad JSON, then give up and send to a person
        reply = client.models.generate_content(model=os.getenv("MODEL_NAME"), contents=user, config=config)
        try:
            return json.loads(reply.text)
        except json.JSONDecodeError:
            if attempt == 2:
                raise
            time.sleep(2)


# ---------- checks done by code ----------

def normalise(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def verify_quotes(facts: dict, proposal_text: str) -> list[str]:
    """Any field whose quote is not found word for word in the text is marked unverified."""
    text = normalise(proposal_text)
    unverified = []
    for name, f in facts.get("fields", {}).items():
        quote = f.get("quote")
        if f.get("status") == "stated" and (not quote or normalise(quote) not in text):
            f["status"] = "unverified"
            f["note"] = "quote not found in the proposal text, check manually"
            unverified.append(name)
    return unverified


def scan_for_instructions(proposal_text: str) -> list[dict]:
    hits = []
    for line in proposal_text.splitlines():
        for pattern in SUSPICIOUS_PATTERNS:
            if re.search(pattern, line, re.I):
                hits.append({"quote": line.strip(), "page": None, "reason": f"code scan matched '{pattern}'"})
                break
    return hits


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default=HERE / "samples", type=Path)
    ap.add_argument("--facts", default=HERE / "facts", type=Path)
    ap.add_argument("--criteria", default=HERE / "criteria.json", type=Path)
    ap.add_argument("--only", nargs="*", help="proposal letters to run, e.g. A C")
    ap.add_argument("--force", action="store_true", help="call the AI again even if facts are saved")
    ap.add_argument("--dry-run", action="store_true", help="print the prompt for the first proposal and stop")
    args = ap.parse_args()

    criteria = json.loads(args.criteria.read_text(encoding="utf-8"))
    system, template = load_prompts()
    files = sorted(args.samples.glob("*.txt"))
    if args.only:
        files = [f for f in files if f.stem in args.only]
    if not files:
        raise SystemExit(f"No proposal .txt files in {args.samples}. See prototype/README.md.")

    args.facts.mkdir(exist_ok=True)
    audit = args.facts / "audit.jsonl"

    for path in files:
        pid, text = path.stem, path.read_text(encoding="utf-8", errors="replace")
        out = args.facts / f"{pid}.json"
        user = build_user_message(template, criteria, text)

        if args.dry_run:
            print("=== SYSTEM ===\n" + system + "\n\n=== USER ===\n" + user)
            return
        if out.exists() and not args.force:
            print(f"{pid}: facts already saved, skipping AI call")
            continue

        facts = call_model(system, user)
        unverified = verify_quotes(facts, text)
        facts.setdefault("suspicious_content", [])
        facts["suspicious_content"] += scan_for_instructions(text)
        out.write_text(json.dumps(facts, indent=2), encoding="utf-8")

        with audit.open("a", encoding="utf-8") as log:
            log.write(json.dumps({
                "time": datetime.now(timezone.utc).isoformat(), "proposal": pid,
                "model": os.getenv("MODEL_NAME"), "prompt_version": PROMPT_VERSION,
                "criteria_version": criteria["version"], "unverified_fields": unverified,
                "suspicious_hits": len(facts["suspicious_content"]), "raw_output_file": out.name,
            }) + "\n")
        print(f"{pid}: saved ({len(unverified)} unverified, {len(facts['suspicious_content'])} suspicious)")


if __name__ == "__main__":
    main()