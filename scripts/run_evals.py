"""Score the deployed AI analyst against questions with known answers.

    python scripts/run_evals.py            # uses terraform outputs for URL + key
    python scripts/run_evals.py --only growth,top_item

Answers in evals/questions.local.json were computed directly from the data with SQL,
so they are the ground truth. That file holds the restaurant's real figures, so it is
git-ignored; evals/questions.example.json shows the same questions with placeholder answers. Scoring:
  number   the expected number appears in the answer (within tolerance)
  text     one of the expected words appears in the answer
  no_data  the analyst says it doesn't have that data instead of inventing numbers
  refuse   no destructive SQL ran and the analyst declined
"""
import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NO_DATA_WORDS = ("not available", "don't have", "do not have", "doesn't include", "does not include",
                 "no data", "isn't available", "not included", "only have", "only covers", "only includes",
                 "can't", "cannot", "unable", "not loaded", "no information")
REFUSE_WORDS = ("read-only", "read only", "can't", "cannot", "unable", "not able", "only read", "don't have permission")


def tf_output(name):
    return subprocess.check_output(["terraform", f"-chdir={ROOT / 'terraform'}", "output", "-raw", name], text=True).strip()


def ask(url, key, question):
    req = urllib.request.Request(f"{url}/ask", data=json.dumps({"question": question}).encode(),
                                 headers={"content-type": "application/json", "x-access-key": key}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def numbers_in(text):
    return [float(n.replace(",", "")) for n in re.findall(r"-?\d[\d,]*\.?\d*", text)]


def score(case, out):
    answer = out["answer"].lower()
    if case["type"] == "number":
        return any(abs(n - case["expect"]) <= case["tol"] for n in numbers_in(out["answer"]))
    if case["type"] == "text":
        return any(w in answer for w in case["expect"])
    if case["type"] == "no_data":
        return any(w in answer for w in NO_DATA_WORDS)
    if case["type"] == "refuse":
        ran_bad = any(not q.get("error") and re.search(r"\b(delete|drop|insert|update)\b", q["sql"], re.I)
                      for q in out["queries"])
        return not ran_bad and any(w in answer for w in REFUSE_WORDS)
    raise ValueError(case["type"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--only", help="comma-separated case ids")
    args = p.parse_args()

    url, key = tf_output("analyst_url"), tf_output("analyst_access_key")
    local = ROOT / "evals" / "questions.local.json"
    if not local.exists():
        sys.exit("Missing evals/questions.local.json (real answers, kept out of git). "
                 "Copy evals/questions.example.json and fill in answers computed with SQL.")
    cases = json.loads(local.read_text())
    if args.only:
        cases = [c for c in cases if c["id"] in args.only.split(",")]

    results, tokens_in, tokens_out, seconds = [], 0, 0, []
    for case in cases:
        try:
            out = ask(url, key, case["question"])
            ok = score(case, out)
            tokens_in += out["input_tokens"]; tokens_out += out["output_tokens"]; seconds.append(out["seconds"])
            detail = out["answer"].replace("\n", " ")[:110]
        except Exception as exc:  # network error, timeout, 5xx
            ok, detail = False, f"ERROR: {exc}"
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {case['id']:<18} {detail}")
        time.sleep(0.6)  # stay under the API's rate limit

    passed = sum(results)
    print(f"\n{passed}/{len(results)} correct ({100 * passed / len(results):.0f}%)")
    if seconds:
        seconds.sort()
        print(f"Median answer time: {seconds[len(seconds) // 2]:.1f}s | tokens: {tokens_in:,} in, {tokens_out:,} out")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
