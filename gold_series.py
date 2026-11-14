"""国际金价序列。

近一天：cngoldprice.com 首页实时曲线，和现有推送用的是同一条国际金价。
近两周：新浪伦敦金（XAU）交易日收盘，按 Frankfurter 的美元兑人民币折成元/克。
本地文件 international_gold.json 只存国际金价。隔一天把这份数据写入飞书表格。
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone

import requests

import gold_price_report as gold
import pc_price_report as charts

OUNCE_GRAMS = 31.1034768
CST = timezone(timedelta(hours=8))
STORE_PATH = os.path.join(os.path.dirname(__file__), "international_gold.json")
SPREADSHEET_TOKEN = "Pe1hsPFo5hlTgot6bxJcAcsynsh"
SINA_DAILY = (
    "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
    "var%20_XAU=/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol=XAU"
)


def now_cst():
    return datetime.now(CST)


def parse_intraday(html):
    matches = list(re.finditer(
        r'timestamp\\?":(\d+),\\?"price\\?":(\d+(?:\.\d+)?)',
        html,
    ))
    if not matches:
        raise RuntimeError("页面上找不到国际金价曲线")
    points = [matches[0]]
    for previous, current in zip(matches, matches[1:]):
        if current.start() - previous.end() > 20:
            break
        points.append(current)
    series = []
    for item in points:
        moment = datetime.fromtimestamp(int(item.group(1)) / 1000, CST)
        series.append((moment, round(float(item.group(2)), 2)))
    series.sort(key=lambda item: item[0])
    return series


def fetch_daily(days=14):
    response = requests.get(
        SINA_DAILY,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"},
        timeout=30,
    )
    response.raise_for_status()
    text = response.text
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < start:
        raise RuntimeError("新浪伦敦金日线解析失败")
    rows = json.loads(text[start:end + 1])
    start_day = now_cst().date() - timedelta(days=days - 1)
    chosen = [row for row in rows if row.get("date") and row["date"] >= start_day.isoformat()]
    if len(chosen) < 2:
        raise RuntimeError("近两周伦敦金日线不足")
    fx = requests.get(
        "https://api.frankfurter.app/{}..?from=USD&to=CNY".format(
            (start_day - timedelta(days=7)).isoformat()
        ),
        timeout=30,
    )
    fx.raise_for_status()
    rates = fx.json().get("rates") or {}
    rate_days = sorted(rates)
    series = []
    for row in chosen:
        day = row["date"]
        earlier = [key for key in rate_days if key <= day]
        if not earlier:
            continue
        usd_cny = float(rates[earlier[-1]]["CNY"])
        usd = float(row["close"])
        price = round(usd * usd_cny / OUNCE_GRAMS, 2)
        series.append({
            "date": day,
            "price_cny_per_gram": price,
            "usd_per_ounce": round(usd, 2),
            "usd_cny": usd_cny,
        })
    if len(series) < 2:
        raise RuntimeError("近两周没有可折算的国际金价")
    return series


def hourly_points(intraday):
    if not intraday:
        raise RuntimeError("没有近一天的国际金价")
    latest = intraday[-1][0]
    start = latest - timedelta(hours=24)
    buckets = {}
    for moment, price in intraday:
        if moment < start:
            continue
        hour = moment.replace(minute=0, second=0, microsecond=0)
        buckets[hour] = price
    points = sorted(buckets.items())
    if len(points) < 2:
        raise RuntimeError("近一天的小时金价不足")
    return points


def load_store():
    if not os.path.isfile(STORE_PATH):
        return {"daily": [], "intraday": [], "last_feishu_date": None, "last_feishu_rows": 0}
    with open(STORE_PATH, encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("daily", [])
    data.setdefault("intraday", [])
    data.setdefault("last_feishu_date", None)
    data.setdefault("last_feishu_rows", 0)
    return data


def save_store(store):
    with open(STORE_PATH, "w", encoding="utf-8") as handle:
        json.dump(store, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def merge_store(store, daily, intraday):
    by_date = {item["date"]: item for item in store["daily"]}
    for item in daily:
        by_date[item["date"]] = item
    store["daily"] = [by_date[key] for key in sorted(by_date)]

    by_time = {item["time"]: item["price_cny_per_gram"] for item in store["intraday"]}
    for moment, price in intraday:
        by_time[moment.isoformat()] = price
    cutoff = now_cst() - timedelta(days=3)
    kept = []
    for stamp, price in sorted(by_time.items()):
        moment = datetime.fromisoformat(stamp)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=CST)
        if moment >= cutoff:
            kept.append({"time": moment.isoformat(), "price_cny_per_gram": price})
    store["intraday"] = kept
    return store


def should_write_feishu(store):
    last = store.get("last_feishu_date")
    if not last:
        return True
    return (now_cst().date() - datetime.fromisoformat(last).date()).days >= 2


def feishu_rows(store):
    rows = [["时间", "国际金价(元/克)", "粒度"]]
    for item in store["daily"]:
        rows.append([item["date"], item["price_cny_per_gram"], "日"])
    for item in store["intraday"]:
        rows.append([item["time"], item["price_cny_per_gram"], "小时内采样"])
    return rows


def write_feishu(store):
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        print("飞书凭据还没配置，本次跳过写入。需要 FEISHU_APP_ID、FEISHU_APP_SECRET，并把表格共享给该应用。")
        return False
    if not should_write_feishu(store):
        print("距上次写入飞书不足 2 天，本次跳过。")
        return False
    token_response = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=30,
    )
    token_body = token_response.json()
    if token_body.get("code") != 0:
        raise RuntimeError("获取飞书 token 失败: {}".format(token_body.get("msg")))
    token = token_body["tenant_access_token"]
    headers = {"Authorization": "Bearer {}".format(token)}
    meta = requests.get(
        "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/metainfo".format(SPREADSHEET_TOKEN),
        headers=headers,
        timeout=30,
    ).json()
    sheets = (meta.get("data") or {}).get("sheets") or []
    if meta.get("code") != 0 or not sheets:
        raise RuntimeError("读取飞书表格失败: {}".format(meta.get("msg")))
    sheet_id = sheets[0].get("sheetId") or sheets[0].get("sheet_id")
    values = feishu_rows(store)
    blank_until = max(int(store.get("last_feishu_rows") or 0), len(values))
    while len(values) < blank_until:
        values.append(["", "", ""])
    value_range = "{}!A1:C{}".format(sheet_id, len(values))
    written = requests.put(
        "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/values".format(SPREADSHEET_TOKEN),
        headers=headers,
        json={"valueRange": {"range": value_range, "values": values}},
        timeout=30,
    ).json()
    if written.get("code") != 0:
        raise RuntimeError("写入飞书表格失败: {}".format(written.get("msg")))
    store["last_feishu_date"] = now_cst().date().isoformat()
    store["last_feishu_rows"] = len(values)
    print("feishu write: ok rows={}".format(len(feishu_rows(store))))
    return True


def render_gold_charts(daily, hourly, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    font_path = charts.find_cjk_font()
    if font_path:
        font_manager.fontManager.addfont(font_path)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=font_path).get_name()
    plt.rcParams["axes.unicode_minus"] = False

    specs = [
        (
            "gold-daily.png",
            "近2周国际金价（交易日收盘）",
            [datetime.fromisoformat(item["date"]) for item in daily],
            [item["price_cny_per_gram"] for item in daily],
            "%m-%d",
            "伦敦金收盘 × 美元兑人民币，元/克",
        ),
        (
            "gold-hourly.png",
            "近一天国际金价（每小时）",
            [item[0] for item in hourly],
            [item[1] for item in hourly],
            "%m-%d %H:%M",
            "金价站实时曲线按小时取最后一笔，元/克",
        ),
    ]
    paths = []
    for filename, title, dates, prices, date_format, note in specs:
        fig, ax = plt.subplots(figsize=(10.5, 5.2), dpi=140)
        fig.patch.set_facecolor("#fafaf8")
        ax.set_facecolor("#ffffff")
        ax.plot(dates, prices, color="#b45309", linewidth=2.2, marker="o", markersize=4.5)
        ax.annotate(
            charts.format_price(prices[-1]),
            (dates[-1], prices[-1]),
            textcoords="offset points",
            xytext=(6, 8),
            color="#b45309",
        )
        ax.set_title(title, loc="left", fontsize=15, pad=12)
        ax.set_ylabel("元/克")
        ax.grid(True, axis="y", color="#e7e5e4", linewidth=0.8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.xaxis.set_major_formatter(mdates.DateFormatter(date_format))
        fig.text(0.01, 0.01, note, color="#78716c", fontsize=9)
        fig.autofmt_xdate(rotation=30, ha="right")
        fig.tight_layout(rect=(0, 0.04, 1, 1))
        path = os.path.join(output_dir, filename)
        fig.savefig(path)
        plt.close(fig)
        paths.append(path)
        print("chart:", path)
    return paths


def refresh():
    page = gold.fetch_page()
    shuibei = gold.get_shuibei_price(page)
    international = gold.get_international_price(page)
    intraday = parse_intraday(page)
    daily = fetch_daily()
    hourly = hourly_points(intraday)
    store = merge_store(load_store(), daily, intraday)
    write_feishu(store)
    save_store(store)
    image_paths = render_gold_charts(
        daily,
        hourly,
        os.path.join(os.path.dirname(__file__), "_gold_out"),
    )
    return {
        "shuibei": shuibei,
        "international": international,
        "daily": daily,
        "hourly": hourly,
        "charts": image_paths,
    }
