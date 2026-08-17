# 🏛️ bili-archive · B站早期失效视频补档工具

> ⚠️ **紧急警告：新浪云将于 2026 年 9 月 16 日 24:00 永久下线，并永久删除全部数据。**
> B站 2015 年以前的视频大量使用新浪外链，这些源视频全部依赖新浪云服务器。**距今可能已不足 30 天**，一切新浪源视频都必须尽快下载保存，过期即永久消失。

B站早期（约 2009–2015）的失效视频，很多并非真正消失——数据仍存于新浪、腾讯、优酷等外链源站，只是无法直接访问。本仓库提供完整的补档流程与命令行工具：

- 🔍 **查源**：通过 CID 反查 VID 与外链源类型（已验证接口）
- 📡 **扫描**：并发探测新浪云分段视频，找出被拆分的真实分段
- 🎯 **确认**：帧差分析验证分段是否属于同一视频
- 🧩 **合成**：一键下载全部分段并合并为完整视频

本工具基于 [B站补档教程](https://www.bilibili.com/opus/1097650249106718720)（作者：ビリビリ削除動画bot）的方法实现，所有接口与 URL 均经过**实测验证**。

---

## 目录

- [背景与原理](#背景与原理)
- [快速上手（30 秒版）](#快速上手30-秒版)
- [详细教程](#详细教程)
  - [Step 1 · 获取 CID](#step-1--获取-cid)
  - [Step 2 · 反查 VID 与源类型](#step-2--反查-vid-与源类型)
  - [Step 3 · 按源类型分流](#step-3--按源类型分流)
  - [Step 4 · 下载新浪源](#step-4--下载新浪源)
  - [Step 5 · 内容确认](#step-5--内容确认)
  - [Step 6 · 合成视频](#step-6--合成视频)
- [脚本用法速查](#脚本用法速查)
- [Claude Code 用户：安装为 skill](#claude-code-用户安装为-skill)
- [常见问题](#常见问题)
- [依赖](#依赖)
- [参考与致谢](#参考与致谢)

---

## 背景与原理

早期 B 站（和隔壁站一样）是漫友用爱发电创建的站点，负担不起独立存储视频的服务器费用，所以采用**外链播放**：用一个"超链接"引用其他站点（新浪、腾讯、优酷、土豆、乐视…）的视频。存储这个引用参数的就是 **VID**（源站视频编号），它是最关键的线索。

- **CID** = 弹幕数据仓库的编号，与 av 号、VID 绑定。知道了 CID 就能反查 VID。
- 多数失效视频只是因为没有"祖父条款"或压制方式独特导致无法转码被审核打回，**数据仍存于源站服务器**，可以被重新挖出。

新浪源是早期视频最常用的外链（人称"渣浪"：视频压缩狠、审核玄学，但正因此留下的老数据也最多，存有 2007–2016 年的全部视频数据）。

## 快速上手（30 秒版）

以教程示例 av39290（吊带袜天使 第9话）为例：

```bash
# 1. 反查 CID 对应的 VID 和源类型
python3 .claude/skills/bili-archive/scripts/sina_archive.py vid 65998
# → cid=65998 aid=39290 type='sina' vid='42462231'  标题: 【10月】吊带袜天使 第9话【TD字幕组】

# 2. 主 VID 直接下载试试（404 = 分段视频，转第 3 步）
curl -sIL "https://cdn.sinacloud.net/edge.v.iask.com/42462231.hlv"

# 3. 分段扫描（约 1–20 分钟，取决于范围）
python3 .claude/skills/bili-archive/scripts/sina_archive.py probe 42462231 --lo -5000 --hi 15000

# 4. 下载候选中连续的簇并合成
python3 .claude/skills/bili-archive/scripts/sina_archive.py grab 42462251 42462253 -o 吊带袜天使_第9话.flv

# 5. 验证分段是否同一视频
python3 .claude/skills/bili-archive/scripts/sina_archive.py verify 42462251 42462253
```

## 详细教程

### Step 1 · 获取 CID

CID 是索引，有了 CID 才能反查 VID。按易用性排序：

**方法 1：BiliPlus 视频页内嵌数据**（av 号已知时最直接）

```bash
curl -sk https://www.biliplus.com/video/av39290/ | grep -o '"cid":[0-9]*'
# → "cid":65998
```

页面 HTML 直接内嵌 JSON（含 cid、vid、type、title）。注意部分视频页 vid 为空，需走 Step 2。

**方法 2：BP 主站手动查询**

打开 https://www.biliplus.com/ → 输入 av 号 → GO → 视频信息页 → Tag 下方 **"视频CID历史"**（出错时点蓝框"CID数据库"字样）。该页可看到 VID 及历次换源记录。

**方法 3：相邻 CID 推算**（约 2010-03 ~ 2012-10-17 间删除、BP 无数据的视频）

查询目标 av 号**相邻两个**视频的 CID（如 av5823 的相邻 av5822/av5824 → cid 8624/8626），夹在中间的 8625 就是目标 CID。

**方法 4：主站"稍后再看"/播放记录卡 CID**

早期删除视频可通过浏览器历史或稍后再看页面的播放请求卡出 cid（配合 [BiliPlus-Evolved 油猴插件](https://greasyfork.org/zh-CN/scripts/446841-biliplus-evolved) 更方便）。

### Step 2 · 反查 VID 与源类型

已验证接口：

```bash
curl -sk "https://hd.biliplus.com/api/cidinfo?cid=65998"
```

返回示例（实测）：

```json
{"code":0,"data":{"cid":65998,"aid":39290,"type":"sina","vid":"42462231",
 "title":"【10月】吊带袜天使 第9话【TD字幕组】","author":"投影消逝中",...}}
```

| 字段 | 含义 |
|---|---|
| `type` | 源站类型：`sina` / `qq` / `youku` / `tudou` / `letv` / `ku6` / `56` / `sohu` / `link` / 直传(空) |
| `vid` | 源站视频编号（**最重要的字段**） |
| `aid=0` | B 站记录已删但源站数据仍在——这正是能补的 |

用脚本批量反查：

```bash
python3 .claude/skills/bili-archive/scripts/sina_archive.py vid 65998 8625
```

### Step 3 · 按源类型分流

| type | 状态 | 处理 |
|---|---|---|
| `sina` | ✅ **可抢救（限时！）** | 见 [Step 4](#step-4--下载新浪源) |
| `qq` | ⚠️ 基本可用 | 链接 `https://v.qq.com/x/page/{vid}.html`。腾讯给早期视频加了审核锁，需人工点"将该视频加入审核队列"过审后才能查看下载；新番/鬼畜等敏感内容建议等风头过去 |
| `youku` | ⚠️ 需申诉 | 链接 `https://v.youku.com/v_show/id_{vid}.html`。失效视频用反馈链接 `https://m.youku.com/feedback/report?deviceType=android&playId={vid}` 申诉（原因写"视频内容正常但无法播放"），一般当天/次日恢复 |
| `tudou` | ❌ 失效 | 2023 年后数据清空，无法找回 |
| `letv` 乐视 | ❌ 失效 | 服务器数据已清除，无法找回 |
| `ku6` / 六间房 | ❌ 失效 | 原站数据清空 |
| 直传 / `link` 源 | ❌ 失效 | 无源站可扒（极少数古早直传视频数据仍存 B 站，可去主站碰运气） |

### Step 4 · 下载新浪源

**URL 模板**（均实测可用，https 优先）：

```
主接口（爱问服务器，存有 2007~2016 全部新浪视频数据，优先）：
https://cdn.sinacloud.net/edge.v.iask.com/{VID}.{flv|hlv}

备接口（硕鼠扒源时代的 sql 服务器）：
https://cdn.sinacloud.net/edge.ivideo.sina.com.cn/{VID}.{flv|hlv}
```

- 扩展名规则：**2010 年 12 月之后 → `.hlv`，之前 → `.flv`**；不确定就两个都试
- 服务器支持 Range 断点续传，`curl -r` 可用

**情况 A：直接命中（HTTP 200）**

```bash
curl -sL -o {VID}.hlv "https://cdn.sinacloud.net/edge.v.iask.com/{VID}.hlv"
```

**情况 B：NoSuchKey（404）→ 分段视频**

新浪对 ≥6 分钟的视频按 **6 分钟一段**切分存储，分段分别放入新的 VID；主 VID 只存调度信息，无法直接取原视频。需要扫描分段：

| 视频年代 | 建议扫描范围（主 VID = x） |
|---|---|
| 2009、2010 年 | `x-5000 ~ x+15000` |
| 2011、2012 年以后 | `x ~ x+10000` |
| 伪分段（时长≤6min 但存储 VID 不对） | `x-50000 ~ x+15000` |

执行（并发 HEAD 探测，±500 范围约 1 分钟，实测命中率约 8%）：

```bash
python3 .claude/skills/bili-archive/scripts/sina_archive.py probe 42462231 --lo -5000 --hi 15000
```

输出会给出命中列表，并自动**聚类出连续 VID 簇**（间隔 ≤3），优先检查这些。

### Step 5 · 内容确认

命中簇中可能有其他视频，需要确认是否属于目标。强候选特征：

1. 连续 VID 簇（间隔 ≤3）
2. 单段时长 ≈ 6 分钟（`ffprobe` 验证）
3. 各段编码参数完全一致（分辨率/帧率/编码器）

再用脚本验证画面连续性（自动排除"后黑"黑帧）：

```bash
python3 .claude/skills/bili-archive/scripts/sina_archive.py verify 42462251 42462253
# 帧差 <40 = 强连续(同一视频)；40~90 = 可能场景切换需人工看图；>90 = 大概率异视频
```

**找全分段**：确定一个簇后，沿簇两端继续 `probe` 补漏（同一视频分段通常连号，中间偶尔插入其他视频或被删的 VID）。

### Step 6 · 合成视频

```bash
python3 .claude/skills/bili-archive/scripts/sina_archive.py grab 42462251 42462253 42462255 -o 视频名.flv
```

grab 会并发下载全部分段并自动 `ffmpeg concat` 合成（分段同为 flv 容器、编码一致，`-c copy` 直拼无需转码）。分段尾部黑屏（"后黑"，早期反二压技巧）可留可裁。GUI 用户可用 [Shutter Encoder](https://www.shutterencoder.com/) 合并。

## 脚本用法速查

```bash
# 反查 VID + 源类型（支持多个 cid）
python3 .claude/skills/bili-archive/scripts/sina_archive.py vid 65998 [8625 ...]

# 分段扫描
python3 .claude/skills/bili-archive/scripts/sina_archive.py probe <主VID> \
    [--lo -5000] [--hi 15000] [--ext hlv|flv] [--threads 80]

# 下载分段并合成
python3 .claude/skills/bili-archive/scripts/sina_archive.py grab <VID>... -o 输出.flv \
    [--ext hlv|flv] [--threads 4]

# 验证相邻分段是否同一视频（需 ffmpeg；自动排除后黑帧）
python3 .claude/skills/bili-archive/scripts/sina_archive.py verify <VID>... [--dir 分段所在目录]
```

## Claude Code 用户：安装为 skill

本仓库自带 Claude Code skill（`bili-archive`）。安装后说"补档/失效视频/新浪源"即可自动调用：

```bash
# 项目级（推荐）
cp -r .claude/skills/bili-archive <你的项目>/.claude/skills/

# 用户级（所有项目可用）
mkdir -p ~/.claude/skills && cp -r .claude/skills/bili-archive ~/.claude/skills/
```

skill 会按 SKILL.md 中的流程自动执行：查 CID → 反查 VID → 分流 → 探测分段 → 确认 → 合成。

## 常见问题

**Q：新浪 CDN 链接还能用吗？**
A：可以。仓库所有接口均在 2026-08 实测（返回 Tengine/阿里云 OSS 风格响应）。但 2026-09-16 24:00 后全部永久下线。

**Q：下载的 flv 只有画面没有声音？**
A：新浪部分旧 flv 音频流为特殊变体。先确认分段下载齐全（`ffprobe` 检查流），多数情况是缺分段而非无声轨。

**Q：404 NoSuchKey 但扩展名没错？**
A：分段主 VID 或伪分段。扩大扫描范围（见 Step 4 表格）再试。

**Q：扫描区间全是别人家的视频？**
A：正常。区间内 8% 左右命中都是邻近上传的其他视频。只认"连续簇 + 内容确认"。

**Q：批量扫描太慢？**
A：`--threads` 调大（默认 80）。CDN 支持高并发，实测 60–100 线程无压力。

**Q：扫不到任何 200？**
A：该视频可能从未上传到新浪（BP 记录错误）或数据已删，及时止损，换个思路（时光机、他站转载）。

**Q：要下载弹幕怎么办？**
A：用 BP 查到的 cid 在 [bilitool.top](https://bilitool.top) 下载（含历史弹幕，需 B 站 SESSDATA）。

## 依赖

- Python 3.8+（仅标准库）
- [ffmpeg](https://ffmpeg.org/)（grab 合成、verify 抽帧；macOS: `brew install ffmpeg`）
- 可选：PIL/numpy（verify 自动帧差；无则退化为人工看图）

## 参考与致谢

- [【教程向】BILIBILI早期的失效视频都是怎么补档的？](https://www.bilibili.com/opus/1097650249106718720) — ビリビリ削除動画bot 的方法论（分段扫描范围、伪分段、各源站处理等）
- [BiliPlus](https://www.biliplus.com/) — esterTion 维护的 B 站视频信息缓存站（cidinfo 反查接口）
- [BiliPlus-Evolved](https://greasyfork.org/zh-CN/scripts/446841-biliplus-evolved) — 油猴插件（CID 反查、CID 历史增强）
- [新浪云终止服务通知](http://news.sinacloud.com/xin-lang-yun-ting-zhi-fu-wu-tong-zhi/)

> 请尊重原作者与上传者：补档视频仅限个人收藏与合理使用，勿用于商业用途，勿把老物搞下架。

## License

[MIT](LICENSE)
