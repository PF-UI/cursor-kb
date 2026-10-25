r"""
Cursor -> Obsidian raw exporter.

Reads the Cursor global chat database (state.vscdb) and writes one Markdown file
per conversation. Raw archive only: full transcript, no AI summarisation.

Usage:
  python export_cursor_chats.py --stats
  python export_cursor_chats.py --out "D:\MyQa\本地电脑\Raw\CursorChat"
  python export_cursor_chats.py --out ... --cursor-db "/path/to/state.vscdb"
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile


def cursor_user_dir() -> str:
    """Cursor's per-user config dir, per platform (overridable with --cursor-db)."""
    if sys.platform == "win32":
        root = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
    elif sys.platform == "darwin":
        root = os.path.expanduser("~/Library/Application Support")
    else:
        root = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(root, "Cursor", "User")


_USER_DIR = cursor_user_dir()
CURSOR_DB = os.path.join(_USER_DIR, "globalStorage", "state.vscdb")
WS_ROOT = os.path.join(_USER_DIR, "workspaceStorage")
WORKSPACES_ROOT = os.path.join(_USER_DIR, "Workspaces")

TYPE_USER, TYPE_ASSISTANT = 1, 2


def snapshot_db(reuse: bool = True) -> str:
    """Copy the live DB (+wal/-shm) next to this script so we never touch the running app."""
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_snapshot")
    os.makedirs(tmp, exist_ok=True)
    cached = os.path.join(tmp, "state.vscdb")
    if reuse and os.path.exists(cached) and os.path.getmtime(cached) >= os.path.getmtime(CURSOR_DB) - 1:
        return cached
    shutil.copy2(CURSOR_DB, cached)
    for side in ("state.vscdb-wal", "state.vscdb-shm"):
        src = CURSOR_DB[: -len("state.vscdb")] + side
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(tmp, side))
    return cached


def uri_to_path(uri: str) -> str:
    """file:///d%3A/MyBlog -> D:\\MyBlog"""
    from urllib.parse import unquote
    if not uri:
        return ""
    u = unquote(uri)
    u = re.sub(r"^file:///", "", u)
    if re.match(r"^[a-zA-Z]/", u):
        u = u[0].upper() + ":\\" + u[2:].replace("/", "\\")
    return u


def project_name(uri: str) -> str:
    p = uri_to_path(uri)
    if not p:
        return ""
    return os.path.basename(p.rstrip("\\")) or p


def load_workspace_map() -> dict:
    """workspaceId -> project root uri"""
    out = {}
    if not os.path.isdir(WS_ROOT):
        return out
    for d in os.listdir(WS_ROOT):
        wj = os.path.join(WS_ROOT, d, "workspace.json")
        if not os.path.isfile(wj):
            continue
        try:
            data = json.load(open(wj, encoding="utf-8"))
        except Exception:
            continue
        out[d] = data.get("folder") or data.get("workspace") or ""
    return out


def load_ws_file_map() -> dict:
    """Cursor/Workspaces/<id>/workspace.json -> list of folders"""
    out = {}
    if not os.path.isdir(WORKSPACES_ROOT):
        return out
    for d in os.listdir(WORKSPACES_ROOT):
        wj = os.path.join(WORKSPACES_ROOT, d, "workspace.json")
        if not os.path.isfile(wj):
            continue
        try:
            data = json.load(open(wj, encoding="utf-8"))
        except Exception:
            continue
        folders = []
        if isinstance(data.get("workspace"), dict):
            folders = data["workspace"].get("folders") or []
        elif isinstance(data.get("folders"), list):
            folders = data["folders"]
        out[d] = [f.get("uri") or f.get("path") or "" for f in folders if isinstance(f, dict)]
    return out


def resolve_project(wid: str, ws_map: dict, ws_file_map: dict) -> str:
    if not wid:
        return ""
    if wid in ws_map and ws_map[wid]:
        return project_name(ws_map[wid])
    if wid in ws_file_map and ws_file_map[wid]:
        names = [project_name(u) for u in ws_file_map[wid] if u]
        return "+".join([n for n in names if n]) or ""
    return ""


def project_for(cd: dict, wid: str, ws_map: dict, ws_file_map: dict) -> str:
    """Best-effort project name: workspace folder -> tracked git repos -> touched files."""
    p = resolve_project(wid, ws_map, ws_file_map)
    if p and not p.lower().endswith("workspace.json"):
        return p
    repos = []
    for r in cd.get("trackedGitRepos") or []:
        base = os.path.basename(str(r.get("repoPath") or "").rstrip("\\/"))
        if base and base not in repos:
            repos.append(base)
    if repos:
        return "+".join(repos)
    counts = {}
    for uri in list((cd.get("originalFileStates") or {}).keys())[:60]:
        path = uri_to_path(uri) if str(uri).startswith("file:") else str(uri)
        parts = [x for x in re.split(r"[/\\]+", path) if x]
        if len(parts) >= 2 and re.match(r"^[A-Za-z]:$", parts[0]):
            seg = parts[1]
            if seg.lower() in ("users", "documents", "desktop") and len(parts) >= 4:
                seg = parts[3]
            counts[seg] = counts.get(seg, 0) + 1
    if counts:
        return max(counts.items(), key=lambda kv: kv[1])[0]
    return ""


def to_local(ts) -> dt.datetime | None:
    if not ts:
        return None
    try:
        return dt.datetime.fromtimestamp(float(ts) / 1000.0)
    except Exception:
        return None


def parse_iso(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone()
    except Exception:
        return None


def clean_text(t: str) -> str:
    if not t:
        return ""
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{4,}", "\n\n\n", t)
    return t.strip()


def tool_line(tfd: dict) -> str:
    name = tfd.get("name") or f"tool{tfd.get('tool')}"
    status = tfd.get("status") or ""
    try:
        params = json.loads(tfd.get("params") or "{}")
    except Exception:
        params = {}
    desc = ""
    for k in ("path", "relativeWorkspacePath", "file_path", "target_file", "pattern", "query", "command", "description", "globPattern"):
        if isinstance(params, dict) and params.get(k):
            v = str(params[k]).replace("\n", " ")
            desc = f"{k}={v[:120]}"
            break
    bits = [b for b in (name, desc, status) if b]
    return "`" + " · ".join(bits) + "`"


def extract(db_path: str, max_chars_per_msg: int = 0):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur, cur2 = con.cursor(), con.cursor()
    ws_map, ws_file_map = load_workspace_map(), load_ws_file_map()

    headers = []
    for cid, wid, created, updated, archived, issub, value in cur.execute(
            "select composerId, workspaceId, createdAt, lastUpdatedAt, isArchived, isSubagent, value from composerHeaders"):
        head = {}
        try:
            head = json.loads(value) if value else {}
        except Exception:
            pass
        headers.append(dict(composerId=cid, workspaceId=str(wid or ""), createdAt=created,
                            lastUpdatedAt=updated or head.get("lastUpdatedAt"),
                            archived=archived, isSubagent=issub, head=head))

    # bubble ids ordered per composer (+ the composerData blob, reused for project hints)
    order, cdata = {}, {}
    for h in headers:
        cid = h["composerId"]
        row = cur2.execute("select value from cursorDiskKV where key=?", (f"composerData:{cid}",)).fetchone()
        seq = []
        cd = {}
        if row and row[0]:
            try:
                cd = json.loads(row[0])
                for bh in cd.get("fullConversationHeadersOnly") or []:
                    if bh.get("bubbleId"):
                        seq.append(bh["bubbleId"])
            except Exception:
                pass
        order[cid] = seq
        cdata[cid] = cd

    convos = []
    for h in headers:
        cid = h["composerId"]
        seq = order.get(cid) or []
        bubbles = []
        if seq:
            qmarks = ",".join("?" * len(seq))
            rows = {r[0]: r[1] for r in cur2.execute(
                f"select key, value from cursorDiskKV where key in ({qmarks})",
                [f"bubbleId:{cid}:{b}" for b in seq])}
            for b in seq:
                v = rows.get(f"bubbleId:{cid}:{b}")
                if v:
                    bubbles.append(v)
        else:
            for (v,) in cur2.execute("select value from cursorDiskKV where key like ? order by key",
                                     (f"bubbleId:{cid}:%",)):
                bubbles.append(v)

        msgs, tool_calls = [], 0
        for raw in bubbles:
            try:
                b = json.loads(raw)
            except Exception:
                continue
            btype = b.get("type")
            text = clean_text(b.get("text") or "")
            tfd = b.get("toolFormerData") or {}
            if btype == TYPE_USER:
                if not text and b.get("richText"):
                    text = ""
                if text:
                    msgs.append(("user", text, None))
            elif btype == TYPE_ASSISTANT:
                if isinstance(tfd, dict) and tfd.get("name"):
                    tool_calls += 1
                if text:
                    msgs.append(("assistant", text, tool_line(tfd) if tfd.get("name") else None))
                elif tfd.get("name"):
                    msgs.append(("tool", "", tool_line(tfd)))
        msgs = [m for m in msgs if m[1].strip() or m[0] == "tool"]

        chars = sum(len(m[1]) for m in msgs)
        chars_user = sum(len(m[1]) for m in msgs if m[0] == "user")
        chars_asst = sum(len(m[1]) for m in msgs if m[0] == "assistant")
        convos.append(dict(
            id=cid, head=h["head"], createdAt=h["createdAt"], updatedAt=h["lastUpdatedAt"],
            archived=h["archived"], isSubagent=h["isSubagent"],
            project=project_for(cdata.get(cid) or {}, h["workspaceId"], ws_map, ws_file_map),
            workspaceId=h["workspaceId"], msgs=msgs, tool_calls=tool_calls,
            chars=chars, chars_user=chars_user, chars_asst=chars_asst,
        ))
    return convos


def sanitize(name: str, limit: int = 60) -> str:
    name = re.sub(r'[\\/:*?"<>|#\[\]\n\r\t]+', " ", name or "")
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    return name[:limit].rstrip() or "untitled"


def fmt_ts(t) -> str:
    return t.strftime("%Y-%m-%d %H:%M") if t else ""


def render_md(c: dict) -> str:
    start = to_local(c["createdAt"]) or parse_iso(c["head"].get("createdAt"))
    end = to_local(c["updatedAt"])
    title = c["head"].get("name") or (c["msgs"][0][1][:40] if c["msgs"] else "untitled")
    project = c["project"]
    L = []
    L.append("---")
    L.append(f"source: cursor-chat")
    L.append(f"session_id: {c['id']}")
    L.append(f"title: \"{title.replace(chr(34), chr(39))}\"")
    L.append(f"project: \"{project}\"")
    L.append(f"created: {start.isoformat(timespec='seconds') if start else ''}")
    L.append(f"updated: {end.isoformat(timespec='seconds') if end else ''}")
    L.append(f"mode: {c['head'].get('unifiedMode') or ''}")
    L.append(f"model: {(c['head'].get('modelConfig') or {}).get('modelName') or ''}")
    L.append(f"messages: {sum(1 for m in c['msgs'] if m[0] != 'tool')}")
    L.append(f"tool_calls: {c['tool_calls']}")
    L.append("tags: [cursor-raw]")
    L.append("---")
    L.append("")
    L.append(f"# {title}")
    L.append("")
    meta = []
    if project:
        meta.append(f"**项目**：{project}")
    if start:
        meta.append(f"**时间**：{fmt_ts(start)} → {fmt_ts(end) if end else ''}")
    if c["head"].get("subtitle"):
        meta.append(f"**摘要**：{c['head']['subtitle']}")
    if meta:
        L.append(" · ".join(meta))
        L.append("")
    todos = c["head"].get("todos") or []
    if todos:
        L.append("## 任务清单")
        L.append("")
        for t in todos:
            mark = "x" if t.get("status") == "completed" else " "
            L.append(f"- [{mark}] {t.get('content') or ''}")
        L.append("")

    L.append("---")
    L.append("")
    for role, text, tool in c["msgs"]:
        if role == "user":
            L.append("### 👤 User")
            L.append("")
            L.append(text)
            L.append("")
        elif role == "assistant":
            if tool:
                L.append(f"> 🛠 {tool}")
                L.append("")
            L.append("### 🤖 Assistant")
            L.append("")
            L.append(text)
            L.append("")
        elif role == "tool":
            L.append(f"> 🛠 {tool}")
            L.append("")
    return "\n".join(L).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="output directory for raw md files")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--min-chars", type=int, default=200, help="skip conversations shorter than this")
    ap.add_argument("--clean", action="store_true", help="delete the db snapshot afterwards")
    ap.add_argument("--cursor-db", help="explicit path to state.vscdb (auto-detected per platform by default)")
    args = ap.parse_args()

    global CURSOR_DB
    if args.cursor_db:
        CURSOR_DB = args.cursor_db
    if not os.path.exists(CURSOR_DB):
        ap.error(f"Cursor database not found: {CURSOR_DB}\n"
                 f"  -> check that Cursor is installed and has chat history, or pass --cursor-db")

    db = snapshot_db()
    print(f"snapshot: {db}", file=sys.stderr)
    convos = extract(db)
    main_c = [c for c in convos if not c["isSubagent"]]
    usable = [c for c in main_c if c["chars"] >= args.min_chars]
    usable.sort(key=lambda c: c["createdAt"] or 0)

    if args.stats:
        print(f"composers total      : {len(convos)}")
        print(f"non-subagent         : {len(main_c)}")
        print(f"usable (>={args.min_chars} chars): {len(usable)}")
        print(f"skipped (empty/thin) : {len(main_c) - len(usable)}")
        print(f"total chars          : {sum(c['chars'] for c in usable):,}")
        print(f"  user               : {sum(c['chars_user'] for c in usable):,}")
        print(f"  assistant          : {sum(c['chars_asst'] for c in usable):,}")
        print(f"tool calls           : {sum(c['tool_calls'] for c in usable):,}")
        print("\nper conversation:")
        for c in usable:
            t = to_local(c["createdAt"])
            print(f"  {t.strftime('%Y-%m-%d') if t else '?'}  {c['chars']:>7,}c  "
                  f"{len(c['msgs']):>5}m  {c['project'][:28]:<28}  {sanitize(c['head'].get('name') or '')[:40]}")
        return

    if not args.out:
        ap.error("--out is required unless --stats")
    os.makedirs(args.out, exist_ok=True)
    index = []
    for c in usable:
        t = to_local(c["createdAt"])
        title = sanitize(c["head"].get("name") or "untitled")
        fname = f"{t.strftime('%Y-%m-%d') if t else '0000-00-00'} {title} -{c['id'][:8]}.md"
        path = os.path.join(args.out, fname)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(render_md(c))
        index.append((t, title, c["project"], fname, len(c["msgs"]), c["chars"]))

    idx = ["---", "type: index", "tags: [cursor-raw, index]", "---", "", "# Cursor 原始对话索引", "",
           f"共 {len(index)} 条会话，导出时间 {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
           "| 日期 | 标题 | 项目 | 消息数 | 字符数 |", "|---|---|---|---:|"]
    for t, title, project, fname, nm, ch in index:
        link = fname[:-3].replace("|", "\\|")
        idx.append(f"| {t.strftime('%Y-%m-%d') if t else ''} | [[{link}]] | {project} | {nm} | {ch:,} |")
    with open(os.path.join(args.out, "_index.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(idx) + "\n")
    print(f"wrote {len(index)} files to {args.out}", file=sys.stderr)
    if args.clean:
        shutil.rmtree(os.path.dirname(db), ignore_errors=True)


if __name__ == "__main__":
    main()
