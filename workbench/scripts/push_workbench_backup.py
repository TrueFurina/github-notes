# -*- coding: utf-8 -*-
"""把 D:\\github 上的原创产物备份到 TrueFurina/github-notes 的 workbench/ 子目录。

策略：读取远端现有 tree（平铺 + 可能已有 workbench/），只新增/更新 workbench/ 下的文件，
绝不修改根目录已有的 16 个条目 —— 不覆盖任何他人内容。force:false 推送。
token 从 HKCU\\Environment 读（用户已设好）。
"""
import os, sys, json, base64, hashlib, urllib.request, urllib.error, winreg

REPO='TrueFurina/github-notes'; BR='main'
TOKEN=winreg.QueryValueEx(winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment'),'GITHUB_TOKEN')[0].strip()
API='https://api.github.com'
HDR={'Authorization':'Bearer '+TOKEN,'Accept':'application/vnd.github+json','User-Agent':'wb-backup'}

def api(url, method='GET', body=None):
    data=json.dumps(body).encode() if body is not None else None
    req=urllib.request.Request(url, data=data, headers=HDR, method=method)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        print('  ✗ API %s %s: %s %s' % (method, url.split('github.com')[-1], e.code, e.read().decode()[:200]))
        raise

def blob_sha(content_bytes):
    h=hashlib.sha1(); h.update(b'blob %d\0'%len(content_bytes)); h.update(content_bytes)
    return h.hexdigest()

# ---------- 1. 要备份的文件清单 ----------
ROOT='D:/github'
files=[]  # (archive_path, local_abs_path)

# 1a. 根目录原创 md（非 _ 临时）→ workbench/docs/
for f in sorted(os.listdir(ROOT)):
    p=os.path.join(ROOT,f)
    if os.path.isfile(p) and f.endswith('.md') and not f.startswith('_'):
        files.append(('docs/'+f, p))

# 1b. tools/ 全部 .py
for r,d,fs in os.walk(os.path.join(ROOT,'tools')):
    d[:]=[x for x in d if x not in ('__pycache__','.pytest_cache','.mypy_cache')]
    for f in fs:
        if f.endswith('.py'):
            fp=os.path.join(r,f)
            arc='tools/'+os.path.relpath(fp, os.path.join(ROOT,'tools')).replace('\\','/')
            files.append((arc, fp))

# 1c. audit-notes-fresh/ 里根目录没有的独有文件（避免覆盖，用 notes/ 前缀）
#     根目录已有的：GitHub-探索与贡献地图、GitHub优质项目洞察、README-审计总索引、
#     ROUND_LOG、ROUND_PROTOCOL、上游贡献手册、工作区地图、核验台账、隐形失效形态归纳
FRESH_SKIP={'GitHub-探索与贡献地图-2026-10-31.md','GitHub优质项目洞察-2026-10-31.md',
    'README-审计总索引.md','ROUND_LOG.md','ROUND_PROTOCOL.md','上游贡献手册.md',
    '工作区地图.md','核验台账.md','隐形失效形态归纳.md','github-workbench-2026-11-01.zip'}
fresh=os.path.join(ROOT,'audit-notes-fresh')
for f in sorted(os.listdir(fresh)):
    p=os.path.join(fresh,f)
    if os.path.isfile(p) and f not in FRESH_SKIP:
        files.append(('notes/'+f, p))

# 1d. 关键工具脚本（恢复工作流要用）→ workbench/scripts/
SCRIPTS=['push_workbench_backup.py','gh_push.py']
for s in SCRIPTS:
    sp=os.path.join(ROOT,s)
    if os.path.isfile(sp): files.append(('scripts/'+s, sp))
# audit-notes-fresh 里的推送脚本也备一份
for s in ['push-notes.py','push_workbench_backup.py']:
    sp=os.path.join(fresh,s)
    if os.path.isfile(sp) and ('notes/'+s) not in [a for a,_ in files]:
        files.append(('scripts/'+s, sp))

# 1e. probes/ 探针脚本（原创，未备份）
for r,d,fs in os.walk(os.path.join(ROOT,'probes')):
    d[:]=[x for x in d if x not in ('__pycache__','.pytest_cache')]
    for f in fs:
        if f.endswith('.py'):
            fp=os.path.join(r,f)
            arc='probes/'+os.path.relpath(fp, os.path.join(ROOT,'probes')).replace('\\','/')
            files.append((arc, fp))

# 1f. work-repo/ 原创项目（实验排课系统）→ workbench/work-repo/
WR_SKIP={'__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','node_modules','.git',
         '.venv','venv','dist','build','target','.workbuddy'}
for r,d,fs in os.walk(os.path.join(ROOT,'work-repo')):
    d[:]=[x for x in d if x not in WR_SKIP]
    for f in fs:
        if f.endswith(('.pyc','.class')): continue
        fp=os.path.join(r,f)
        arc='work-repo/'+os.path.relpath(fp, os.path.join(ROOT,'work-repo')).replace('\\','/')
        files.append((arc, fp))

# 1g. 挂机工作流原创脚本 → workbench/workflows/
WF=['round_start.py','weekly-report.ps1','upstream-scout.ps1','auto-fixer.ps1',
    'pr-watchdog.ps1','auto-rebaser.ps1']
for s in WF:
    sp=os.path.join(ROOT,s)
    if os.path.isfile(sp): files.append(('workflows/'+s, sp))

# 去重（arc 唯一）
seen=set(); unique=[]
for arc,p in files:
    if arc in seen: continue
    seen.add(arc); unique.append((arc,p))
files=unique
print('待备份 %d 个文件:' % len(files))

# ---------- 2. 读远端现有 tree ----------
head=api(f'{API}/repos/{REPO}/git/refs/heads/{BR}')['object']['sha']
commit=api(f'{API}/repos/{REPO}/git/commits/{head}')
base_tree_sha=commit['tree']['sha']
tree=api(f'{API}/repos/{REPO}/git/trees/{base_tree_sha}?recursive=1')
print('远端 HEAD %s, tree %s, 现有条目 %d' % (head[:10], base_tree_sha[:10], len(tree['tree'])))

# 分离根级条目 / workbench 下条目
root_entries=[]   # 保留原样的根级条目
wb_existing={}    # workbench/ 下已有 path -> (mode,type,sha)
for e in tree['tree']:
    if e['path']=='workbench' or e['path'].startswith('workbench/'):
        # workbench/ 整个子树由 build() 重建；这里只收集 blob 做变更检测，目录条目跳过
        if e['type']=='blob':
            wb_existing[e['path'][len('workbench/'):]] = e
        continue
    root_entries.append(e)  # 根级平铺 blob，保留

print('保留根级条目 %d 个（不动）' % len(root_entries))
print('workbench/ 下已有 %d 个（将被本地版本更新）' % len(wb_existing))

# ---------- 3. 上传新/变更 blob ----------
wb_files={}  # arc -> (mode '100644', sha)
changed=0; same=0
for arc, lp in files:
    with open(lp,'rb') as fh: data=fh.read()
    sha=blob_sha(data)
    old=wb_existing.get(arc)
    if old and old.get('sha')==sha:
        same+=1
        wb_files[arc]=('100644', sha)
    else:
        r=api(f'{API}/repos/{REPO}/git/blobs','POST',{'content':base64.b64encode(data).decode(),'encoding':'base64'})
        wb_files[arc]=('100644', r['sha'])
        changed+=1
        print('  ↑ %s (%d B) %s' % (arc, len(data), sha[:8]))

# 保留 workbench/ 下本地没有的旧文件（如其它会话推的）
for arc,e in wb_existing.items():
    if arc not in wb_files:
        wb_files[arc]=('100644', e['sha'])
        print('  · 保留 workbench/%s（本地无，远端有）' % arc)

print('workbench/ 总 %d 文件：变更/新增 %d，未变 %d' % (len(wb_files), changed, same))

# ---------- 4. 建树：扁平 -> 嵌套 ----------
class Node:
    def __init__(self): self.blobs={}; self.dirs={}
    def add(self, arc, mode, sha):
        parts=arc.split('/')
        n=self
        for p in parts[:-1]: n=n.dirs.setdefault(p, Node())
        n.blobs[parts[-1]]=(mode, sha)

root=Node()
for arc,(mode,sha) in wb_files.items():
    root.add(arc, mode, sha)

def build(node):
    entries=[]
    for name,(mode,sha) in node.blobs.items():
        entries.append({'path':name,'mode':mode,'type':'blob','sha':sha})
    for name,child in node.dirs.items():
        ctree=build(child)
        r=api(f'{API}/repos/{REPO}/git/trees','POST',{'tree':ctree})
        entries.append({'path':name,'mode':'040000','type':'tree','sha':r['sha']})
    return entries

wb_entries=build(root)
new_tree_entries=root_entries + [{'path':'workbench','mode':'040000','type':'tree','sha':'__WB__'}]
# 占位替换：先建 workbench 子树
wb_subtree=api(f'{API}/repos/{REPO}/git/trees','POST',{'tree':wb_entries})
for e in new_tree_entries:
    if e['path']=='workbench': e['sha']=wb_subtree['sha']

root_tree=api(f'{API}/repos/{REPO}/git/trees','POST',{'tree':new_tree_entries})
print('新 tree: %s (workbench 子树 %s)' % (root_tree['sha'][:10], wb_subtree['sha'][:10]))

# ---------- 5. commit + force:false 推送 ----------
msg='backup: workbench 归档（docs %d + tools %d + notes %d + scripts %d + probes %d + work-repo %d + workflows %d = %d）' % (
    sum(1 for a in wb_files if a.startswith('docs/')),
    sum(1 for a in wb_files if a.startswith('tools/')),
    sum(1 for a in wb_files if a.startswith('notes/')),
    sum(1 for a in wb_files if a.startswith('scripts/')),
    sum(1 for a in wb_files if a.startswith('probes/')),
    sum(1 for a in wb_files if a.startswith('work-repo/')),
    sum(1 for a in wb_files if a.startswith('workflows/')),
    len(wb_files))
r=api(f'{API}/repos/{REPO}/git/commits','POST',{'message':msg,'tree':root_tree['sha'],'parents':[head]})
newc=r['sha']
print('新 commit %s: %s' % (newc[:10], msg))
try:
    api(f'{API}/repos/{REPO}/git/refs/heads/{BR}','PATCH',{'sha':newc,'force':False})
    print('✓ 已推送 main -> %s' % newc[:10])
except urllib.error.HTTPError as e:
    print('✗ 推送撞上并发：%s，HEAD 仍 %s' % (e.code, head[:10])); sys.exit(1)

print('\n备份完成：%d 文件已入 github-notes/workbench/' % len(files))
