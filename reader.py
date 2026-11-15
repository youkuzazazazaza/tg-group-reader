#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TG 群消息实时读取器 (userbot)

以你自己的 Telegram 账号身份监听白名单群的新消息, 打印到 stdout / 追加写 JSONL。
不需要机器人入群、不需要收验证码 (登录态来自 login_tdata.py 转换的 session)。

特性:
- 断线自愈: client 断开后自动重挑代理、重建连接
- 自动 JoinChannel: 白名单里的公开群未加入会自动加入
- 白名单热读: 修改 config.json 的 groups 即生效, 免重启
- 隐藏链接: 消息内嵌 URL 实体(按钮链接等)追加在文本尾部, 不丢失

用法:
  python reader.py
  python reader.py --jsonl out.jsonl        # 同时落盘 JSONL
  python reader.py --config my.json
"""
import argparse
import asyncio
import datetime
import json
import os

import requests
from telethon import TelegramClient, events

BASE = os.path.dirname(os.path.abspath(__file__))

# Telegram Desktop 官方客户端的公共 api 对(开源仓库可见), 也可换成你自己的
PUB_API_ID = 2040
PUB_API_HASH = "b18441a1ff607e10a989891a5462e627"


def load_cfg(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("api_id", PUB_API_ID)
    cfg.setdefault("api_hash", PUB_API_HASH)
    cfg.setdefault("session", "data/reader.session")
    cfg.setdefault("groups", [])
    cfg.setdefault("proxy_ports", [7897])
    cfg.setdefault("proxy_probe", True)
    return cfg


def pick_proxy(cfg):
    """探测各 SOCKS5 端口可用性, 返回可用端口(int), 0=直连。"""
    ports = cfg["proxy_ports"] or [0]
    if not cfg["proxy_probe"] or not ports[0]:
        return ports[0]
    for port in ports:
        try:
            r = requests.get("https://api.telegram.org",
                             proxies={"https": "socks5h://127.0.0.1:%d" % port},
                             timeout=8)
            if r.status_code < 500:
                return port
        except Exception:
            continue
    return ports[0]


def norm_group(s):
    for p in ("https://t.me/", "http://t.me/", "t.me/", "@"):
        if s.startswith(p):
            return s[len(p):]
    return s.split("?")[0].rstrip("/")


def fmt_text(m):
    """raw_text + entities 里的隐藏链接。"""
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
    ap = argparse.ArgumentParser(description="TG 群消息实时读取器(userbot)")
    ap.add_argument("--config", default=os.path.join(BASE, "config.json"))
    ap.add_argument("--jsonl", default=None, help="可选, 消息追加写入该 JSONL 文件")
    a = ap.parse_args()

    cfg = load_cfg(a.config)
    sess = cfg["session"]
    if not os.path.isabs(sess):
        sess = os.path.join(BASE, sess)
    if not os.path.exists(sess + ".session"):
        raise SystemExit("[!] 找不到 %s, 请先运行 python login_tdata.py" % sess)

    jf = None
    if a.jsonl:
        jf = open(a.jsonl, "a", encoding="utf-8")

    def ts():
        return datetime.datetime.now().strftime("%m-%d %H:%M:%S")

    def emit(rec):
        line = "[%s] [%s] %s: %s" % (rec["ts"], rec["group"], rec["sender"],
                                     rec["text"].replace("\n", " "))
        print(line[:300])
        if jf:
            jf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            jf.flush()

    async def amain():
        from telethon.tl.functions.channels import JoinChannelRequest

        joined_cache = set()

        while True:  # 自愈外环: 断线 -> 重挑代理重建 client
            port = pick_proxy(cfg)
            proxy = ("socks5", "127.0.0.1", port) if port else None
            client = TelegramClient(sess, cfg["api_id"], cfg["api_hash"], proxy=proxy)
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    raise SystemExit("[!] session 未授权, 请重新运行 login_tdata.py")
                me = await client.get_me()
                print("[%s] user mode as %s (id=%s) proxy=%s" %
                      (ts(), me.first_name, me.id, port or "direct"))
            except SystemExit:
                raise
            except Exception as e:
                print("[%s] connect err %r -> retry in 30s" % (ts(), e))
                await asyncio.sleep(30)
                continue

            async def ensure_joined(keys):
                ok = []
                for k in keys:
                    try:
                        await client(JoinChannelRequest(k))
                        print("[%s] joined %s" % (ts(), k))
                        ok.append(k)
                    except Exception as e:
                        print("[%s] join %s err %r" % (ts(), k, e))
                        ok.append(k)  # 可能已加入/私有群, 也放进 cache 免反复重试
                return ok

            @client.on(events.NewMessage())
            async def on_msg(ev):
                chat = await ev.get_chat()
                uname = (getattr(chat, "username", None) or "").lower()
                cid = getattr(chat, "id", None)
                title = getattr(chat, "title", None) or ""
                white = set()
                for g in cfg["groups"]:
                    g = norm_group(g.strip().lower())
                    if g.lstrip("-").isdigit():
                        white.add(int(g))
                    else:
                        white.add(g)
                hit = ((uname and uname in white) or (cid in white)
                       or (title and title.lower() in
                           {norm_group(g) for g in cfg["groups"]}))
                if not hit:
                    return
                m = ev.message
                sender = await m.get_sender()
                name = getattr(sender, "title", None) or \
                    (getattr(sender, "first_name", None) or "") or \
                    (getattr(sender, "username", None) or str(getattr(sender, "id", "?")))
                rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                       "group": uname or title or cid,
                       "sender_id": getattr(sender, "id", None),
                       "sender": name,
                       "text": fmt_text(m),
                       "msg_id": m.id}
                emit(rec)

            while True:
                if not client.is_connected():
                    print("[%s] client disconnected -> recreate" % ts())
                    break
                # 白名单热读(改 config.json 免重启) + 补加群
                try:
                    cfg.update(load_cfg(a.config))
                except Exception:
                    pass
                keys = {norm_group(g.strip().lower()) for g in cfg["groups"]}
                todo = keys - joined_cache
                if todo:
                    try:
                        joined_cache |= set(await ensure_joined(todo))
                    except Exception as e:
                        print("[%s] join loop err %r" % (ts(), e))
                await asyncio.sleep(10)

            try:
                await client.disconnect()
            except Exception:
                pass
            await asyncio.sleep(20)  # backoff 后重挑代理

    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
