"""精简 GraphQL 盘点：只取 state/mergedAt/author，单页 100 条、载荷小，不会触发代理截断。"""
import json, os, urllib.request

TOKEN = os.environ["GITHUB_TOKEN"]
ME = "TrueFurina"
REPOS = [("TencentCloud", "Octop"), ("TencentCloud", "octop-harness"), ("TencentCloud", "octop-memory")]
Q = """
query($o:String!,$n:String!,$c:String){
  repository(owner:$o,name:$n){
    pullRequests(first:100, after:$c, states:[OPEN,CLOSED,MERGED]){
      totalCount pageInfo{hasNextPage endCursor}
      nodes{ number state mergedAt author{login} }
    }
  }
}
"""


def gql(v):
    body = json.dumps({"query": Q, "variables": v}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "Authorization": "Bearer " + TOKEN, "Content-Type": "application/json", "User-Agent": "x"})
    return json.loads(urllib.request.urlopen(req, timeout=40).read().decode())


tot = {"total": 0, "open": 0, "merged": 0, "closed_unmerged": 0}
for o, n in REPOS:
    nodes, cursor = [], None
    while True:
        d = gql({"o": o, "n": n, "c": cursor})
        if "errors" in d:
            raise SystemExit(d["errors"])
        r = d["data"]["repository"]["pullRequests"]
        nodes += r["nodes"]
        if not r["pageInfo"]["hasNextPage"]:
            break
        cursor = r["pageInfo"]["endCursor"]
    mine = [x for x in nodes if (x.get("author") or {}).get("login") == ME]
    s = {"total": len(mine), "open": sum(x["state"] == "OPEN" for x in mine),
         "merged": sum(bool(x.get("mergedAt")) for x in mine),
         "closed_unmerged": sum(x["state"] == "CLOSED" and not x.get("mergedAt") for x in mine)}
    print(f"{o}/{n:14} 提交={s['total']:4} open={s['open']:3} merged={s['merged']:3} "
          f"closed_unmerged={s['closed_unmerged']:3}  (仓内 PR 总计 {len(nodes)})")
    for k in tot:
        tot[k] += s[k]
print(f"TRIO 合计        提交={tot['total']:4} open={tot['open']:3} merged={tot['merged']:3} "
      f"closed_unmerged={tot['closed_unmerged']:3}")
json.dump(tot, open(r"d:\github\_prs\lifecycle_real.json", "w", encoding="utf-8"), indent=2)
