"""按用户指定口径盘点：每个仓一次 search 请求（is:pr is:open author:TrueFurina），不翻全量历史。"""
import json, os, time, urllib.parse, urllib.request

TOKEN = os.environ["GITHUB_TOKEN"]
ME = "TrueFurina"
REPOS = ["TencentCloud/Octop", "TencentCloud/octop-harness", "TencentCloud/octop-memory"]
H = {"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
     "User-Agent": "pr-search"}


def get(url, tries=4):
    last = None
    for i in range(tries):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30).read().decode())
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{last} :: {url}")


out = {}
for repo in REPOS:
    q = urllib.parse.quote(f"repo:{repo} is:pr is:open author:{ME}")
    d = get(f"https://api.github.com/search/issues?q={q}&per_page=30&sort=created&order=desc")
    items = d.get("items", [])
    out[repo] = items
    print(f"\n### {repo}  open={d.get('total_count')} （本页 {len(items)}）")
    for it in items:
        n = it["number"]
        draft = "D" if it.get("draft") else "-"
        print(f"  #{n:<5} {draft} {it['created_at'][:10]} c={it['comments']:<3} {it['title'][:70]}")

json.dump(out, open(r"d:\github\_prs\open_by_search.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
total = sum(d.get("total_count", 0) for d in out.values())
print(f"\nTRIO open 合计 = {total}")
