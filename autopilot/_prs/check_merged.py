import json, os, urllib.request

H = {"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
     "Accept": "application/vnd.github+json", "User-Agent": "x"}


def g(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30).read().decode())


for n in (2174, 2687, 2708, 2722, 2723):
    p = g(f"https://api.github.com/repos/TencentCloud/Octop/pulls/{n}")
    print(f"#{n} author={p['user']['login']} state={p['state']} merged={bool(p.get('merged_at'))} "
          f"merged_at={p.get('merged_at')} closed_at={p.get('closed_at')} | {p['title'][:56]}")
