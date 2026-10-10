import csv
import os
import re
import requests
import datetime


def require_env(name):
    value = os.environ.get(name)
    if value is None or not str(value).strip():
        raise RuntimeError(f"缺少环境变量 {name}")
    return str(value).strip()


def get_access_token():
    # 获取access token的url
    url = 'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={}&secret={}' \
        .format(appID, appSecret)
    response = requests.get(url, timeout=30).json()
    access_token = response.get('access_token')
    if not access_token:
        raise RuntimeError(
            "获取微信 access_token 失败: errcode={} errmsg={}".format(
                response.get("errcode"), response.get("errmsg")
            )
        )
    print("access_token: ok")
    return access_token


def get_gold_price():
    """读取首页实时金价曲线的最新一个点。"""
    url = "https://cngoldprice.com/"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GithubActionSample/1.0)"}
    response = requests.get(url=url, headers=headers, timeout=30)
    response.raise_for_status()
    matches = list(re.finditer(
        r'timestamp\\?":(\d+),\\?"price\\?":(\d+(?:\.\d+)?)',
        response.text,
    ))
    if not matches:
        raise RuntimeError("页面上找不到实时金价曲线数据，站点结构可能已变化")

    series = [matches[0]]
    for previous, current in zip(matches, matches[1:]):
        if current.start() - previous.end() > 20:
            break
        series.append(current)

    timestamp, price = max(
        ((int(item.group(1)), item.group(2)) for item in series),
        key=lambda item: item[0],
    )
    shown = f"{float(price):.2f}"
    point_time = datetime.datetime.fromtimestamp(
        timestamp / 1000, datetime.timezone(datetime.timedelta(hours=8))
    )
    print("chart latest:", point_time.strftime("%Y-%m-%d %H:%M"), shown)
    return shown
def send_gold_price(access_token, gold_price):
    today = datetime.date.today()
    # yesterday = today - datetime.timedelta(days=1)
    today_str = today.strftime("%Y年%m月%d日")

    body = {
        "touser": openId,
        "template_id": gold_template_id,
        "url": "https://weixin.qq.com",
        "data": {
            "date": {
                "value": today_str
            },
            "gold_price": {
                "value": gold_price
            }
        }
    }
    url = 'https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={}'.format(access_token)
    result = requests.post(url, json=body, timeout=30).json()
    print("wechat send: errcode={} errmsg={}".format(result.get("errcode"), result.get("errmsg")))
    if result.get("errcode") not in (0, None):
        raise RuntimeError("微信模板消息发送失败: {}".format(result.get("errmsg")))

def data_to_csv(gold_price):
    header = ['date', 'gold_price']
    file_path = 'gold_price_result.csv'
    today_str = datetime.date.today().strftime("%Y年%m月%d日")

    rows = []
    if os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
        with open(file_path, mode='r', newline='', encoding='utf-8') as file:
            rows = list(csv.reader(file))
    if not rows:
        rows = [header]

    updated = False
    for row in rows[1:]:
        if row and row[0] == today_str:
            row[1] = gold_price
            updated = True
            break
    if not updated:
        rows.append([today_str, gold_price])

    with open(file_path, mode='w', newline='', encoding='utf-8') as file:
        csv.writer(file).writerows(rows)





if __name__ == '__main__':
    # 从测试号信息获取
    appID = require_env("APP_ID")
    appSecret = require_env("APP_SECRET")
    # 收信人ID即 用户列表中的微信号
    openId = require_env("OPEN_ID")
    # 金价模板ID
    gold_template_id = require_env("GOLD_TEMPLATE_ID")



    gold_price=get_gold_price()
    data_to_csv(gold_price)
    access_token = get_access_token()
    send_gold_price(access_token, gold_price)

    openId="onF0w6z7Xu-tnbd7vCfaDUqmgK1A"
    access_token = get_access_token()
    send_gold_price(access_token, gold_price)
    

    





