"""拉 harness #197 的正文、patch 与测试文件全文，判断评审缺口。"""
import json, os, time, urllib.request

TOKEN = os.environ["GITHUB_TOKEN"]
H = {"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json", "User-Agent": "x"}
H_RAW = dict(H, Accept="application/vnd.github.raw")


def get(url, h=H, tries=4):
    last = None
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30).read().decode()
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{last} :: {url}")


pr = json.loads(get("https://api.github.com/repos/TencentCloud/octop-harness/pulls/197"))
print("head repo:", pr["head"]["repo"]["full_name"], "| ref:", pr["head"]["ref"], "| sha:", pr["head"]["sha"])
print("base:", pr["base"]["ref"], pr["base"]["sha"][:10], "| state:", pr["state"])
print("mergeable_state:", pr.get("mergeable_state"))
print("\n=== BODY ===")
print(pr.get("body") or "（空）")

files = json.loads(get("https://api.github.com/repos/TencentCloud/octop-harness/pulls/197/files?per_page=30"))
print("\n=== FILES ===")
for f in files:
    print(f"\n--- {f['filename']} ({f['status']} +{f['additions']}/-{f['deletions']})")
    print(f.get("patch") or "（无 patch）")

print("\n=== 测试文件全文 ===")
print(get("https://raw.githubusercontent.com/TencentCloud/octop-harness/" + pr["head"]["sha"] + "/tests/test_acp_service.py", H_RAW))
