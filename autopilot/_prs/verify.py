"""核实 open PR 真实数量（REST list）并拉重点候选的规模/文件明细。"""
import json, os, time, urllib.request

TOKEN = os.environ["GITHUB_TOKEN"]
ME = "TrueFurina"
REPOS = ["TencentCloud/Octop", "TencentCloud/octop-harness", "TencentCloud/octop-memory"]
H = {"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
     "User-Agent": "pr-verify"}
CAND = {"TencentCloud/Octop": [2731, 2687],
        "TencentCloud/octop-harness": [197, 164, 165, 163, 132, 129, 127, 124],
        "TencentCloud/octop-memory": [30, 33, 34, 35, 36]}


def get(url, tries=4):
    last = None
    for i in range(tries):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30).read().decode())
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{last} :: {url}")


print("== REST 实拉 open PR（state=open，per_page=10 抗代理截断）==")
tot = 0
for repo in REPOS:
    page, mine = 1, []
    while True:
        prs = get(f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=10&page={page}")
        mine += [p for p in prs if (p.get("user") or {}).get("login") == ME]
        if len(prs) < 10:
            break
        page += 1
    print(f"  {repo}: 本人 open={len(mine)}（翻了 {page} 页）")
    tot += len(mine)
print(f"TRIO 本人 open 合计 = {tot}")

print("\n== #2687 状态 ==")
p = get("https://api.github.com/repos/TencentCloud/Octop/pulls/2687")
print(f"  state={p['state']} merged={bool(p.get('merged_at'))} merged_at={p.get('merged_at')} "
      f"head={p['head']['ref']} +{p['additions']}/-{p['deletions']} files={p['changed_files']}")

print("\n== 候选明细 ==")
for repo, nums in CAND.items():
    for n in nums:
        try:
            pr = get(f"https://api.github.com/repos/{repo}/pulls/{n}")
            files = get(f"https://api.github.com/repos/{repo}/pulls/{n}/files?per_page=30")
        except Exception as e:
            print(f"  {repo}#{n} ERR {e}")
            continue
        tests = [f["filename"] for f in files if "test" in f["filename"].lower()]
        last = ""
        try:
            cs = get(f"https://api.github.com/repos/{repo}/issues/{n}/comments?per_page=10")
            last = (cs[-1]["user"]["login"] if cs else "")
        except Exception:
            pass
        print(f"\n  {repo}#{n} state={pr['state']} draft={pr['draft']} "
              f"+{pr['additions']}/-{pr['deletions']} files={pr['changed_files']} "
              f"comments={pr['comments']} reviews={pr['review_comments']} last={last}")
        print(f"    {pr['title']}")
        for f in files:
            print(f"      {f['status']:<8} +{f['additions']:<4} -{f['deletions']:<4} {f['filename']}")
        print(f"    test files: {tests or '（无）'}")
