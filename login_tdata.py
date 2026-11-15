#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tdata -> 独立 Telethon 用户会话

把桌面版 Telegram 的 tdata 登录态转换成一份独立的 Telethon session:
- CreateNewSession: 生成全新 auth_key, 等效"多登一台设备", 桌面端不被互踢
- 转换在 SOCKS5 代理下完成(国内环境必需)

用法:
  python login_tdata.py
  python login_tdata.py --tdata "C:/Users/xxx/AppData/Roaming/Telegram Desktop/tdata" \
                        --session data/reader.session --proxy-port 7897
"""
import argparse
import asyncio
import os

from opentele2.api import API, CreateNewSession
from opentele2.td import TDesktop


def parse():
    ap = argparse.ArgumentParser(description="tdata -> 独立 Telethon 用户会话")
    ap.add_argument("--tdata", default=os.path.expandvars(
        r"%APPDATA%\Telegram Desktop\tdata"), help="桌面版 tdata 目录")
    ap.add_argument("--session", default="data/reader.session",
                    help="输出 session 路径")
    ap.add_argument("--proxy-port", type=int, default=7897,
                    help="本机 SOCKS5 代理端口(TG 需代理的环境必填), 0=直连")
    return ap.parse_args()


async def run(a):
    proxy = ("socks5", "127.0.0.1", a.proxy_port) if a.proxy_port else None
    os.makedirs(os.path.dirname(os.path.abspath(a.session)) or ".", exist_ok=True)

    td = TDesktop(a.tdata)          # 构造即加载
    if not td.isLoaded():
        raise SystemExit("[!] tdata 加载失败: %s (桌面版需保持登录态)" % a.tdata)

    client = await td.ToTelethon(
        session=a.session,
        flag=CreateNewSession,      # 独立 auth_key; UseCurrentSession 会与桌面端互踢!
        api=API.TelegramDesktop,
        proxy=proxy)
    await client.connect()
    ok = await client.is_user_authorized()
    me = await client.get_me()
    await client.disconnect()
    if not ok:
        raise SystemExit("[!] 会话授权失败, 请检查代理可用性后重试")
    print("[+] session=%s" % a.session)
    print("[+] user=%s (id=%s)" % (me.first_name, me.id))
    print("[+] api_id/api_hash 使用 Telegram Desktop 公共对, config.json 已默认配好")


if __name__ == "__main__":
    asyncio.run(run(parse()))
