---
name: bili-archive
description: B站早期失效视频补档（重点：新浪云源抢救）。当用户提到"补档""失效视频""已删除视频""新浪源""BiliPlus""VID/CID""外链源""老视频找回""新浪云下线"等时使用。⚠️ 新浪云将于 2026-09-16 24:00 永久下线并删除全部数据，所有新浪源视频必须在截止前抢救！
---

# B站早期失效视频补档（新浪源抢救）

## ⚠️ 紧急背景（必读）

**新浪云 2026-09-16 24:00 永久下线**，下线后永久删除全部数据。B站早期（2015年前）视频大量使用新浪外链（`cdn.sinacloud.net/edge.v.iask.com/` 等），这些源视频**全部依赖新浪云服务器存活**。今天距下线可能已不足 30 天，一切 `type=sina` 的视频都应立即下载保存，且无法保证恢复。

技术背景：早期B站用外链播放（引用其他站点视频），存储引用参数的即 **VID**；CID 是弹幕数据仓库，与 av号、VID 绑定。多数失效视频仅因无"祖父条款"或压制方式独特无法转码，数据仍存于源站，可被挖出。

## 工作流程总览

```
获取 CID → 反查 VID+源类型 → 按源类型处理（新浪是主战场） → 下载（直下或扫分段） → 确认内容 → 合成
```

## Step 1：获取 CID

CID 是核心索引，有了 CID 才能反查 VID。获取方式（按易用性排序）：

1. **BiliPlus 视频页内嵌数据**（av号已知时最直接）：
   ```
   curl -sk https://www.biliplus.com/video/av{AV号}/ | grep -o '"cid":[0-9]*' 
   ```
   页面 HTML 内嵌 JSON，含 `cid`、`vid`、`type`、`title`（已验证，如 av39290 → cid=65998）。注意部分视频页 `vid` 为空，需走 Step 2。

2. **BP 主站手动查询**：打开 https://www.biliplus.com/ → 输入 av 号 → GO → 视频信息页 → Tag 下方"视频CID历史"（出错时点"CID数据库"）。CID 历史页可看到 VID 及各期源记录。

3. **相邻 CID 推算**（约 2010-03 ~ 2012-10-17 间删除、BP 无数据的视频）：查询相邻 av 号的 CID（如 av5823 的相邻 av5822/av5824 → cid 8624/8626），夹在中间的 8625 就是目标 CID。

4. **主站"稍后再看"/播放记录卡 CID**：早期删除视频可通过浏览器历史或稍后再看页面的播放请求卡出 cid（配合 BiliPlus-Evolved 油猴插件更方便，脚本：https://delflare505.win/scripts/446841/Biliplus%20Evolved.user.js）。

## Step 2：反查 VID 与源类型（已验证接口）

```
curl -sk "https://hd.biliplus.com/api/cidinfo?cid={CID}"
```
返回示例（实测）：
```json
{"code":0,"data":{"cid":65998,"aid":39290,"type":"sina","vid":"42462231","title":"【10月】吊带袜天使 第9话【TD字幕组】","author":"投影消逝中",...}}
```
- `type` = 源站类型（sina / qq / youku / tudou / letv / ku6 / 56 / sohu / link / 直传空值）
- `vid` = 源站视频编号（最重要字段！）
- `aid=0` = B站记录已删但源站数据仍在，**这正是能补的**

批量反查多个 CID 时逐条 curl 即可（接口无速率限制迹象）。

## Step 3：按源类型分流

| type | 状态 | 处理 |
|---|---|---|
| `sina` | ✅ 可抢救（限时！） | 走 Step 4 新浪源下载流程 |
| `qq` | ⚠️ 基本可用 | `https://v.qq.com/x/page/{vid}.html`，腾讯给早期视频加了审核锁，需人工点"加入审核队列"过审后才能下载；新番/番剧鬼畜等敏感内容建议等风头过去 |
| `youku` | ⚠️ 需申诉 | `https://v.youku.com/v_show/id_{vid}.html`，失效视频用反馈链接 `https://m.youku.com/feedback/report?deviceType=android&playId={vid}` 申诉（原因写"视频内容正常但无法播放"），一般当天/次日恢复 |
| `tudou` | ❌ 失效 | 2023年后数据清空，无法找回 |
| `letv`（乐视） | ❌ 失效 | 服务器数据已清除，无法找回 |
| `ku6` / 六间房 | ❌ 失效 | 原站数据清空 |
| 直传 / `link` 源 | ❌ 失效 | 无源站可扒（直传源仅极少数古早视频数据仍在 B 站，可试试主站） |

## Step 4：新浪源下载

### URL 模板（已验证可用，https 优先）

```
主接口（爱问服务器，存有 2007~2016 全部新浪视频数据，优先用）：
https://cdn.sinacloud.net/edge.v.iask.com/{VID}.{flv|hlv}
备接口（硕鼠扒源时代的 sql 服务器）：
https://cdn.sinacloud.net/edge.ivideo.sina.com.cn/{VID}.{flv|hlv}
```
扩展名规则：**2010年12月之后 → `.hlv`，之前 → `.flv`**；不确定就两个都试（404 无妨）。服务器支持 Range 断点续传，`curl -r` 可用。

### 情况 A：直接命中（200）
```
curl -sL -o {VID}.hlv "https://cdn.sinacloud.net/edge.v.iask.com/{VID}.hlv"
```
下载后 `ffprobe` 检查时长/编码。

### 情况 B：NoSuchKey（404）→ 分段视频
主 VID 无法直接取原视频，需扫描其分段 VID（新浪对 ≥6min 视频按 6 分钟一段切分，分段存入新 VID；主 VID 只存调度信息）。

**扫描范围**（主 VID 记为 x）：
- 2009、2010 年视频：`x-5000 ~ x+15000`
- 2011、2012 年以后：`x ~ x+10000`
- 伪分段视频（时长≤6min 但实际存储 VID 不对，如 av43001）：`x-50000 ~ x+15000`

**执行**：用本 skill 脚本 `sina_archive.py probe`（并发 HEAD 探测，±500 范围约 1 分钟，实测命中率约 8%）。勿用 IDM 批量任务（易出"有文件但加载不出"的问题）。

### 分段识别（关键技巧）
命中列表中找**连续 VID 簇**（间隔 ≤3，如 42462251/253/255 隔2连排）。强候选特征：
1. 连续簇
2. 单段时长 ≈ 6 分钟（`ffprobe` 验证，实测 357.76s / 359.23s / 366.44s）
3. 各段编码参数完全一致（分辨率/帧率/编码器）

**内容确认**：下载候选分段 → `sina_archive.py verify` 比较相邻段首尾帧画面连续性（取段尾2帧×段头2帧的最小帧差；黑帧"后黑"自动排除）。帧差 <40 强连续、40~90 中等差异（可能场景切换，需人工看图）、>90 大概率异视频。也可以抽帧让用户人工看图确认。

**找全分段**：确定一个簇后，沿簇两端继续探测 ±30 补齐（同一视频分段通常连号，中间偶尔插入其他视频）。

## Step 5：合成

```
sina_archive.py grab {VID1} {VID2} ... -o merged.flv   # 并发下载+concat合成
```
等价手工命令：
```
ffmpeg -f concat -safe 0 -i concat_list.txt -c copy merged.flv
```
注：concat 直接拼接即可（分段同为 flv 容器、编码一致，无需转码）。分段尾部黑屏可留可裁。GUI 用户可用 Shutter Encoder（https://www.shutterencoder.com/）合并。

## 常见问题

- **"下载的只有画面没声音"**：新浪部分旧 flv 音频流为 mp3/speex 变体，ffprobe 确认流存在性；大多数是分段未下全或该源本身无声轨。
- **404 NoSuchKey 但扩展名没错**：分段主 VID 或伪分段，扩大扫描范围再试。
- **扫不出任何 200**：该视频可能从未上传到新浪（BP 记录错误）或数据已删，及时止损。
- **搜索结果混淆**：扫描区间内命中大量他人视频（正常，命中率 8% 左右），只认连续簇+内容确认。
- **需要下载弹幕**：用 BP 查到的 cid 在 bilitool.top 下载（含历史弹幕，需 SESSDATA）。

## 输出约定

- `grab` 会把分段文件下载到 `-o` 输出文件所在目录（分段命名 `{VID}.{ext}`），`verify` 用 `--dir` 指定该目录
- 命名建议：`{标题或av号}_{VID}.flv`，保留 BP 返回的 title 做参考
- 下载完成后汇报：源类型、VID、分段数、总时长、是否已确认内容、保存路径
