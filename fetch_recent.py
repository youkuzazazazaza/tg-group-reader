#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回捞指定群最近 N 条消息 (只读)

用 session 的临时副本连接, 避免与正在运行的 reader.py 抢 SQLite 锁。
输出到 stdout, 也可 --jsonl 落盘。

用法:
  python fetch_recent.py linuxdoit 20
  python fetch_recent.py t.me/telegram 50 --jsonl back.jsonl
"""
import argparse
import asyncio
import datetime
import json
import os
import shutil
import tempfile

from telethon import TelegramClient

BASE = os.path.dirname(os.path.abspath(__file__))

PUB_API_ID = 2040
PUB_API_HASH = "b18441a1ff607e10a989891a5462e627"


def norm_group(s):
    for p in ("https://t.me/", "http://t.me/", "t.me/", "@"):
        if s.startswith(p):
            return s[len(p):]
    return s.split("?")[0].rstrip("/")


def fmt_text(m):
    t = m.raw_text or ""
    extra = []
    for e in (m.entities or []):
        u = getattr(e, "url", None)
        if u and u not in t:
            extra.append(u)
    if extra:
        t = (t + "\n" + "\n".join(extra)).strip()
    if not t:
        if m.photo:
            t = "<photo>"
        elif m.video:
            t = "<video>"
        elif m.media:
            t = "<media>"
        else:
            t = ""
    return t


def main():
    ap = argparse.ArgumentParser(description="回捞 TG 群最近 N 条消息")
    ap.add_argument("group", help="群标识: t.me/xxx / @xxx / 用户名 / 数字id")
    ap.add_argument("n", type=int, nargs="?", default=20, help="条数, 默认20")
    ap.add_argument("--config", default=os.path.join(BASE, "config.json"))
    ap.add_argument("--jsonl", default=None)
    a = ap.parse_args()

    cfg = json.load(open(a.config, encoding="utf-8"))
    api_id = int(cfg.get("api_id") or PUB_API_ID)
    api_hash = cfg.get("api_hash") or PUB_API_HASH
    sess = cfg.get("session") or "data/reader.session"
    if not os.path.isabs(sess):
        sess = os.path.join(BASE, sess)
    if not os.path.exists(sess + ".session"):
        raise SystemExit("[!] 找不到 %s, 请先运行 python login_tdata.py" % sess)

    port = (cfg.get("proxy_ports") or [7897])[0]
    proxy = ("socks5", "127.0.0.1", port) if port else None

    tmp = tempfile.mktemp(suffix=".session")
    shutil.copy(sess + ".session", tmp)  # 副本, 避免与 reader 并发锁

    async def run():
        client = TelegramClient(tmp, api_id, api_hash, proxy=proxy)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise SystemExit("[!] session 未授权, 请重新运行 login_tdata.py")
            entity = await client.get_entity(norm_group(a.group))
            out = open(a.jsonl, "a", encoding="utf-8") if a.jsonl else None
            async for m in client.iter_messages(entity, limit=a.n):
                sender = await m.get_sender()
                name = getattr(sender, "title", None) or \
                    (getattr(sender, "first_name", None) or "") or \
                    (getattr(sender, "username", None) or str(getattr(sender, "id", "?")))
                rec = {"ts": m.date.isoformat(timespec="seconds") if m.date else None,
                       "group": norm_group(a.group),
                       "sender_id": getattr(sender, "id", None),
                       "sender": name,
                       "text": fmt_text(m),
                       "msg_id": m.id}
                print("[%s] %s: %s" % (rec["ts"], name,
                                       rec["text"].replace("\n", " "))[:300])
                if out:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if out:
                out.close()
        finally:
            await client.disconnect()
            for suf in ("", "-journal"):
                try:
                    os.remove(tmp + suf)
                except OSError:
                    pass

    asyncio.run(run())


if __name__ == "__main__":
    main()
