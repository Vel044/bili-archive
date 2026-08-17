#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新浪源批量抢救工具 · 术力口(VOCALOID)专项
用法:
  sina_rescue.py scan --start 50000 --end 51000 [--out vocaloid_list.csv] [--gap 0.5]
                            # 页面扫描: 拿 cid+title+tag, 术力口关键词命中即记入清单(可断点续传)
  sina_rescue.py vid --in vocaloid_list.csv    # 对清单逐个 cidinfo 反查 vid+type(自动限速)
说明:
  - 页面接口(www.biliplus.com)比 cidinfo 接口(hd.biliplus.com)限流宽松得多, 实测:
    页面 0.5s 间隔稳定, cidinfo 需 5s+ 间隔
  - scan 每扫完一个 av 立即落盘, Ctrl-C 后可 --resume 继续
  - 术力口关键词: 标题或标签命中即收录(宁可多收, 下载前人工筛)
"""
import argparse
import csv
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
PAGE = "https://www.biliplus.com/video/av{}/"
CIDINFO = "https://hd.biliplus.com/api/cidinfo?cid={}"

# 宽召回关键词表（只负责把 130 万 av 缩到 2-5 万候选，宁可多收；最终判定由 AI 完成）
VOCA_SUBSTR = [
    "vocaloid", "ボカロ", "术力口", "电子歌姬", "電子歌姫", "V家", "v家",
    "初音", "ミク", "miku", "hatsune", "葱娘",
    "镜音", "鏡音", "kagamine", "リン", "レン",
    "巡音", "ルカ", "megurine", "流歌",
    "gumi", "ぐみ", "グミ", "megpoid",
    "kaito", "カイト", "冰音", "meiko", "メイコ",
    "vflower", "イア", "結月", "结月", "ゆかり", "flower", "フラワー",
    "洛天依", "乐正绫", "乐正龙牙", "言和", "心华", "星尘", "徵羽摩柯", "墨清弦", "阿绫",
    "世界第一的公主", "世末舞厅", "千本桜", "千本樱", "深海少女", "深海シティ",
    "炉心融解", "悪ノ", "恶之", "メルト", "被发现的", "from y to y", "y to y",
    "右肩の蝶", "悪ノ娘", "悪ノ召使", "ココロ", "からくり", "初音ミクの消失",
    "裏表ラバーズ", "ローリンガール", "rolling girl", "ぽっぴっぽー", "メランコリック",
    "六兆年と一夜物語", "六兆年", "东京泰迪熊", "东京テディベア", "脳漿炸裂ガール",
    "スイートマジック", "トゥインクル", "キミボシ", "マトリョシカ", "俄罗斯套娃",
    "ハロ", "天ノ弱", "天ノ弱", "ジッタードール", "ドーナツホール", "from y to y",
    "メグメグ", "モザイクロール", "ODDS&ENDS", "カゲロウ", "阳炎", "Lost One",
    "インビジブル", "アンハッピーリフレイン", "心拍数", "心拍数#0822",
    "独りんぼエンヴィー", "虎视眈眈", "虎視眈眈", "威風堂々", "威风堂堂",
    "千本桜", "黑化", "ダンスロボットダンス", "はやくそれになりたい",
    "エイリアンエイリアン", "アスノヨゾラ哨戒班", "哨戒班", "フィクサー",
    "彗星ハネムーン", "彗星蜜月", "v flower", "ヴェノマニア公の狂気",
]
# 英文短词整词匹配（\b...\b），避免子串误伤
VOCA_WORD = ["miku", "mik", "luka", "gumi", "kaito", "meiko", "flower", "melt",
             "len", "rin", "ia", "vocaloid", "hatsune", "kagamine",
             "megurine", "megpoid", "vflower", "megurine"]

def get(url, timeout=10):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")

def page_av(av):
    """返回 dict(av,cid,title,tag) 或 None(无记录)"""
    t = get(PAGE.format(av))
    m = re.search(r'"list":\[\{"page":1,"type":"vupload","cid":(\d+),', t)
    if not m:
        return None
    tm = re.search(r'"title":"([^"]*)"', t)
    tg = re.search(r'"tag":"([^"]*)"', t)
    return {
        "av": av,
        "cid": int(m.group(1)),
        "title": tm.group(1) if tm else "",
        "tag": tg.group(1) if tg else "",
    }

def is_voca_recall(item):
    """宽召回: 标题或标签命中即收录(召回率优先, 准确率交给 AI 精筛)"""
    hay = item["title"] + " " + item["tag"]
    hay_l = hay.lower()
    for k in VOCA_SUBSTR:
        if k in hay or k.lower() in hay_l:
            return True
    for w in VOCA_WORD:
        if re.search(r"\b" + re.escape(w) + r"\b", hay_l):
            return True
    return False

def cmd_scan(args):
    out = args.out
    fresh = not (args.resume and os.path.exists(out))
    header = ["av", "cid", "title", "tag"]
    scanned_file = out + ".progress"
    done = set()
    if args.resume and os.path.exists(scanned_file):
        with open(scanned_file) as f:
            done = set(int(x) for x in f.read().split())
    if fresh:
        with open(out, "w", newline="") as f:
            csv.writer(f).writerow(header)

    n_hit = 0
    n_503 = 0
    for av in range(args.start, args.end + 1):
        if av in done:
            continue
        try:
            item = page_av(av)
            if item and is_voca_recall(item):
                with open(out, "a", newline="") as f:
                    csv.writer(f).writerow([item["av"], item["cid"], item["title"], item["tag"]])
                n_hit += 1
                print(f"  ✚ av{av} cid={item['cid']} {item['title'][:50]}", flush=True)
        except urllib.error.HTTPError as e:
            if e.code == 503:
                n_503 += 1
                if n_503 >= 3:
                    print(f"  连续限流, 深度退避 60s…", flush=True)
                    time.sleep(60)
                    n_503 = 0
                else:
                    time.sleep(15)
            else:
                time.sleep(2)
        except Exception:
            time.sleep(2)
        with open(scanned_file, "a") as f:
            f.write(f"{av}\n")
        time.sleep(args.gap)
        if (av - args.start + 1) % 200 == 0:
            print(f"  进度 av{av} 命中 {n_hit} (503累计 {n_503})", flush=True)
    print(f"完成: av{args.start}~{args.end} 命中 {n_hit} 条 → {out}")

def cmd_vid(args):
    with open(args.infile, newline="") as f:
        rows = list(csv.DictReader(f))
    out = args.infile + ".vid.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["av", "cid", "title", "tag", "type", "vid"])
    for i, r in enumerate(rows):
        try:
            data = json_loads(get(CIDINFO.format(r["cid"])))
            typ = (data.get("data") or {}).get("type", "")
            vid = (data.get("data") or {}).get("vid", "")
            w.writerow([r["av"], r["cid"], r["title"], r["tag"], typ, vid])
            print(f"  av{r['av']} type={typ} vid={vid}")
        except Exception as e:
            w.writerow([r["av"], r["cid"], r["title"], r["tag"], "ERR", str(e)[:20]])
            print(f"  av{r['av']} 反查失败")
        time.sleep(6)  # cidinfo 限流严, 6s 间隔
        if (i + 1) % 20 == 0:
            print(f"  进度 {i+1}/{len(rows)}")
    print(f"完成 → {out}")

def json_loads(t):
    import json
    return json.loads(t)

def main():
    p = argparse.ArgumentParser(description="新浪源批量抢救 · 术力口专项")
    sub = p.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("scan")
    s1.add_argument("--start", type=int, required=True)
    s1.add_argument("--end", type=int, required=True)
    s1.add_argument("--out", default="vocaloid_list.csv")
    s1.add_argument("--gap", type=float, default=2.0, help="请求间隔秒数(默认2.0, 实测2.0s零503)")
    s1.add_argument("--resume", action="store_true", help="断点续传")
    s2 = sub.add_parser("vid")
    s2.add_argument("--in", dest="infile", required=True)
    a = p.parse_args()
    if a.cmd == "scan":
        cmd_scan(a)
    elif a.cmd == "vid":
        cmd_vid(a)

if __name__ == "__main__":
    main()
