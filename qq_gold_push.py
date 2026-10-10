import argparse
import asyncio
import json
import os

import requests

import gold_price_report as gold


def require_qq_env(name):
    return gold.require_env(name)


def get_qq_token(app_id, app_secret):
    response = requests.post(
        "https://api.bot.qq.com/app/getAppAccessToken",
        json={"appId": app_id, "clientSecret": app_secret},
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    token = body.get("access_token")
    if not token:
        raise RuntimeError("获取 QQ access_token 失败")
    print("qq access_token: ok")
    return token


def build_message(shuibei_price, international_price):
    today = gold.datetime.date.today().strftime("%Y年%m月%d日")
    return "金价情况\n{}\n水贝金价 {} 元/克\n国际金价 {} 元/克".format(
        today, shuibei_price, international_price
    )


def send_group_message(token, group_openid, content):
    response = requests.post(
        "https://api.bot.qq.com/v2/groups/{}/messages".format(group_openid),
        headers={
            "Authorization": "QQBot {}".format(token),
            "Content-Type": "application/json",
        },
        json={"msg_type": 0, "content": content},
        timeout=30,
    )
    try:
        body = response.json()
    except ValueError:
        body = {}
    print(
        "qq send status={} code={} message={}".format(
            response.status_code,
            body.get("code", body.get("err_code", "")),
            body.get("message", body.get("msg", "")),
        )
    )
    if response.status_code >= 400:
        raise RuntimeError("QQ 群消息发送失败")
    if body.get("id"):
        print("qq message id: ok")


def push_gold_price():
    app_id = require_qq_env("QQ_APP_ID")
    app_secret = require_qq_env("QQ_APP_SECRET")
    group_openid = require_qq_env("QQ_GROUP_OPENID")
    page = gold.fetch_page()
    shuibei_price = gold.get_shuibei_price(page)
    international_price = gold.get_international_price(page)
    content = build_message(shuibei_price, international_price)
    print(content)
    token = get_qq_token(app_id, app_secret)
    send_group_message(token, group_openid, content)


def credentials_ready():
    names = ("QQ_APP_ID", "QQ_APP_SECRET", "QQ_GROUP_OPENID")
    present = [name for name in names if os.environ.get(name, "").strip()]
    if len(present) == len(names):
        return True
    if not present:
        print("QQ 凭据还没配置，本次跳过。需要 QQ_APP_ID、QQ_APP_SECRET、QQ_GROUP_OPENID。")
        return False
    missing = [name for name in names if name not in present]
    raise RuntimeError("QQ 凭据不完整，还缺: {}".format(", ".join(missing)))


async def capture_group_openid(timeout_sec):
    app_id = require_qq_env("QQ_APP_ID")
    app_secret = require_qq_env("QQ_APP_SECRET")
    token = get_qq_token(app_id, app_secret)
    import websockets

    async with websockets.connect("wss://api.bot.qq.com/websocket/", open_timeout=20) as ws:
        hello = json.loads(await asyncio.wait_for(ws.recv(), 20))
        interval = hello.get("d", {}).get("heartbeat_interval", 45000) / 1000
        seq = {"n": None}

        async def heartbeat():
            while True:
                await ws.send(json.dumps({"op": 1, "d": seq["n"]}))
                await asyncio.sleep(interval)

        await ws.send(json.dumps({
            "op": 2,
            "d": {
                "token": "QQBot {}".format(token),
                "intents": 1 << 25,
                "shard": [0, 1],
                "properties": {
                    "$os": "linux",
                    "$browser": "qq-gold-push",
                    "$device": "qq-gold-push",
                },
            },
        }))
        heart = asyncio.create_task(heartbeat())
        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout_sec
            print("等待群事件。请在 {} 秒内把机器人拉进群，或在群里 @ 它一次。".format(timeout_sec))
            while True:
                remain = deadline - loop.time()
                if remain <= 0:
                    raise RuntimeError("等待超时，还没拿到 group_openid")
                payload = json.loads(await asyncio.wait_for(ws.recv(), remain))
                if payload.get("s") is not None:
                    seq["n"] = payload["s"]
                if payload.get("op") == 9:
                    raise RuntimeError("QQ 鉴权失败，请检查 AppID 和 AppSecret")
                if payload.get("op") != 0:
                    continue
                data = payload.get("d") or {}
                group_openid = data.get("group_openid")
                print("event:", payload.get("t"))
                if group_openid:
                    print("QQ_GROUP_OPENID:", group_openid)
                    return group_openid
        finally:
            heart.cancel()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if args.capture:
        asyncio.run(capture_group_openid(args.timeout))
        return
    if credentials_ready():
        push_gold_price()


if __name__ == "__main__":
    main()
