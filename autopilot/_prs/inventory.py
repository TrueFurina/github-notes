"""盘点 TrueFurina 在 Octop 三仓的 PR 全生命周期 + open PR 候选明细。

口径：
  - 以列表接口为准（search 对 repo: 索引不全，见知识沉淀 错误账本 #7）
  - 只统计 author.login == ME 的 PR（不含别人）
  - merged 以 merged_at 非空判定；closed 未合入单列
"""
import json, os, urllib.request

TOKEN = os.environ["GITHUB_TOKEN"]
ME = "TrueFurina"
REPOS = ["TencentCloud/Octop", "TencentCloud/octop-harness", "TencentCloud/octop-memory"]
H = {"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
     "User-Agent": "pr-inventory"}


def api(url):
    last = None
    for _ in range(4):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=40).read().decode())
        except Exception as e:
            last = e
            continue
    raise RuntimeError(f"失败: {last} :: {url}")


# 本机代理在 ~500KB 处截断（ghlib 的教训，实测 per_page=30 → 493KB+60KB 缺）
# PR 列表对象本身很大，压到 10 页均 ~180KB 才稳定
PER = 10


def all_pages(path):
    out, page = [], 1
    while True:
        u = f"https://api.github.com{path}{'&' if '?' in path else '?'}per_page={PER}&page={page}"
        b = api(u)
        if not b:
            return out
        out += b
        if len(b) < PER:
            return out
        page += 1


summary, open_prs = {}, []
for repo in REPOS:
    prs = all_pages(f"/repos/{repo}/pulls?state=all&sort=created&direction=desc")
    mine = [p for p in prs if (p.get("user") or {}).get("login") == ME]
    op = [p for p in mine if p["state"] == "open"]
    merged = [p for p in mine if p.get("merged_at")]
    closed = [p for p in mine if p["state"] == "closed"]
    summary[repo] = {"total": len(mine), "open": len(op), "merged": len(merged),
                     "closed_unmerged": len(closed) - len(merged), "closed": len(closed),
                     "repo_total_prs": len(prs)}
    open_prs += [dict(p, _repo=repo) for p in op]

print("== 全生命周期（author=TrueFurina）==")
t = {"total": 0, "open": 0, "merged": 0, "closed_unmerged": 0}
for r, s in summary.items():
    print(f"{r:34} total={s['total']:4} open={s['open']:3} merged={s['merged']:3} "
          f"closed_unmerged={s['closed_unmerged']:3}  (仓内 PR 总数 {s['repo_total_prs']})")
    for k in t:
        t[k] += s[k]
print(f"{'TRIO 合计':34} total={t['total']:4} open={t['open']:3} merged={t['merged']:3} "
      f"closed_unmerged={t['closed_unmerged']:3}")

json.dump({"summary": summary, "totals": t}, open(r"d:\github\_prs\lifecycle.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
json.dump(open_prs, open(r"d:\github\_prs\open_prs.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

print(f"\n== open PR 明细（{len(open_prs)} 条，拉 files/comments 中）==")
rows = []
for i, p in enumerate(open_prs, 1):
    repo, n = p["_repo"], p["number"]
    try:
        files = all_pages(f"/repos/{repo}/pulls/{n}/files")
        comments = all_pages(f"/repos/{repo}/issues/{n}/comments")
        reviews = api(f"https://api.github.com/repos/{repo}/pulls/{n}/reviews?per_page=30")
    except Exception as e:
        print(f"  #{n} ERR {e}")
        continue
    paths = [f["filename"] for f in files]
    tests = [x for x in paths if "test" in x.lower()]
    add = sum(f["additions"] for f in files)
    dele = sum(f["deletions"] for f in files)
    last_author = comments[-1]["user"]["login"] if comments else ""
    rows.append({"repo": repo, "n": n, "title": p["title"], "files": len(files),
                 "add": add, "del": dele, "tests": len(tests), "comments": len(comments),
                 "reviews": len(reviews), "last_comment_by": last_author,
                 "mergeable_state": p.get("mergeable_state"), "created": p["created_at"][:10],
                 "paths": paths})
    if i % 20 == 0:
        print(f"  ...{i}/{len(open_prs)}")

rows.sort(key=lambda r: (r["files"], r["add"] + r["del"]))
json.dump(rows, open(r"d:\github\_prs\open_detail.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print("\n== 最小改动面 Top 25（files, +/-, 是否有测试, 评论/评审) ==")
print(f"{'#':>5} {'文件':>3} {'+':>5} {'-':>4} {'test':>4} {'评论':>4} {'评审':>4} {'state':>9} {'最后评论者':<12} 标题")
for r in rows[:25]:
    print(f"{r['n']:>5} {r['files']:>3} {r['add']:>5} {r['del']:>4} {r['tests']:>4} "
          f"{r['comments']:>4} {r['reviews']:>4} {str(r['mergeable_state']):>9} "
          f"{r['last_comment_by'][:12]:<12} {r['title'][:58]}")
