import base64
import os

import requests

import pc_price_report as report
import qq_gold_push as qq


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


def push_pc_prices():
    if not qq.credentials_ready():
        return
    products = report.load_products()
    content = report.build_message(products)
    print(content)
    charts = report.render_charts(products, os.path.join(os.path.dirname(__file__), "_pc_price_out"))
    token = qq.get_qq_token(qq.require_qq_env("QQ_APP_ID"), qq.require_qq_env("QQ_APP_SECRET"))
    group_openid = qq.require_qq_env("QQ_GROUP_OPENID")
    qq.send_group_message(token, group_openid, content)
    for path in charts:
        file_info = upload_group_image(token, group_openid, path)
        send_group_image(token, group_openid, file_info)


if __name__ == "__main__":
    push_pc_prices()
