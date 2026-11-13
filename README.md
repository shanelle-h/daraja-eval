# Daraja & Kenya-DPA Eval: where frontier models slip on Kenyan fintech specifics

> **TODO before submitting:** replace the single `<<VIDEO LINK>>` placeholder in section 2 with your real link, then delete this note.

## 1. Short description
Domain: Kenyan fintech engineering and compliance (Safaricom M-Pesa Daraja APIs + the Kenya Data Protection Act 2019).
The gap: models know generic payment APIs but blur Daraja's quirks (the same result code meaning different things per API,
numeric vs string result codes, async acknowledgements treated as success, C2B URL and validation rules) and Kenyan legal specifics
(DPA breach clocks, data localisation scope). Ten graded tasks with structured, deterministically scored answers.

**Key finding:** on the same 10 tasks, `gpt-oss-120b` passed 15/30 attempts (50%) and `qwen3.8-27b` 13/30 (43%). Neither passed
T03 (exact C2B reject code), T04 (production URL rules), T05 (STK vs B2C `2001`) or T08 (DPA breach section and processor deadline) on any answered attempt.
The failures are confident, specific and wrong: invented section numbers (s.31, s.45 instead of s.43), invented result codes, and
"one code means one thing" over-generalisation.

## 2. Video walkthrough
<<https://drive.google.com/file/d/1I7nYV8Z2DGYc9ZAQ4ZryWyffkvN-VYQE/view?usp=sharing>>

https://drive.google.com/file/d/1I7nYV8Z2DGYc9ZAQ4ZryWyffkvN-VYQE/view?usp=sharing

## 3. Domain and expertise
Kenyan fintech software engineering (the author builds and ships payment integrations at a Nairobi fintech) plus
data-protection compliance for payments. Expected answers were drafted from public Safaricom Daraja documentation,
SDK documentation, the Data Protection Act 2019 and its 2021 Regulations, then checked by the author
(see `docs/verification_checklist.md`).

## 4. What it tests and why it matters
It measures whether a model gives *operationally correct* answers on details that cause real production bugs and
compliance misses in Kenya: marking unpaid orders as paid, never marking paid orders as paid, mis-diagnosing a failed payout,
registering unusable C2B URLs, or missing a 72-hour breach deadline. Audience: developers integrating M-Pesa, fintech compliance
officers, and anyone using an AI assistant for Kenyan payments work. Local-law and local-API specifics are under-represented
in training data, and wrong answers read as confident.

Answer-key note (T08): expected values follow the Data Protection Act 2019, s.43(1)(a) (the controller notifies the Data Commissioner
within 72 hours of becoming aware, where there is a real risk of harm) and s.43(3) (the processor notifies the controller without delay and,
where reasonably practicable, within 48 hours). The controller's clock starts when it is aware of a breach posing real risk of harm
(the compliance officer's confirmation at 11:30), giving Fri 2026-11-06 11:30.

Tasks (details and rationale in `tasks/tasks.json`):

| ID | Topic | Judgment/edge case |
|---|---|---|
| T01 | STK callback handler bug | int vs string `ResultCode`; decoy lines that are correct |
| T02 | STK Query after missed callback | `ResponseCode 0` is not payment success; string type |
| T03 | C2B validation | exact reject code, validation must be enabled, fail-closed `ResponseType` |
| T04 | C2B production URL rules | keyword/HTTPS/tunnel rules, one-time registration fix |
| T05 | Decode 4 failures | `2001` means wrong PIN (STK) vs invalid initiator (B2C) |
| T06 | B2C async semantics | sync ack vs result; fix before retry |
| T07 | Build STK request | timestamp, Base64 password, phone normalisation incl. 01xx and invalid input |
| T08 | DPA breach timeline | s.43, processor 48h, controller 72h clock start |
| T09 | Data localisation | strategic-interest scope vs ordinary private payments; transfer safeguards |
| T10 | C2B v2 masking | MSISDN unusable; design alternative |

## 5. Setup and run instructions
Requires Python 3.9+ and at least one API key. The results below used Groq's OpenAI-compatible API (free tier).
```bash
cd daraja-eval
python -m venv .venv && source .venv/bin/activate      # optional (Windows: .venv\Scripts\activate)
pip install -r requirements.txt                         # just `requests`
cp .env.example .env                                    # then add GROQ_API_KEY (or export it as an env var)
python selftest.py                                      # validates the grader offline (no API calls, no cost)
python run_eval.py --runs 3 --temperature 0 --models-filter groq --workers 1
```
`models.json` also lists Google and Anthropic entries; they are skipped when their key is not set. `--workers 1` avoids Groq's per-minute rate limit (HTTP 429) on the Qwen model.
Useful flags: `--only T05,T07`, `--models-filter qwen`, `--dry-run` (mock models, free), `--regrade results/raw_<stamp>.jsonl`.

Measured runtime and cost: `gpt-oss-120b` 30 calls in about 5 minutes (4 workers), about 53k total tokens. `qwen3.8-27b` 30 calls in about 73 minutes
with 1 worker because rate-limited calls waited and retried, about 49k total tokens. Both ran on Groq's free tier, so no charge; token use is small enough that cost
is negligible on paid plans as well.

## 6. Models tested and results
Run date: 2026-11-07 | temperature 0 | 3 runs per task | max 8,192 output tokens | no tools, no web access | both models served through Groq.

| Model (exact id) | Strict pass | API errors |
|---|---|---|
| `openai/gpt-oss-120b` | 15/30 (50%) | 0 |
| `qwen/qwen3.8-27b` | 13/30 (43%); 13/27 (48%) of answered attempts | 3 (HTTP 429, counted as failed) |

Pass rate per task (attempts passing every field):

| Task | `openai/gpt-oss-120b` | `qwen/qwen3.8-27b` |
|---|---|---|
| T01 STK callback handler | 3/3 (†) | 3/3 |
| T02 STK Query after lost callback | 3/3 | 3/3 |
| T03 C2B validation reject code | 0/3 | 0/3 |
| T04 C2B production URL rules | 0/3 | 0/2 (1 not run, 429) |
| T05 `2001` STK vs B2C | 0/3 | 0/2 (1 not run, 429) |
| T06 B2C async semantics | 3/3 | 3/3 |
| T07 Build STK request | 0/3 (‡) | 2/3 |
| T08 DPA breach clock | 0/3 | 0/3 |
| T09 Data localisation | 3/3 | 0/3 |
| T10 C2B v2 masking | 3/3 | 2/2 (1 not run, 429) |

† `gpt-oss-120b` T01 comes from a re-run (`raw_20261107T140508Z`) after the T01 question was reworded and its code line 6 made safe (`i.get("Value")`). In the first full run the old wording
produced one defensible extra answer that the grader marked wrong; that is a question flaw, so the corrected question was re-run.
‡ In 2 of 3 attempts the model returned empty text: hidden reasoning used the entire 8,192-token budget. That is a budget failure, not a knowledge failure, and it is counted as a failed attempt.

Files used for these numbers: `results/raw_20261107T085913Z.jsonl` (`gpt-oss-120b`, T01-T10), `results/raw_20261107T140508Z.jsonl` (`gpt-oss-120b`, T01 re-run),
`results/raw_20261107T125144Z.jsonl` (Qwen, T01-T10), each with its `scored_*.json` and `summary_*.md`.

**Excluded model:** `gemini-3.8-flash` was run but is not scored. On the free tier 13 of its 30 calls returned HTTP 429, and its T01 attempts ran on the pre-fix question wording.
Its 17 answered attempts are kept in `results/failed_or_superseded/` for transparency (13/17 correct; right on T03 and T05, wrong on T04). Other earlier files there are failed or superseded runs.

## 7. Failure analysis
Tasks failed on every answered attempt by both scored models: **T03, T04, T05, T08**. T09 split the models (`gpt-oss` passed, Qwen failed), and T07 failed mostly on phone numbers.

* **Hallucinated legal citations (T08).** Both models got the 72-hour deadline right but cited the wrong law. `gpt-oss`: "Section 31 of the Kenya Data Protection Act, 2019 deals with data-breach notification" and
  "Section 31(3) requires the processor to inform the controller without undue delay and, where reasonably practicable, within 24 hours". Qwen: "primarily governed by Section 45", with a 72-hour processor deadline.
  The Act's s.43(3) says 48 hours. Each model invented a different section number and wording; they are not confusing one real section.
* **Guessing an exact code (T03).** The correct reject code is `C2B00012`. `gpt-oss` returned `"1"`. Qwen returned `"1024"` in all three runs, and its reasoning shows it guessing:
  "Let's go with `1024` as it is the standard "Validation Failed" code in many Kenyan fintech stacks", including a "Correction" paragraph that says to use `1`, then still ending with `1024`.
* **Over-generalisation (T05).** Both models mapped STK `2001` to invalid initiator credentials. `gpt-oss`: "The credentials (shortcode, passkey, security credential, or consumer key/secret) used to generate the STK request are wrong or not authorized."
  Qwen: "`ResultCode 2001` specifically indicates that the `Initiator` or `SecurityCredential` provided in the request was not recognized or is invalid." The B2C reading is right; applying it to STK is the trap
  (the same code and description mean wrong PIN on STK).
* **Missing a published rule (T04).** Both accepted URLs containing `mpesa` and `exec` as valid in production. Qwen: "Safaricom does not enforce a specific path structure". Both got the one-time-registration fix right.
* **Local-format blind spot (T07).** Both models sometimes rejected valid `01xx` mobile numbers (`0110123456`, `0101234567`) as "not a mobile prefix". Qwen got them right in 2 of 3 runs, so outputs vary between runs even at temperature 0.
  Qwen computed the Base64 password correctly in every answered run, so the main weakness here is the number format, not Base64.
* **Right answer, weak reasoning (T09).** `gpt-oss` passed T09 by reasoning that public bodies are "expected" to keep data in Kenya, not by applying the regulation's strategic-interest test. Final-answer grading cannot see that, which is a known limit of this eval.

## 8. Prior work and sources
Nothing here existed before the hackathon; tasks, grader and runner were written for it with AI assistance (Claude) and then
verified by the author. No existing benchmark or dataset is used. Facts were drawn from public sources listed per task
(`sources` in `tasks/tasks.json`) and `docs/verification_checklist.md`: Safaricom Daraja documentation (via public mirrors/SDK docs),
the Kenya Data Protection Act 2019 (s.43 checked against the Act's text), and the Data Protection (General) Regulations 2021. Passkeys and numbers in the tasks are fictitious.

---
## Scoring logic
* **No LLM judge.** Each task ends with a required JSON object. `grader.py` takes the last JSON object in the response and
  compares every field with the expected value using a per-field rule: case-insensitive enum, case-sensitive exact string
  (for Base64), integer, boolean (also accepts "true"/"false"), order-insensitive set (line numbers, URL letters), ordered list
  (phones), or datetime (tolerates `T`, seconds, timezone suffix).
* **Field score** = correct fields / total fields. **Strict pass** = all fields correct. The headline number is the **strict pass rate**.
  A missing/unparseable JSON block scores 0 (reported separately as "Unparseable"). API failures are retried 4 times, then counted as failed attempts and reported.
* **Reliability check of the grader** (`python selftest.py`): for every task it verifies that the gold answer passes, garbage fails,
  and each single-field corruption of the gold answer is rejected (no false passes), plus formatting variants still pass (no false fails).
* **Residual risk:** an expected answer being wrong or disputed. That is why each task has a rationale, sources and a verification row in `docs/verification_checklist.md`.

## Files
```
README.md  run_eval.py  grader.py  selftest.py  models.json  requirements.txt  .env.example
tasks/tasks.json      # prompts, expected answers, match types, rationale, sources
docs/verification_checklist.md
results/              # raw model outputs + scores from the real runs
results/failed_or_superseded/   # not scored: API failures, smoke tests, superseded runs
```