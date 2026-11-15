# tg-group-reader

用**你自己的 Telegram 账号**（userbot）读取指定群组的消息。

不需要机器人入群、不需要收验证码 —— 登录态直接复用桌面版 Telegram 的 tdata，
转换成一份独立的 Telethon session（等效"多登一台设备"，桌面端不受影响）。

## 功能

| 组件 | 说明 |
|---|---|
| `login_tdata.py` | 桌面版 tdata → 独立 Telethon 用户会话（一次性） |
| `reader.py` | 实时监听白名单群新消息，打印 / 写 JSONL，断线自愈 |
| `fetch_recent.py` | 回捞某群最近 N 条历史消息（只读） |

- **用户身份收消息**：普通账号即可读群（机器人有 privacy mode 限制且需拉群）
- **断线自愈**：连接断开自动重挑代理、重建 client，不僵死
- **白名单热更新**：改 `config.json` 的 `groups` 免重启
- **自动加群**：白名单里的公开群未加入会自动 `JoinChannel`
- **消息格式化**：文本 + 内嵌隐藏链接（按钮 URL 等实体不丢失）

## 快速开始

```bash
pip install -r requirements.txt

# 1) 一次性: 把桌面版 Telegram 登录态转成独立 session
#    (桌面版需保持登录; 国内环境需本地 SOCKS5 代理)
python login_tdata.py --proxy-port 7897

# 2) 准备配置
cp config.example.json config.json
#    编辑 groups -> 你要读的群, 如 "linuxdoit"

# 3) 实时读取 (Ctrl-C 退出)
python reader.py
python reader.py --jsonl out.jsonl     # 同时落盘

# 4) 回捞历史
python fetch_recent.py linuxdoit 20
```

## 登录原理（tdata → 独立会话）

- [opentele2](https://pypi.org/project/opentele2/)（须 **1.x，2.0 结构已变**）读取桌面版 tdata；
- `ToTelethon(flag=CreateNewSession)` 让 Telegram 服务器为本次签发**全新 auth_key**，
  与桌面端互不干扰。**千万不要用 `UseCurrentSession`** —— 同一 auth_key 并发会被服务器互踢，
  桌面端会话会掉线；
- 转换默认走 SOCKS5 代理（`--proxy-port`）；
- `config.json` 里的 `api_id/api_hash` 默认是 Telegram Desktop 开源仓库里的**公共客户端对**
  （2040 / b18441...），非个人密钥；介意的话可换成 [my.telegram.org](https://my.telegram.org) 申请的自有对。

## 配置说明（config.json）

| 字段 | 说明 |
|---|---|
| `session` | session 文件路径（默认 `data/reader.session`） |
| `groups` | 白名单群：`t.me/xxx`、`@xxx`、用户名或数字 id |
| `proxy_ports` | 本机 SOCKS5 端口列表，按序探测，取第一个通的 |
| `proxy_probe` | 是否做端口探测（GET api.telegram.org） |

## 断线自愈

`reader.py` 主循环为两层：

```
while True:                      # 外环: 连接生命周期
    port = pick_proxy(cfg)       #   每轮重挑可用代理
    client = TelegramClient(..., proxy=port)
    connect / 鉴权 / 挂 NewMessage 监听
    while client.is_connected(): # 内环: 心跳 + 白名单热读 + 补加群
        sleep(10)
    disconnect -> backoff 20s -> 外环重建
```

Telethon 默认重试若干次后会放弃并静默断开，长驻进程若只挂事件不查
`is_connected()` 就会"假活"——本项目吃过这个亏，故把断线检测做成了主循环。

## 踩坑记录（都实测过）

1. `opentele2` 必须 **1.5.x**，2.0 起模块结构变了（无 `td.configs`）。
2. `TGConvertor` 的 `to_telethon_file` 会写错 dc_id/DC 地址 → session 永远 `authorized=False`，别用。
3. Telethon 1.45 用 SOCKS5 必须装 `python-socks[asyncio]`，否则连接连续失败。
4. DC5 正确地址 `149.154.171.5`（若手头工具写的是 `91.108.56.130` 那是弃用地址）。
5. `iter_messages` 与长驻 reader 并发用同一 SQLite session 会抢锁 —— `fetch_recent.py` 用 session 副本规避。

## 隐私与合规

- reader 只输出白名单内的群，其余消息一律忽略、不落盘；
- userbot 属 Telegram 官方容忍但敏感的用法：**仅做只读监听，不要用它群发/加人/爬库**，
  账号有被限流或封禁的风险，请自行评估；
- 请遵守所在地区法律法规与 Telegram ToS。

## License

MIT
