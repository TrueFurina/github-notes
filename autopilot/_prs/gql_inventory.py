"""GraphQL 版 PR 盘点：单查询返回 state/mergedAt/additions/changedFiles，避免 REST 大分页被代理截断。

输出：
  lifecycle.json       三仓全生命周期（author=TrueFurina）
  open_detail.json     全部 open PR 的规模指标（用于排序）
"""
import json, os, urllib.request

TOKEN = os.environ["GITHUB_TOKEN"]
ME = "TrueFurina"
REPOS = [("TencentCloud", "Octop"), ("TencentCloud", "octop-harness"), ("TencentCloud", "octop-memory")]

Q = """
query($owner:String!,$name:String!,$cursor:String){
  repository(owner:$owner,name:$name){
    pullRequests(first:100, after:$cursor, states:[OPEN,CLOSED,MERGED],
                 orderBy:{field:CREATED_AT,direction:DESC}){
      totalCount
      pageInfo{hasNextPage endCursor}
      nodes{
        number title state mergedAt createdAt additions deletions changedFiles
        author{login}
        comments{totalCount}
        reviews{totalCount}
        isDraft
      }
    }
  }
}
"""


def gql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "Authorization": "Bearer " + TOKEN, "Content-Type": "application/json",
        "User-Agent": "pr-inv"})
    last = None
    for _ in range(4):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=40).read().decode())
        except Exception as e:
            last = e
    raise RuntimeError(str(last))


summary, rows = {}, []
for owner, name in REPOS:
    full = f"{owner}/{name}"
    nodes, cursor, total = [], None, 0
    while True:
        d = gql(Q, {"owner": owner, "name": name, "cursor": cursor})
        if "errors" in d:
            raise RuntimeError(d["errors"])
        r = d["data"]["repository"]["pullRequests"]
        total = r["totalCount"]
        nodes += r["nodes"]
        if not r["pageInfo"]["hasNextPage"]:
            break
        cursor = r["pageInfo"]["endCursor"]
    mine = [n for n in nodes if ((n.get("author") or {}).get("login")) == ME]
    op = [n for n in mine if n["state"] == "OPEN"]
    merged = [n for n in mine if n.get("mergedAt")]
    closed = [n for n in mine if n["state"] == "CLOSED"]
    summary[full] = {"repo_total_prs": total, "total": len(mine), "open": len(op),
                     "merged": len(merged), "closed_unmerged": len(closed) - len(merged),
                     "closed": len(closed)}
    rows += [dict(n, repo=full) for n in op]

print("== 全生命周期（author=TrueFurina，GraphQL 实拉）==")
t = {"total": 0, "open": 0, "merged": 0, "closed_unmerged": 0}
for r, s in summary.items():
    print(f"{r:32} total={s['total']:4} open={s['open']:3} merged={s['merged']:3} "
          f"closed_unmerged={s['closed_unmerged']:3}  (仓内 PR 总数 {s['repo_total_prs']})")
    for k in t:
        t[k] += s[k]
print(f"{'TRIO 合计':32} total={t['total']:4} open={t['open']:3} merged={t['merged']:3} "
      f"closed_unmerged={t['closed_unmerged']:3}")

json.dump(summary, open(r"d:\github\_prs\lifecycle.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(rows, open(r"d:\github\_prs\open_detail.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

rows.sort(key=lambda r: (r["changedFiles"], r["additions"] + r["deletions"]))
print(f"\n== open PR 按改动面排序（{len(rows)} 条，前 30）==")
print(f"{'#':>5} {'仓':<28} {'文件':>3} {'+':>5} {'-':>4} {'评论':>4} {'评审':>4} {'draft':>5} 标题")
short = {"TencentCloud/Octop": "Octop", "TencentCloud/octop-harness": "harness",
         "TencentCloud/octop-memory": "memory"}
for r in rows[:30]:
    print(f"{r['number']:>5} {short[r['repo']]:<28} {r['changedFiles']:>3} {r['additions']:>5} "
          f"{r['deletions']:>4} {r['comments']['totalCount']:>4} {r['reviews']['totalCount']:>4} "
          f"{str(r['isDraft']):>5} {r['title'][:52]}")
