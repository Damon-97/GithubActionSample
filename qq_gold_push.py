import argparse
import asyncio
import base64
import json
import os

import requests

import gold_price_report as gold
import gold_series
import pc_price_report as price_fmt


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


def move_text(start_price, end_price):
    delta = end_price - start_price
    if not start_price:
        return "无对比"
    pct = delta / start_price * 100
    sign = "+" if delta > 0 else ""
    return "{}{} 元（{}{:.1f}%）".format(
        sign, price_fmt.format_price(delta), sign, pct
    )


def build_message(shuibei_price, international_price, daily, hourly):
    today = gold.datetime.date.today().strftime("%Y年%m月%d日")
    first_day, last_day = daily[0], daily[-1]
    first_hour, last_hour = hourly[0], hourly[-1]
    return "\n".join([
        "金价情况",
        today,
        "水贝金价 {} 元/克".format(shuibei_price),
        "国际金价 {} 元/克".format(international_price),
        "",
        "近2周（伦敦金交易日收盘，元/克）",
        "{}  {}".format(last_day["date"], price_fmt.format_price(last_day["price_cny_per_gram"])),
        "较 {} 的 {}，变动 {}".format(
            first_day["date"],
            price_fmt.format_price(first_day["price_cny_per_gram"]),
            move_text(first_day["price_cny_per_gram"], last_day["price_cny_per_gram"]),
        ),
        "",
        "近一天（每小时，元/克）",
        "{}  {}".format(last_hour[0].strftime("%m-%d %H:%M"), price_fmt.format_price(last_hour[1])),
        "较 {} 的 {}，变动 {}".format(
            first_hour[0].strftime("%m-%d %H:%M"),
            price_fmt.format_price(first_hour[1]),
            move_text(first_hour[1], last_hour[1]),
        ),
    ])


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


def upload_group_image(token, group_openid, png_path):
    with open(png_path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")
    response = requests.post(
        "https://api.bot.qq.com/v2/groups/{}/files".format(group_openid),
        headers={
            "Authorization": "QQBot {}".format(token),
            "Content-Type": "application/json",
        },
        json={
            "file_type": 1,
            "file_name": os.path.basename(png_path),
            "file_data": encoded,
            "srv_send_msg": False,
        },
        timeout=60,
    )
    try:
        body = response.json()
    except ValueError:
        body = {}
    print("qq image status={} message={}".format(response.status_code, body.get("message", "")))
    if response.status_code >= 400 or not body.get("file_info"):
        raise RuntimeError("QQ 图片上传失败")
    return body["file_info"]


def send_group_image(token, group_openid, file_info):
    response = requests.post(
        "https://api.bot.qq.com/v2/groups/{}/messages".format(group_openid),
        headers={
            "Authorization": "QQBot {}".format(token),
            "Content-Type": "application/json",
        },
        json={"msg_type": 7, "media": {"file_info": file_info}},
        timeout=30,
    )
    try:
        body = response.json()
    except ValueError:
        body = {}
    print("qq image send status={} message={}".format(response.status_code, body.get("message", "")))
    if response.status_code >= 400:
        raise RuntimeError("QQ 图片消息发送失败")


def push_gold_price():
    app_id = require_qq_env("QQ_APP_ID")
    app_secret = require_qq_env("QQ_APP_SECRET")
    group_openid = require_qq_env("QQ_GROUP_OPENID")
    snapshot = gold_series.refresh()
    content = build_message(
        snapshot["shuibei"],
        snapshot["international"],
        snapshot["daily"],
        snapshot["hourly"],
    )
    print(content)
    token = get_qq_token(app_id, app_secret)
    send_group_message(token, group_openid, content)
    for path in snapshot["charts"]:
        file_info = upload_group_image(token, group_openid, path)
        send_group_image(token, group_openid, file_info)


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
