"""Compare two support-ticket prompt versions against the same labeled cases."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CATEGORIES = {"delivery", "refund", "account", "other"}


def check(raw, expected):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        parsed = json.loads(raw, object_pairs_hook=unique_object)
    except ValueError:
        return ["invalid_json"]
    if not isinstance(parsed, dict) or set(parsed) != {"category", "urgent"}:
        return ["wrong_fields"]
    errors = []
    if not isinstance(parsed["category"], str) or parsed["category"] not in CATEGORIES:
        errors.append("invalid_category")
    elif parsed["category"] != expected["category"]:
        errors.append("wrong_category")
    if type(parsed["urgent"]) is not bool:
        errors.append("invalid_urgent_type")
    elif parsed["urgent"] != expected["urgent"]:
        errors.append("wrong_urgency")
    return errors


def groq_response(model, api_key, prompt, ticket):
    payload = {
        "model": model,
        "temperature": 0,
        "max_completion_tokens": 512,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": ticket},
        ],
    }
    request = Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=45) as response:
            choice = json.load(response)["choices"][0]
            content = choice["message"]["content"]
            if choice.get("finish_reason") == "length":
                raise RuntimeError("Groq output reached the token limit")
            if not isinstance(content, str):
                raise RuntimeError("Groq response has no text content")
            return content
    except HTTPError as error:
        status = error.code
        error.close()
        raise RuntimeError(f"Groq HTTP {status}. Check model access, key or rate limits.") from None
    except (URLError, TimeoutError):
        raise RuntimeError("Groq connection failed or timed out.") from None
    except (ValueError, KeyError, IndexError, TypeError):
        raise RuntimeError("Unexpected Groq response format.") from None


def compare(cases, produce):
    rows = []
    for case in cases:
        row = {"id": case["id"], "ticket": case["ticket"], "expected": case["expected"]}
        for side in ("baseline", "candidate"):
            raw = produce(side, case)
            row[side] = {"output": raw, "errors": check(raw, case["expected"])}
        before = not row["baseline"]["errors"]
        after = not row["candidate"]["errors"]
        row["change"] = {
            (True, False): "regression",
            (False, True): "improvement",
            (True, True): "stable_pass",
            (False, False): "stable_fail",
        }[before, after]
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("demo", "groq"), default="demo")
    parser.add_argument("--baseline", default="prompts/v1.txt")
    parser.add_argument("--candidate", default="prompts/v2.txt")
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--output", type=Path, default=Path("reports/comparison.json"))
    parser.add_argument("--fail-on-regression", action="store_true")
    args = parser.parse_args()

    paths = {"baseline": ROOT / args.baseline, "candidate": ROOT / args.candidate}
    if args.mode == "demo" and (args.baseline, args.candidate) != ("prompts/v1.txt", "prompts/v2.txt"):
        parser.error("Demo replays fixed v1/v2 fixtures. Use --mode groq for custom prompts.")
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if args.mode == "groq" and not api_key:
        parser.error("Set GROQ_API_KEY in this PowerShell session before running live mode.")
    try:
        prompts = {side: path.read_text(encoding="utf-8") for side, path in paths.items()}
        case_text = (ROOT / "data/cases.json").read_text(encoding="utf-8")
        cases = json.loads(case_text)
        if args.mode == "demo":
            overrides = json.loads((ROOT / "data/demo_overrides.json").read_text(encoding="utf-8"))
            versions = {"baseline": "v1", "candidate": "v2"}

            def produce(side, case):
                return overrides[versions[side]].get(case["id"], json.dumps(case["expected"]))
        else:
            def produce(side, case):
                return groq_response(args.model, api_key, prompts[side], case["ticket"])

        rows = compare(cases, produce)
        summary = {
            "cases": len(rows),
            "baseline_pass": sum(not row["baseline"]["errors"] for row in rows),
            "candidate_pass": sum(not row["candidate"]["errors"] for row in rows),
            "regressions": [row["id"] for row in rows if row["change"] == "regression"],
            "improvements": [row["id"] for row in rows if row["change"] == "improvement"],
        }
        report = {
            "mode": args.mode,
            "model": args.model if args.mode == "groq" else None,
            "prompt_sha256": {side: hashlib.sha256(prompt.encode()).hexdigest() for side, prompt in prompts.items()},
            "cases_sha256": hashlib.sha256(case_text.encode()).hexdigest(),
            "summary": summary,
            "cases": rows,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (RuntimeError, OSError, ValueError) as error:
        print(f"Run incomplete: {error}", file=sys.stderr)
        return 2
    print(f"Mode: {args.mode} | Baseline: {summary['baseline_pass']}/{len(rows)} | Candidate: {summary['candidate_pass']}/{len(rows)}")
    print("Regressions:", ", ".join(summary["regressions"]) or "none")
    print("Improvements:", ", ".join(summary["improvements"]) or "none")
    print(f"Report: {args.output}")
    return int(args.fail_on_regression and bool(summary["regressions"]))


if __name__ == "__main__":
    sys.exit(main())
