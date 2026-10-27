# Write-up

## 1. AI vs. rules

**AI is used for one step only: reading each proposal and pulling out the facts** (price, weeks, licence, insurance, warranty, installs, team), each with the exact quote and page it came from. Proposals are free text, written differently by every bidder, which is where AI actually helps.

**Everything else is plain code:** getting text out of the PDF, checking the AI's quotes, the suspicious-text scan, the mandatory pass/fail checks, the scoring maths and building the ranked list.

I drew the line there because a pass/fail or a score has to be the same every time and has to be explainable to a bidder who asks "why did I lose?". An AI can give two different scores for the same input, can't show its working reliably, and can be talked into things by text inside the proposal. Code can't. I used the same split in my 10Pearls Women Tech Quest 2026 project (a utility bill decoder): Gemini read the bills, and Python did all the maths, cleanup and self-checks.

## 2. Consistency and explainability

- The AI reads each proposal **once**. The facts are checked and saved, and scoring always runs on the saved facts. Ranking the same proposals twice gives exactly the same result, because the second run is just the same maths on the same numbers.
- The AI call uses a pinned model version, temperature 0 and fixed JSON output.
- Every score uses a fixed formula with the admin's weights:
  - **Experience:** installs ÷ highest install count among bids
  - **Price:** money saved under the $260k ceiling ÷ the biggest saving. I used the ceiling because a plain "cheapest ÷ price" gives every bid about 24/25, so price would barely matter despite being worth 25%.
  - **Timeline:** weeks saved under 16 ÷ the most weeks saved
  - **Warranty:** panel and workmanship years, each compared with the best bid, averaged
  - **Team:** 4-item checklist (named lead, crew, safety plan, monitoring), 3.75 points each
  - "Highest", "biggest" and "best" mean among the eligible, unflagged bids only. Totals are rounded to one decimal.
- The reviewer sees, for each proposal: the total, the points per criterion, a one-line reason, and the **quote from the proposal behind every fact**. Anyone can follow the sum back to the source text.

## 3. Human in the loop

- **Admin** sets the criteria and weights. Each edit creates a new version.
- **Reviewer** checks the extracted facts against the quotes before trusting the ranking. Any fact the code couldn't verify is highlighted.
- **Flagged** proposals are never ranked or rejected automatically. A person decides.
- **Unclear or missing facts** (like D's timeline) trigger a clarification request instead of a guess.
- The reviewer **can override** any fact, score or status, but must write a reason.
- **The final award is always a person's decision.** The tool only recommends.

**Audit log (append-only):** who uploaded what and when, file hash, criteria version, AI model and prompt version, raw AI output with quotes, quote-check and flag results, score breakdown, every override (who, old value, new value, reason) and the final decision.

## 4. Changing criteria

Criteria are versioned. Every scored result records the version it used, so old results never silently change meaning.

**The design keeps AI calls to a minimum.** The AI reads each proposal once and the facts are saved. After that, any change to the criteria only reruns the code, never the AI:

- **Weights or pass/fail rules changed:** code re-scores from the saved facts. No AI call, no extra cost, instant.
- **New criterion that needs a fact we don't have** (e.g. "battery storage offered"): the AI is called only for that one field, then code re-scores.
- **A proposal is replaced** (bidder sends a revised PDF): only that proposal goes through the AI again.
- **Mid-evaluation edits:** the reviewer is warned the ranking uses an older version and chooses to re-score. Both versions stay in the audit log.

## 5. Risks and safeguards

| Risk | Safeguard |
|---|---|
| **Wrong extraction** (misread price, wrong page) | Every fact needs a quote; code checks the quote really exists in the text. Reviewer confirms facts before deciding. |
| **Made-up facts** | AI marks missing facts "not stated" instead of guessing; no quote = no fact. Code gives a missing fact 0 points and asks for clarification, so the proposal stays in the ranking (e.g. D's missing timeline). Only the admin's mandatory criteria can exclude a proposal. |
| **Manipulation** (like C's hidden instruction) | Proposal text is wrapped as data in the prompt; AI reports instruction-like text; code runs its own pattern scan; the AI has no power to score anyway. Flagged proposals go to a person. |
| **Loopholes in mandatory checks** (like B using a subcontractor's licence) | The licence field asks whether the **bidder itself** holds it. "To be confirmed after award" does not pass. |
| **Bias** (e.g. favouring long, polished proposals) | The AI never judges quality; scores come only from facts and fixed formulas. Same rules for every bidder. |
| **Cost** | One AI call per proposal; re-scoring reuses saved facts. |
| **Model changes** | Model version pinned and logged; upgrades tested on known proposals first. |

## Assumptions

- **C's install count** says "since 2020", but the window is the last 5 years. I took the count as stated and noted it for the reviewer to check.
