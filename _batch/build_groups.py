"""Build batch groups from the exported raw files.

Usage:
  python build_groups.py                 # base = parent of this script's folder
  python build_groups.py --base "D:\\work\\cursor-kb"
"""
import argparse
import json
import os
import re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="knowledge-base working dir (contains Raw/ and _batch/)")
    ap.add_argument("--cap-chars", type=int, default=150_000, help="max chars per group")
    ap.add_argument("--max-batch", type=int, default=6, help="max conversations per group")
    args = ap.parse_args()

    raw = os.path.join(args.base, "Raw", "CursorChat")
    out_dir = os.path.join(args.base, "_batch")
    if not os.path.isdir(raw):
        ap.error(f"raw dir not found: {raw}")

    items = []
    for fn in os.listdir(raw):
        if not fn.endswith(".md") or fn.startswith("_"):
            continue
        text = open(os.path.join(raw, fn), encoding="utf-8").read()
        try:
            head = text.split("---")[1]
        except IndexError:
            continue
        meta = dict(re.findall(r"^(\w+): ?(.*)$", head, re.M))
        m = re.search(r"-([0-9a-f]{8})\.md$", fn)
        items.append(dict(
            file=fn,
            id=m.group(1) if m else "",
            project=(meta.get("project") or "").strip('"'),
            date=(meta.get("created") or "").strip()[:10],
            chars=len(text),
        ))

    items.sort(key=lambda x: (x["project"], x["date"]))
    groups, cur, cur_chars = [], [], 0
    for it in items:
        if cur and (cur_chars + it["chars"] > args.cap_chars or len(cur) >= args.max_batch):
            groups.append(cur)
            cur, cur_chars = [], 0
        cur.append(it)
        cur_chars += it["chars"]
    if cur:
        groups.append(cur)

    os.makedirs(out_dir, exist_ok=True)
    for old in os.listdir(out_dir):
        if re.fullmatch(r"group_\d+\.json", old):
            os.remove(os.path.join(out_dir, old))
    for i, g in enumerate(groups, 1):
        with open(os.path.join(out_dir, f"group_{i:02d}.json"), "w", encoding="utf-8") as f:
            json.dump(g, f, ensure_ascii=False, indent=1)

    print(f"{len(items)} conversations -> {len(groups)} groups")
    for i, g in enumerate(groups, 1):
        chars = sum(x["chars"] for x in g)
        print(f"  group_{i:02d}: {len(g)} files, {chars:,} chars")


if __name__ == "__main__":
    main()
