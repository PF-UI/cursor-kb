"""Copy the two-layer knowledge base into the Obsidian vault and write the root index.

Usage:
  python sync_to_vault.py --vault "D:\\MyQa\\本地电脑"
  python sync_to_vault.py --vault ... --base "D:\\work\\cursor-kb"
"""
import argparse
import datetime as dt
import os
import shutil

PAIR_SUBDIRS = [
    (os.path.join("Raw", "CursorChat"), os.path.join("Raw", "CursorChat")),
    ("AI对话记录", "AI对话记录"),
    ("项目", "项目"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT", ""),
                    help="Obsidian vault root (or set OBSIDIAN_VAULT)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.vault:
        ap.error("--vault is required (or set OBSIDIAN_VAULT)")
    if not os.path.isdir(args.vault):
        ap.error(f"vault not found: {args.vault}")

    stats = []
    for src_sub, dst_sub in PAIR_SUBDIRS:
        src = os.path.join(args.base, src_sub)
        dst = os.path.join(args.vault, dst_sub)
        n = 0
        if os.path.isdir(src):
            if not args.dry_run:
                os.makedirs(dst, exist_ok=True)
            for fn in os.listdir(src):
                if not fn.endswith(".md"):
                    continue
                if not args.dry_run:
                    shutil.copy2(os.path.join(src, fn), os.path.join(dst, fn))
                n += 1
        stats.append((dst_sub, n))

    raw = next(n for s, n in stats if s.endswith("CursorChat"))
    notes = next(n for s, n in stats if s.endswith("AI对话记录"))
    hubs = next(n for s, n in stats if s.endswith("项目"))
    hub_dir = os.path.join(args.vault, "项目")
    hub_names = sorted(fn[:-3] for fn in os.listdir(hub_dir) if fn.endswith(".md")) if os.path.isdir(hub_dir) else []

    L = ["---", "type: index", "tags: [cursor-ai, 导航]", "---", "",
         "# Cursor 对话知识库", "",
         "> [!info] 这是什么",
         f"> 把 Cursor 里 {max(raw - 1, 0)} 段历史对话沉淀成两层：**Raw 原文层**（完整对话，仅溯源）+ **知识层**（AI 提炼笔记，带双链）。",
         f"> 最近同步：{dt.datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
         "## 两层结构", "",
         "| 层 | 目录 | 用途 | 文件数 |", "|---|---|---|---|",
         f"| 原文层 | `Raw/CursorChat/` | 完整对话、工具调用轨迹，只做溯源，不常读 | {raw} |",
         f"| 知识层 | `AI对话记录/` | 一句话主题 + 核心结论 + 踩坑 + 待办 | {notes} |",
         f"| 导航层 | `项目/` | 每个项目一条时间线，汇总该项目所有对话 | {hubs} |", "",
         "## 项目导航", ""]
    L += [f"- [[{h}]]" for h in hub_names]
    L += ["", "## 怎么用", "",
          "- 找某次对话的结论：`Ctrl+O` 搜知识点，或从 [[_index]] 按日期进原文。",
          "- 想复用某段排错经验：先看知识层的 `⚠️ 踩坑`，需要细节再点 `原始对话` 回原文。",
          "- 新对话想纳入：把新导出的 md 放 `Raw/CursorChat/`，再按同样模板提炼一篇。", "",
          "## 维护脚本", "",
          f"- 导出：`{os.path.join(args.base, 'export_cursor_chats.py')}`（读 Cursor 本地 SQLite）",
          f"- 同步：`{os.path.join(args.base, '_batch', 'sync_to_vault.py')}`（Raw + 笔记 + 项目页一键拷入 Vault）"]

    if not args.dry_run:
        with open(os.path.join(args.vault, "Cursor 对话知识库.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(L) + "\n")

    prefix = "[dry-run] " if args.dry_run else ""
    print(f"{prefix}synced: raw={raw} notes={notes} hubs={hubs}")
    print(f"{prefix}index: {os.path.join(args.vault, 'Cursor 对话知识库.md')}")


if __name__ == "__main__":
    main()
