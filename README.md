# Cursor → Obsidian 迁移包

把 Cursor 的历史对话导出成 Markdown，再提炼成带双链的 Obsidian 笔记。纯 Python 标准库，无第三方依赖。

## 文件清单（7 个，约 45 KB）

```
cursor-kb/
├─ export_cursor_chats.py      # ① 导出原文（403 行）
├─ _batch/
│   ├─ TEMPLATE.md             # ② 提炼规范（给 AI 读的提示词，不是代码）
│   ├─ build_groups.py         # ③ 切分任务批次
│   ├─ verify.py               # ④ 双链闭合体检
│   ├─ fix_projects.py         # ⑤ 项目名归并
│   ├─ make_hubs.py            # ⑥ 生成项目主页
│   └─ sync_to_vault.py        # ⑦ 拷进 Vault
└─ README.md                   # 本文件
```

## 前置条件

| 项 | 要求 |
|---|---|
| Python | **3.10+**（脚本用了 `X \| None` 类型标注） |
| Cursor | 目标机器**必须装过 Cursor 且有对话记录**，否则没有数据源 |
| Obsidian | 一个已有的 Vault 目录（不存在就先用 Obsidian 建一个） |

Cursor 数据库位置（脚本自动识别，无需配置）：

- Windows `%APPDATA%\Cursor\User\globalStorage\state.vscdb`
- macOS `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`
- Linux `~/.config/Cursor/User/globalStorage/state.vscdb`

位置特殊时用 `--cursor-db "完整路径"` 覆盖。

## 五步跑完

```powershell
# 0. 把整个 cursor-kb 目录放到任意位置，例如 D:\work\cursor-kb，然后 cd 进去

# 1. 先看统计（不写文件）：确认会话数量与体量
python export_cursor_chats.py --stats

# 2. 导出原文层 → 直接写进 Vault 的 Raw 目录
python export_cursor_chats.py --out "D:\MyVault\Raw\CursorChat"

# 3. 切分任务批次（产出 _batch\group_01.json ...）
python _batch\build_groups.py

# 4. 【唯一需要 AI 的一步】把每个 group_XX.json 交给 AI，
#    让它按 _batch\TEMPLATE.md 的规范逐篇写成笔记，落到 AI对话记录\
#    —— 用 Cursor / Claude / 任意 Agent 都行，提示词就是 TEMPLATE.md 的内容

# 5. 校验 → 归并项目名 → 生成项目主页 → 同步进 Vault
python _batch\verify.py
python _batch\fix_projects.py
python _batch\make_hubs.py
python _batch\sync_to_vault.py --vault "D:\MyVault"
```

所有脚本都接受 `--base "<知识库目录>"`，默认取脚本所在目录，所以整包放到哪都能跑。

## 关键参数

| 脚本 | 参数 | 说明 |
|---|---|---|
| `export_cursor_chats.py` | `--min-chars 200` | 小于该长度的会话跳过（默认滤掉空草稿） |
| | `--clean` | 导出后删除 1 GB 临时快照 |
| | `--cursor-db` | 手动指定数据库路径 |
| `build_groups.py` | `--cap-chars 150000` | 每组字符上限 |
| | `--max-batch 6` | 每组最多几篇 |
| `fix_projects.py` | `--dry-run` | 只看会改哪些，不落盘 |
| `sync_to_vault.py` | `--vault` | Vault 根目录（也可用环境变量 `OBSIDIAN_VAULT`） |
| | `--dry-run` | 只演练不拷贝 |

## 排错

| 现象 | 原因 / 解法 |
|---|---|
| `Cursor database not found` | Cursor 没装过、或没聊过天；用 `--cursor-db` 指定 |
| 导出的对话确实很多但内容为空 | `state.vscdb` 里有大量空草稿 composer，`--min-chars` 会自动滤掉 |
| 中文乱码 | PowerShell 里先执行 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`，并设 `$env:PYTHONIOENCODING='utf-8'` |
| `verify.py` 报 missing | 某篇笔记还没写，或 `raw:` 双链里的 8 位 id 抄错了 |
| Obsidian 里双链点不开 | 文件名不能含 `[ ] | # : ? *`，本包的命名规则已规避 |

## 说明

- 第 4 步是唯一无法脚本化的环节：判断「哪些是噪音、哪句是结论、这个报错的根因」需要模型。
- 原文层与知识层分离的意义：原文可全文检索溯源，知识层只留可复用结论，图谱不被噪音污染。
