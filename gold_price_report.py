import csv
import json
import os
import requests
import datetime
from bs4 import BeautifulSoup


def get_access_token():
    # 获取access token的url
    url = 'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={}&secret={}' \
        .format(appID.strip(), appSecret.strip())
    response = requests.get(url).json()
    print(response)
    access_token = response.get('access_token')
    print(f"access_token: {access_token}")
    return access_token
def get_gold_price():
    url = 'https://cngoldprice.com/'
    response = requests.get(url=url)
    content = response.text
    soup = BeautifulSoup(content, 'html.parser')
    gold_price = soup.find('div', class_='text-4xl font-bold mb-2 p-4 pb-0 text-center')
    # print(gold_price.text)
    return gold_price.text
def send_gold_price(access_token, gold_price):
    today = datetime.date.today()
    today_str = today.strftime("%Y年%m月%d日")

    body = {
        "touser": openId.strip(),
        "template_id": gold_template_id.strip(),
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
    print(requests.post(url, json.dumps(body)).text)

def data_to_csv(gold_price):
    header = ['date', 'gold_price']
    file_path = 'output.csv'
    # 检查文件是否存在以及是否为空
    file_exists = os.path.isfile(file_path)
    file_empty = file_exists and os.path.getsize(file_path) == 0

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
        writer.writerows(data)

if __name__ == '__main__':
    # 从测试号信息获取
    appID = os.environ.get("APP_ID")
    appSecret = os.environ.get("APP_SECRET")
    # 收信人ID即 用户列表中的微信号
    openId = os.environ.get("OPEN_ID")
    # 天气预报模板ID
    gold_template_id = os.environ.get("GOLD_TEMPLATE_ID")
    

    gold_price=get_gold_price()
    data_to_csv(gold_price)
    access_token = get_access_token()
    send_gold_price(access_token, gold_price)




