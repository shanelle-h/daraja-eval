#!/usr/bin/env python3
"""Run the Daraja/Kenya-DPA eval against one or more models and grade the answers.

Examples:
  python run_eval.py --runs 3                       # all enabled models in models.json
  python run_eval.py --only T05,T07 --runs 1        # subset of tasks
  python run_eval.py --models-filter claude-sonnet  # subset of models (substring of key)
  python run_eval.py --dry-run                      # no API calls; mock model answers
  python run_eval.py --regrade results/raw_XXXX.jsonl   # re-score saved outputs offline
"""
import argparse, json, os, sys, time, datetime, concurrent.futures as cf
from collections import defaultdict
import requests
from grader import grade_task

ROOT = os.path.dirname(os.path.abspath(__file__))
PROMPT_PREFIX = ("You are an expert Kenyan fintech engineer and compliance specialist. "
                 "Answer the following question precisely.\n\n")


def load_env():
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ------------------------------------------------------------------ providers
def call_anthropic(m, prompt, temperature, max_tokens):
    body = {"model": m["id"], "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if temperature is not None and m.get("send_temperature", True):
        body["temperature"] = temperature
    body.update(m.get("extra", {}))
    r = requests.post("https://api.anthropic.com/v1/messages", json=body, timeout=300, headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    r.raise_for_status()
    j = r.json()
    return "".join(b.get("text", "") for b in j["content"] if b.get("type") == "text"), j.get("usage")


def call_openai(m, prompt, temperature, max_tokens):
    body = {"model": m["id"], "max_completion_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if temperature is not None and m.get("send_temperature", True):
        body["temperature"] = temperature
    body.update(m.get("extra", {}))
    base = m.get("base_url", "https://api.openai.com/v1").rstrip("/")   # any OpenAI-compatible API (e.g. Groq)
    key = os.environ[m.get("key_env", "OPENAI_API_KEY")]
    r = requests.post(f"{base}/chat/completions", json=body, timeout=300,
                      headers={"Authorization": f"Bearer {key}"})
    r.raise_for_status()
    j = r.json()
    return j["choices"][0]["message"]["content"] or "", j.get("usage")


def call_google(m, prompt, temperature, max_tokens):
    gen = {"maxOutputTokens": max_tokens}
    if temperature is not None and m.get("send_temperature", True):
        gen["temperature"] = temperature
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": gen}
    body.update(m.get("extra", {}))
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m['id']}:generateContent",
                      json=body, timeout=300, headers={"x-goog-api-key": os.environ["GOOGLE_API_KEY"]})
    r.raise_for_status()
    j = r.json()
    parts = j["candidates"][0]["content"].get("parts", [])
    return "".join(p.get("text", "") for p in parts), j.get("usageMetadata")


def call_mock(m, prompt, task):
    if m["provider"] == "mock_gold":
        return "Reasoning omitted.\n```json\n" + json.dumps(task["expected"]) + "\n```", None
    return "I am not sure.\n```json\n{}\n```", None


PROVIDERS = {"anthropic": call_anthropic, "openai": call_openai, "google": call_google}


def one_call(m, task, run_idx, temperature, max_tokens, retries=6):
    prompt = PROMPT_PREFIX + task["prompt"]
    rec = {"model_key": m["key"], "model_id": m["id"], "provider": m["provider"], "task_id": task["id"],
           "run_idx": run_idx, "temperature": temperature if m.get("send_temperature", True) else None,
           "max_tokens": max_tokens, "timestamp": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z"}
    t0 = time.time()
    for attempt in range(retries):
        try:
            if m["provider"].startswith("mock"):
                text, usage = call_mock(m, prompt, task)
            else:
                text, usage = PROVIDERS[m["provider"]](m, prompt, temperature, max_tokens)
            rec.update(response_text=text, usage=usage, error=None)
            break
        except Exception as e:  # network, 429, 5xx
            rec.update(response_text="", usage=None, error=f"{type(e).__name__}: {e}")
            code = getattr(getattr(e, "response", None), "status_code", None)
            time.sleep(25 * (attempt + 1) if code == 429 else 2 ** attempt * 2)   # free tiers: wait out the rate limit
    rec["latency_s"] = round(time.time() - t0, 2)
    return rec


# ------------------------------------------------------------------ reporting
def score_and_report(raw_path, tasks_by_id, out_dir):
    recs = [json.loads(l) for l in open(raw_path)]
    scored = []
    for r in recs:
        g = grade_task(tasks_by_id[r["task_id"]], r["response_text"])
        scored.append({**{k: r[k] for k in ("model_key", "model_id", "task_id", "run_idx", "error")}, **g})
    stamp = os.path.basename(raw_path).replace("raw_", "").replace(".jsonl", "")
    with open(os.path.join(out_dir, f"scored_{stamp}.json"), "w") as f:
        json.dump(scored, f, indent=2)

    by_model = defaultdict(list)
    by_mt = defaultdict(list)
    for s in scored:
        by_model[(s["model_key"], s["model_id"])].append(s)
        by_mt[(s["model_key"], s["task_id"])].append(s)
    models = sorted(by_model)
    lines = [f"# Results ({stamp})", "",
             "Pass = every field of the task correct. Field score = fraction of fields correct. "
             "Errors (API failures) count as failed attempts and are listed.", "",
             "| Model | Attempts | Strict pass rate | Mean field score | Unparseable | API errors |", "|---|---|---|---|---|---|"]
    for key, mid in models:
        ss = by_model[(key, mid)]
        n = len(ss)
        lines.append(f"| `{mid}` | {n} | {sum(s['passed'] for s in ss)/n:.0%} | {sum(s['score'] for s in ss)/n:.2f} | "
                     f"{sum(not s['parse_ok'] for s in ss)} | {sum(bool(s['error']) for s in ss)} |")
    tids = sorted(tasks_by_id)
    lines += ["", "## Pass rate per task (fraction of attempts passing all fields)", "",
              "| Task | " + " | ".join(f"`{m[1]}`" for m in models) + " |", "|---|" + "---|" * len(models)]
    for t in tids:
        row = []
        for key, _ in models:
            ss = by_mt.get((key, t), [])
            row.append(f"{sum(s['passed'] for s in ss)}/{len(ss)}" if ss else "-")
        lines.append(f"| {t} {tasks_by_id[t]['title']} | " + " | ".join(row) + " |")
    lines += ["", "## Field-level misses (task.field: attempts wrong / attempts)", ""]
    miss = defaultdict(lambda: [0, 0])
    for s in scored:
        for fld, ok in s["fields"].items():
            miss[(s["task_id"], fld)][1] += 1
            miss[(s["task_id"], fld)][0] += (not ok)
    for (t, fld), (w, n) in sorted(miss.items(), key=lambda kv: -kv[1][0] / kv[1][1]):
        if w:
            lines.append(f"- {t}.{fld}: {w}/{n}")
    p = os.path.join(out_dir, f"summary_{stamp}.md")
    open(p, "w").write("\n".join(lines) + "\n")
    return p, "\n".join(lines)


def main():
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.path.join(ROOT, "tasks", "tasks.json"))
    ap.add_argument("--models", default=os.path.join(ROOT, "models.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "results"))
    ap.add_argument("--runs", type=int, default=3, help="attempts per task per model")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=8192, help="generous: reasoning models spend tokens thinking")
    ap.add_argument("--workers", type=int, default=2, help="keep low on free tiers to avoid rate limits")
    ap.add_argument("--only", default="", help="comma-separated task ids")
    ap.add_argument("--models-filter", default="", help="substring of model key")
    ap.add_argument("--dry-run", action="store_true", help="use mock models, no API calls")
    ap.add_argument("--regrade", default="", help="path to raw_*.jsonl to re-score offline")
    a = ap.parse_args()

    tasks = json.load(open(a.tasks))["tasks"]
    tasks_by_id = {t["id"]: t for t in tasks}
    os.makedirs(a.out, exist_ok=True)

    if a.regrade:
        p, text = score_and_report(a.regrade, tasks_by_id, a.out)
        print(text)
        return

    if a.only:
        keep = set(a.only.split(","))
        tasks = [t for t in tasks if t["id"] in keep]

    if a.dry_run:
        models = [{"key": "mock_gold", "provider": "mock_gold", "id": "mock-gold"},
                  {"key": "mock_bad", "provider": "mock_bad", "id": "mock-bad"}]
    else:
        models = [m for m in json.load(open(a.models))["models"] if m.get("enabled", True)]
        models = [m for m in models if a.models_filter in m["key"]]
        keyvar = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GOOGLE_API_KEY"}
        ok = []
        for m in models:
            if m["id"].startswith("REPLACE"):
                print(f"skip {m['key']}: model id not set in models.json")
            elif not os.environ.get(m.get("key_env") or keyvar[m["provider"]]):
                print(f"skip {m['key']}: {m.get('key_env') or keyvar[m['provider']]} not set")
            else:
                ok.append(m)
        models = ok
    if not models:
        sys.exit("No runnable models. Set keys in .env and model ids in models.json (or use --dry-run).")

    jobs = [(m, t, i) for m in models for t in tasks for i in range(a.runs)]
    print(f"{len(models)} models x {len(tasks)} tasks x {a.runs} runs = {len(jobs)} calls")
    stamp = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).strftime("%Y%m%dT%H%M%SZ")
    raw_path = os.path.join(a.out, f"raw_{stamp}.jsonl")
    done = 0
    with cf.ThreadPoolExecutor(a.workers) as ex, open(raw_path, "w") as f:
        futs = [ex.submit(one_call, m, t, i, a.temperature, a.max_tokens) for m, t, i in jobs]
        for fu in cf.as_completed(futs):
            f.write(json.dumps(fu.result()) + "\n")
            f.flush()
            done += 1
            if done % 10 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)}")
    p, text = score_and_report(raw_path, tasks_by_id, a.out)
    print(text)
    print(f"\nraw outputs: {raw_path}\nsummary: {p}")


if __name__ == "__main__":
    main()