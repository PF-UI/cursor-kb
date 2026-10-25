"""Verify every raw conversation has exactly one note, and that frontmatter is intact.

Usage:
  python verify.py --base "D:\\work\\cursor-kb"
"""
import argparse
import collections
import os
import re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = ap.parse_args()

    raw = os.path.join(args.base, "Raw", "CursorChat")
    notes = os.path.join(args.base, "AI对话记录")
    if not os.path.isdir(notes):
        ap.error(f"notes dir not found: {notes}")

    raw_ids = {}
    for fn in os.listdir(raw):
        if fn.endswith(".md") and not fn.startswith("_"):
            m = re.search(r"-([0-9a-f]{8})\.md$", fn)
            if m:
                raw_ids[m.group(1)] = fn

    seen = collections.Counter()
    note_of = {}
    bad = []
    for fn in os.listdir(notes):
        if not fn.endswith(".md"):
            continue
        text = open(os.path.join(notes, fn), encoding="utf-8").read()
        fm = text.split("---")[1] if text.startswith("---") else ""
        m = re.search(r'^raw:\s*"?\[\[(.+?)\]\]"?\s*$', fm, re.M)
        if not m:
            bad.append((fn, "no raw link"))
            continue
        mid = re.search(r"-([0-9a-f]{8})$", m.group(1))
        if not mid:
            bad.append((fn, f"raw link has no id: {m.group(1)}"))
            continue
        key = mid.group(1)
        seen[key] += 1
        note_of.setdefault(key, []).append(fn)
        for field in ("date", "project", "session_id", "tags"):
            if not re.search(rf"^{field}:", fm, re.M):
                bad.append((fn, f"missing {field}"))
        if "> [!summary]" not in text:
            bad.append((fn, "no summary callout"))

    missing = [i for i in raw_ids if i not in seen]
    dupes = {k: v for k, v in note_of.items() if len(v) > 1}
    extra = [k for k in seen if k not in raw_ids]

    print(f"raw conversations : {len(raw_ids)}")
    print(f"notes             : {sum(1 for f in os.listdir(notes) if f.endswith('.md'))}")
    print(f"matched ids       : {len(seen)}")
    print(f"missing           : {len(missing)} {missing[:10]}")
    print(f"duplicates        : {len(dupes)} {list(dupes.items())[:5]}")
    print(f"extra (no raw)    : {len(extra)} {extra[:10]}")
    print(f"frontmatter issues: {len(bad)}")
    for f, why in bad[:15]:
        print(f"   {f} -> {why}")
    raise SystemExit(0 if not (missing or dupes or extra) else 1)


if __name__ == "__main__":
    main()
