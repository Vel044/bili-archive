#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站早期失效视频 · 新浪源补档工具
用法:
  sina_archive.py vid <cid>...                     # cidinfo 反查 VID+源类型
  sina_archive.py probe <主VID> [--lo -5000] [--hi 15000] [--ext hlv] [--threads 80]
                                                    # 分段扫描: 并发探测存活分段VID
  sina_archive.py grab <VID>... -o out.flv [--threads 4]   # 并发下载+concat 合成
  sina_archive.py verify <VID>...                   # 相邻分段首尾帧连续性验证(需ffmpeg)

示例:
  sina_archive.py vid 65998
  sina_archive.py probe 42462231 --lo -500 --hi 500
  sina_archive.py grab 42462251 42462253 42462255 -o av39290.flv
"""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
BPLUS_API = "https://hd.biliplus.com/api/cidinfo?cid={}"
SINA_MAIN = "https://cdn.sinacloud.net/edge.v.iask.com/{vid}.{ext}"           # 爱问服务器(优先)
SINA_BACKUP = "https://cdn.sinacloud.net/edge.ivideo.sina.com.cn/{vid}.{ext}"  # sql服务器

def http(method, url, timeout=10, retries=1):
    """返回 (status, headers) 或 (status, None); 超时/网络错重试后返回 (-1, None)"""
    for i in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, None
        except Exception:
            if i == retries:
                return -1, None
    return -1, None


# ---------- vid: cidinfo 反查 ----------
def cmd_vid(cids):
    for cid in cids:
        status, _ = http("GET", BPLUS_API.format(cid))
        if status != 200:
            print(f"cid {cid}: 查询失败 HTTP {status}")
            continue
        try:
            with urllib.request.urlopen(
                urllib.request.Request(BPLUS_API.format(cid), headers={"User-Agent": UA}), timeout=10
            ) as r:
                data = json.load(r)["data"]
        except Exception as e:
            print(f"cid {cid}: 解析失败 {e}")
            continue
        print(f"cid={cid} aid={data.get('aid')} type={data.get('type')!r} vid={data.get('vid')!r}")
        if data.get("title"):
            print(f"     标题: {data['title']}  作者: {data.get('author','')}")
        if data.get("vid"):
            print(f"     源站: {data.get('type')}  → 下载需用 vid={data['vid']}")
        print()


# ---------- probe: 分段扫描 ----------
def probe_one(args):
    vid, ext = args
    for base in (SINA_MAIN, SINA_BACKUP):
        st, hd = http("HEAD", base.format(vid=vid, ext=ext))
        if st == 200:
            return (vid, hd.get("Content-Length", "?"))
        if st in (403, 429):  # 被限流, 换接口无意义, 直接放弃该轮
            return None
    return None

def cmd_probe(main_vid, lo, hi, ext, threads):
    rng = range(main_vid + lo, main_vid + hi + 1)
    print(f"扫描 {rng.start} ~ {rng.stop-1}（共 {len(rng)} 个）…")
    hits = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as ex:
        for i, r in enumerate(ex.map(probe_one, ((v, ext) for v in rng), chunksize=32)):
            if r:
                hits.append(r)
            if (i + 1) % 500 == 0:
                print(f"  进度 {i+1}/{len(rng)}，命中 {len(hits)}")
    hits.sort()
    print(f"\n命中 {len(hits)}/{len(rng)}:")
    print("  " + ", ".join(str(v) for v, _ in hits) if hits else "  (无命中)")

    # 聚类: 间隔<=3 视为同一视频的连续分段
    clusters = []
    cur = [hits[0]] if hits else []
    for a, b in zip(hits, hits[1:]):
        if b[0] - a[0] <= 3:
            cur.append(b)
        else:
            clusters.append(cur); cur = [b]
    if cur:
        clusters.append(cur)
    strong = [c for c in clusters if len(c) >= 2]
    print(f"\n连续簇（间隔≤3，优先检查这些，单段应≈6分钟）:")
    if not strong:
        print("  无。若目标时长明确较短，可查看单命中附近的相邻编号。")
    for c in strong:
        print(f"  {[v for v,_ in c]}  （总大小约 {sum(int(s) if str(s).isdigit() else 0 for _,s in c)/1e6:.1f} MB）")
    # 输出主VID最近的候选(供快速抽查)
    if hits:
        nearest = min(hits, key=lambda h: abs(h[0] - main_vid))
        print(f"\n距主VID {main_vid} 最近的命中: {nearest[0]}（{nearest[1]} 字节）")
    print("\n下一步: 用 grab 下载候选簇 → verify 验证连续性 → 确认内容")


# ---------- grab: 下载 + 合成 ----------
def fetch_one(args):
    vid, ext, outdir = args
    dest = os.path.join(outdir, f"{vid}.{ext}")
    for base in (SINA_MAIN, SINA_BACKUP):
        try:
            req = urllib.request.Request(base.format(vid=vid, ext=ext), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            if os.path.getsize(dest) > 0:
                return vid, dest
        except Exception:
            continue
    return vid, None

def cmd_grab(vids, ext, out, threads):
    outdir = os.path.dirname(os.path.abspath(out)) or "."
    os.makedirs(outdir, exist_ok=True)
    print(f"下载 {len(vids)} 个分段 → {outdir}/…")
    ok = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as ex:
        for vid, dest in ex.map(fetch_one, ((v, ext, outdir) for v in vids)):
            if dest:
                ok.append(dest)
                print(f"  ✓ {os.path.basename(dest)}")
            else:
                print(f"  ✗ {vid} 下载失败")
    if not ok:
        print("全部失败"); sys.exit(1)
    merge_files(ok, out)
    # 报告合成结果
    try:
        d = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", out],
            capture_output=True, text=True, timeout=60
        ).stdout.strip()
        print(f"\n合成完成: {out}（时长 {float(d)/60:.1f} 分钟）")
    except Exception:
        print(f"\n合成完成: {out}")


def merge_files(files, out):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, dir=os.path.dirname(os.path.abspath(out)) or ".") as f:
        for p in files:
            f.write(f"file '{os.path.abspath(p)}'\n")
        lst = f.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out],
            check=True, timeout=3600,
        )
    finally:
        os.unlink(lst)


# ---------- verify: 首尾帧连续性验证 ----------
def cmd_verify(vids, ext, work):
    if len(vids) < 2:
        print("至少需要 2 个分段才能比较"); sys.exit(1)
    tmpdir = tempfile.mkdtemp(prefix="sina_verify_")
    print(f"提取帧到 {tmpdir} …")
    frames = {}
    for i, vid in enumerate(vids):
        src = os.path.join(work, f"{vid}.{ext}")
        if not os.path.exists(src):
            print(f"缺少 {src}，请先 grab 下载"); sys.exit(1)
        pngs = [os.path.join(tmpdir, n) for n in
                (f"head0_{vid}.png", f"head5_{vid}.png", f"tail0_{vid}.png", f"tail5_{vid}.png")]
        for png, pos in ((pngs[0], ""), (pngs[1], "-ss 5 "),
                         (pngs[2], "-sseof -0.4 "), (pngs[3], "-sseof -5 ")):
            subprocess.run(
                f"ffmpeg -y -v error {pos}-i \"{src}\" -frames:v 1 -vf \"scale=200:-1\" \"{png}\"",
                shell=True, check=False,
            )
        frames[vid] = pngs
        print(f"  {vid} 帧已提取（首/首+5s/尾/尾-5s）")

    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        print("无 PIL/numpy，无法自动比较。请人工查看帧图：")
        for v in vids:
            print(f"  {frames[v][0]}  {frames[v][1]}")
        return
    def is_black(png):
        ima = np.asarray(Image.open(png).convert("L")).astype(float)
        return ima.mean() < 40  # 覆盖黑屏与渐黑过渡帧

    print("\n连续性（取段尾2帧×段头2帧的最小帧差, 0=完全相同, <60=连续性强, >100=不连续）:")
    for i in range(len(vids) - 1):
        a_head0, a_head5, a_tail0, a_tail5 = frames[vids[i]]
        b_head0, b_head5, b_tail0, b_tail5 = frames[vids[i + 1]]
        pairs = [(a_tail0, b_head0), (a_tail0, b_head5),
                 (a_tail5, b_head0), (a_tail5, b_head5)]
        diffs = []
        for pa, pb in pairs:
            if not (os.path.exists(pa) and os.path.exists(pb)) or is_black(pa) or is_black(pb):
                continue  # 黑帧(后黑)不参与
            ima = Image.open(pa).convert("RGB")
            imb = Image.open(pb).convert("RGB")
            if ima.size != imb.size:  # 不同视频分辨率可能不同,统一后比较
                imb = imb.resize(ima.size)
            ima = np.asarray(ima).astype(float)
            imb = np.asarray(imb).astype(float)
            diffs.append(np.abs(ima - imb).mean())
        if not diffs:
            print(f"  段{i+1}↔段{i+2}: 无可比帧（可能均为黑场）")
            continue
        diff = min(diffs)
        if diff < 40:
            verdict = "✅ 强连续(同一视频)"
        elif diff < 90:
            verdict = "⚠️ 中等差异(可能为场景切换,建议人工看图确认)"
        else:
            verdict = "❌ 差异大(大概率不同视频,建议人工确认)"
        print(f"  段{i+1}↔段{i+2}: 最小帧差 {diff:.1f}/255  {verdict}")
    print("\n注: 分段尾部常见黑屏后黑(已自动排除)；若多数对连续且时长≈6分钟，基本可确认。")
    print("    存疑对的抽帧图在本轮临时目录可人工复核；若中间疑似缺段，用 probe 沿簇两端继续探测补齐。")


# ---------- main ----------
def main():
    p = argparse.ArgumentParser(description="B站早期视频新浪源补档工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("vid", help="cidinfo 反查 VID+源类型")
    s1.add_argument("cids", type=int, nargs="+")

    s2 = sub.add_parser("probe", help="分段扫描")
    s2.add_argument("vid", type=int, help="主VID")
    s2.add_argument("--lo", type=int, default=-5000)
    s2.add_argument("--hi", type=int, default=15000)
    s2.add_argument("--ext", default="hlv", choices=["hlv", "flv"])
    s2.add_argument("--threads", type=int, default=80)

    s3 = sub.add_parser("grab", help="下载分段并合成")
    s3.add_argument("vids", type=int, nargs="+")
    s3.add_argument("-o", "--out", required=True)
    s3.add_argument("--ext", default="hlv", choices=["hlv", "flv"])
    s3.add_argument("--threads", type=int, default=4)

    s4 = sub.add_parser("verify", help="相邻分段首尾帧连续性验证")
    s4.add_argument("vids", type=int, nargs="+")
    s4.add_argument("--ext", default="hlv", choices=["hlv", "flv"])
    s4.add_argument("--dir", default=".", help="分段文件所在目录(默认当前目录)")

    a = p.parse_args()
    if a.cmd == "vid":
        cmd_vid(a.cids)
    elif a.cmd == "probe":
        cmd_probe(a.vid, a.lo, a.hi, a.ext, a.threads)
    elif a.cmd == "grab":
        cmd_grab(a.vids, a.ext, a.out, a.threads)
    elif a.cmd == "verify":
        cmd_verify(a.vids, a.ext, a.dir)

if __name__ == "__main__":
    main()
