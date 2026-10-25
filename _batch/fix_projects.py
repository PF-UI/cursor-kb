"""Normalise path-derived project names and their wikilinks.

Usage:
  python fix_projects.py --base "D:\\work\\cursor-kb"
"""
import argparse
import os
import re

MAP = {"AppData": "未分类", "Desktop": "未分类", "New": "未分类", "2.2.9_0": "浏览器扩展"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    notes_dir = os.path.join(args.base, "AI对话记录")
    if not os.path.isdir(notes_dir):
        ap.error(f"notes dir not found: {notes_dir}")

    changed = []
    for fn in sorted(os.listdir(notes_dir)):
        if not fn.endswith(".md"):
            continue
        path = os.path.join(notes_dir, fn)
        t = open(path, encoding="utf-8").read()
        parts = t.split("---", 2)
        if len(parts) < 3:
            continue
        head, body = parts[1], parts[2]
        m = re.search(r"^project:\s*(.*)$", head, re.M)
        if not m:
            continue
        old = m.group(1).strip().strip('"')
        if old not in MAP:
            continue
        new = MAP[old]
        if not args.dry_run:
            head = re.sub(r"^project:\s*.*$", f"project: {new}", head, count=1, flags=re.M)
            body = body.replace(f"[[{old}]]", f"[[{new}]]")
            open(path, "w", encoding="utf-8", newline="\n").write("---" + head + "---" + body)
        changed.append((fn, old, new))

    tag = "would rewrite" if args.dry_run else "rewrote"
    print(f"{tag} {len(changed)} notes")
    for fn, old, new in changed:
        print(f"  {old:10s} -> {new:8s}  {fn}")


if __name__ == "__main__":
    main()
