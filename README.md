# MATACS-TH-2026-02: AI Proposal Triage Design

**Candidate:** Urooj Fatima

**Reference:** MATACS-TH-2026-02

**Time spent:** about 2 hours for the design (roughly 1 hour reading the brief and planning the flow and diagram, about 1 hour writing the files)

## Files

| File | What it is |
|---|---|
| [`diagram/process-flow.png`](diagram/process-flow.png) | Process flow from upload to ranked output, showing AI steps, code steps and human checkpoints |
| [`WRITEUP.md`](WRITEUP.md) | Answers to the five questions |
| [`PROMPTS.md`](PROMPTS.md) | The extraction prompt, exactly as it would be sent |
| [`ranking.json`](ranking.json) | Expected ranking of proposals A to E |
| [`prototype/`](prototype/) | Optional: extraction script plus a scoring script that reproduces `ranking.json` (see [`prototype/README.md`](prototype/README.md)) |

## The design in one line

AI only reads each proposal and pulls out the facts with exact quotes. Code checks those quotes, applies the admin's pass/fail rules and does all the scoring. A person reviews and makes the final award.

## How I used AI tools

I used Claude to help plan the flow, draft the prompt and write-up, and build the prototype. I reviewed, questioned and edited everything before committing. 

I asked Claude to use the AI for extraction and do all the scoring in code because this helps in reducing the AI calls and also the re-using saved facts ensures that any data inputted twice gets the same output. I had already used the same split in my [Women Tech Quest 2026 project](https://github.com/UroojFatima-052/wtq-2026) where I had limited API calls and that design decision helped me using the calls efficiently.

Where I disagreed and corrected it: Claude suggested that D should be declared as "ineligible" because it has missing timeline but I disagreed and asked it to include D in ranking. I did that because timeline was never stated as mandatory requirement for ranking and AI should never guess or create any rule. If something is missing just simply give it 0 points and ask the Human for review, no need to drop it.
