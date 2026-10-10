import csv
import os
import re
import requests
import datetime
from bs4 import BeautifulSoup


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


def _sell_price(text):
    text = text.replace(",", "").strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return text
    return None


def get_gold_price():
    """读取水贝市场批发售价。页面改版后不再使用旧的大号价格节点。"""
    url = "https://cngoldprice.com/"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GithubActionSample/1.0)"}
    response = requests.get(url=url, headers=headers, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    heading = soup.find(id="shuibei-mkt")
    table = None
    if heading is not None:
        section = heading.find_parent("section")
        if section is not None:
            table = section.find("table")
    if table is None:
        for candidate in soup.find_all("table"):
            if "水贝" in candidate.get_text():
                table = candidate
                break
    if table is None:
        raise RuntimeError("页面上找不到水贝市场报价表，站点结构可能已变化")

    body = table.find("tbody")
    rows = body.find_all("tr") if body else table.find_all("tr")[1:]
    quotes = []
    for row in rows:
        cells = [cell.get_text(strip=True) for cell in row.find_all("td")]
        if len(cells) < 2:
            continue
        sell = _sell_price(cells[1])
        if sell is not None:
            quotes.append((cells[0], sell))
    if not quotes:
        raise RuntimeError("水贝报价表里没有可用售价")

    chosen = next((price for name, price in quotes if name == "水贝国际"), quotes[0][1])
    print("shuibei quotes:", ", ".join(f"{name}={price}" for name, price in quotes))
    print("gold_price:", chosen)
    return chosen
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
    # 检查文件是否存在以及是否为空
    file_exists = os.path.isfile(file_path)
    file_empty = file_exists and os.path.getsize(file_path) == 0

    exists_date=set()
    if file_exists:
        with open(file_path, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            next(reader)  # 跳过表头
            exists_date = {row[0] for row in reader}  # 假设日期是索引列，位于第一列

    today = datetime.date.today()
    today_str = today.strftime("%Y年%m月%d日")
    gold_price = gold_price
    data = [[today_str, gold_price]]

    # 写入 CSV 文件
    with open(file_path, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        # 如果文件不存在或为空，则写入表头
        if not file_exists or file_empty:
            writer.writerow(header)
        # 写入数据行
        for row in data:
            if row[0] not in exists_date:
                writer.writerow(row)





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
    

    





