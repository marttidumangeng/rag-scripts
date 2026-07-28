"""list_queue.py — Print the full ranked discovery queue from the triage report."""
import json, os

triage_path = os.path.join(os.path.dirname(__file__), "staging", "reports", "content-queue-triage.json")
with open(triage_path, encoding="utf-8") as f:
    data = json.load(f)

# Support both list and dict formats
if isinstance(data, list):
    candidates = data
else:
    candidates = data.get("all_companies") or data.get("top") or data.get("candidates") or data.get("queue") or data.get("results") or []

print(f"Total companies in queue: {len(candidates)}")
print(f"Triage generated: {data.get('generated_at', data.get('scanned_at', 'unknown')) if isinstance(data, dict) else 'N/A'}\n")
print(f"{'#':<4} {'Score':>6} {'Robots':>7} {'ID':>6}  {'Company':<50} Website")
print("-" * 115)
for i, c in enumerate(candidates, 1):
    site = c.get("website") or c.get("site") or "-"
    site_disp = site[:45] if site != "-" else "-"
    cid = c.get("company_id") or c.get("id") or ""
    name = c.get("company_name") or c.get("name") or ""
    score = c.get("rank_score") or c.get("score") or 0
    n = c.get("incomplete_count") or c.get("n_incomplete") or c.get("n") or 0
    done = c.get("done", False)
    done_marker = " [DONE]" if done else ""
    gaps = c.get("gap_counts", {})
    gap_str = " | ".join(f"{k.replace('no_','')}:{v}" for k, v in gaps.items() if v)
    print(f"{i:<4} {score:>6} {n:>7} {cid:>6}  {name:<45}{done_marker:<7} {site_disp}")
