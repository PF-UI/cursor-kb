"""Build project hub (MOC) notes from the generated AI notes.

Usage:
  python make_hubs.py --base "D:\\work\\cursor-kb"
"""
import argparse
import collections
import os
import re

ALIAS = {"": "未分类"}


def parse_fm(text):
    if not text.startswith("---"):
        return {}
    try:
        head = text.split("---")[1]
    except IndexError:
        return {}
    fm = {}
    for line in head.splitlines():
        m = re.match(r"^(\w+):\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    tags = fm.get("tags", "")
    if tags.startswith("["):
        fm["tags"] = [t.strip().strip('"\'') for t in tags.strip("[]").split(",") if t.strip()]
    else:
        fm["tags"] = []
    for k in ("raw", "project", "date"):
        fm[k] = fm.get(k, "").strip('"')
    return fm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = ap.parse_args()

    notes_dir = os.path.join(args.base, "AI对话记录")
    hubs_dir = os.path.join(args.base, "项目")
    if not os.path.isdir(notes_dir):
        ap.error(f"notes dir not found: {notes_dir}")

    notes = []
    for fn in sorted(os.listdir(notes_dir)):
        if not fn.endswith(".md"):
            continue
        fm = parse_fm(open(os.path.join(notes_dir, fn), encoding="utf-8").read())
        proj = ALIAS.get(fm.get("project", ""), fm.get("project", "") or "未分类")
        notes.append(dict(file=fn, stem=fn[:-3], date=fm.get("date", ""), project=proj,
                          tags=fm.get("tags", []), raw=fm.get("raw", "")))

    by_proj = collections.defaultdict(list)
    for n in notes:
        by_proj[n["project"]].append(n)

    os.makedirs(hubs_dir, exist_ok=True)
    for old in os.listdir(hubs_dir):
        if old.endswith(".md"):
            os.remove(os.path.join(hubs_dir, old))

    written = []
    for proj, items in sorted(by_proj.items(), key=lambda kv: -len(kv[1])):
        items.sort(key=lambda n: n["date"])
        dates = [i["date"] for i in items if i["date"]]
        tags = collections.Counter(t for i in items for t in i["tags"] if t not in ("cursor-ai", "技术笔记"))
        L = ["---", "type: project-index", f"project: {proj}",
             "tags: [cursor-ai, 项目索引]", "---", "", f"# {proj}", "",
             "> [!info] 概览",
             f"> {len(items)} 次 AI 对话" + (f" · {dates[0]} ~ {dates[-1]}" if dates else "") +
             (f" · 高频主题：{'、'.join(t for t, _ in tags.most_common(4))}" if tags else ""), "",
             "## 会话时间线", "", "| 日期 | 笔记 | 原始对话 |", "|---|---|---|"]
        for i in items:
            raw_link = f"[[{i['raw'][2:-2]}]]" if i["raw"].startswith("[[") else ""
            L.append(f"| {i['date']} | [[{i['stem']}]] | {raw_link} |")
        if tags:
            L += ["", "## 标签分布", ""]
            L += [f"- `{t}` ×{c}" for t, c in tags.most_common(12)]
        L += ["", "## 原始材料", "",
              f"全部原文见 [[_index]]（Raw/CursorChat 目录，共 {len(notes)} 条会话）。"]
        with open(os.path.join(hubs_dir, f"{proj}.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(L) + "\n")
        written.append((proj, len(items)))

    print(f"{len(notes)} notes -> {len(written)} project hubs")
    for p, c in written:
        print(f"  {c:3d}  {p}")


if __name__ == "__main__":
    main()
