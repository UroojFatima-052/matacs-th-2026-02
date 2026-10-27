# Prototype

A small working version of the design. Only `extract.py` calls the AI; everything after that is plain code.

| File | What it does |
|---|---|
| `criteria.json` | The admin's criteria for this category: fields to extract, mandatory rules, weights and scoring method. Nothing about the category is hard-coded in the scripts. |
| `extract.py` | Sends the prompt from [`../PROMPTS.md`](../PROMPTS.md) to the model once per proposal, then checks every quote exists in the text and scans for hidden instructions. Saves facts to `facts/`. |
| `score.py` | No AI. Flags suspicious proposals, applies the mandatory checks, scores with the weights from `criteria.json` and ranks. |
| `sample_facts.json` | Facts for A to E as the extraction step would return them (values only, no proposal text). |

## 1. Score the sample set (no API key needed)

```
cd prototype
python score.py --check ../ranking.json
```

This reproduces [`../ranking.json`](../ranking.json) from `sample_facts.json` and prints `All match.` with the per-criterion breakdown for each proposal.

## 2. Run the full pipeline with the AI

The brief asks not to commit the proposal text, so add it yourself:

1. Create `prototype/samples/` and save each proposal as `A.txt` ... `E.txt` (this folder is in `.gitignore`).
2. Set up the key:
   ```
   pip install -r requirements.txt
   copy .env.example .env
   ```
   Put a Google AI Studio key in `API_KEY` (use `cp` on Mac/Linux).
3. Run:
   ```
   python extract.py
   python score.py --facts facts/ --check ../ranking.json
   ```

`python extract.py --dry-run` prints the exact prompt without calling the model.

**Tested:** a real run with `gemini-3.5-flash-lite` on A to E returned 0 unverified quotes, caught C's hidden instruction twice (once by the model, once by the code scan), and `score.py --facts facts/` gave `All match.` against `ranking.json`.

## Design points you can see in the code

- **One AI call per proposal.** If `facts/<letter>.json` already exists, `extract.py` skips the call. Change a weight in `criteria.json` and re-run `score.py`: new ranking, zero AI calls.
- **No quote, no fact.** A field whose quote isn't found word for word in the text becomes `unverified` and scores 0 until a person checks it.
- **Two layers against manipulation.** The model reports instruction-like text, and code runs its own pattern scan. Either one flags the proposal.
- **Audit trail.** Each extraction writes a line to `facts/audit.jsonl` with time, model, prompt version, criteria version and check results.