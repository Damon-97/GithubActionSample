"""近 15 日装机配件价格。

价格来自粉象比价公开页面（compare.fenxianglife.com）：
京东、天猫每日最低券后价，画在页面的 180 日走势图里。
站点没有单独的历史价接口，这里按图上的坐标轴把每日价格还原出来。
"""

import os
import re
from datetime import datetime, timedelta

import requests


SOURCE_NAME = "粉象比价"
PRODUCTS = [
    {
        "group": "显卡",
        "name": "技嘉魔鹰 RTX 5060 8G",
        "url": "https://compare.fenxianglife.com/p/gigabyte-geforce-rtx-5060-gaming-oc-8g-nlhrtookrl.html",
    },
    {
        "group": "显卡",
        "name": "瀚铠 9060 XT 8G 黑色合金",
        "url": "https://compare.fenxianglife.com/p/bac21f5a8-amd-radeon-rx-9060-xt-8gb-oc-3qn3mfhr57.html",
    },
    {
        "group": "CPU",
        "name": "R5 9600X",
        "url": "https://compare.fenxianglife.com/p/amd-ryzen-5-9600x-i2nqho4agh.html",
    },
    {
        "group": "CPU",
        "name": "R5 9500F",
        "url": "https://compare.fenxianglife.com/p/amd-ryzen-5-9500f-jlz42ejywu.html",
    },
    {
        "group": "内存",
        "name": "七彩虹战斧 DDR5 6000 16GB",
        "url": "https://compare.fenxianglife.com/p/colorful-ddr5-6000-cl38-bupwhkq7c3.html",
        "note": "清单写的是七彩虹 DDR5 8G×2。公开监测没有完全同名的套条，这条是最接近的七彩虹 DDR5。",
    },
]


def fetch_html(url):
    response = requests.get(url, timeout=30, headers={"User-Agent": "GithubActionSample/pc-price"})
    response.raise_for_status()
    response.encoding = "utf-8"
    return response.text


def tidy_price(price):
    nearest = round(price)
    if abs(price - nearest) <= 0.15:
        return float(nearest)
    return round(price, 2)


def parse_series(html):
    asof_match = re.search(r"截至\s*(\d{4}-\d{2}-\d{2})", html)
    if not asof_match:
        raise RuntimeError("页面没有数据截止日期")
    asof = asof_match.group(1)
    svg_match = re.search(r'<svg viewBox="0 0 520 230".*?</svg>', html)
    if not svg_match:
        raise RuntimeError("页面没有价格走势图")
    svg = svg_match.group(0)
    axis = [
        (float(y), float(amount.replace(",", "")))
        for y, amount in re.findall(r'<text x="72" y="([\d.]+)"[^>]*>¥([\d,.]+)</text>', svg)
    ]
    date_labels = re.findall(r"<text [^>]*>(\d{2}-\d{2})</text>", svg)
    path_match = re.search(r'<path d="([^"]+)"', svg)
    if len(axis) < 2 or len(date_labels) < 2 or not path_match:
        raise RuntimeError("走势图坐标不完整")
    points = [
        (float(x), float(y))
        for x, y in re.findall(r"[ML]\s*([\d.]+),([\d.]+)", path_match.group(1))
    ]
    if len(points) < 2:
        raise RuntimeError("走势图没有价格点")
    y_hi, price_hi = axis[0]
    y_lo, price_lo = axis[1]
    end = datetime.strptime("{}-{}".format(asof[:4], date_labels[-1]), "%Y-%m-%d")
    start = datetime.strptime("{}-{}".format(end.year, date_labels[0]), "%Y-%m-%d")
    if start > end:
        start = start.replace(year=start.year - 1)
    x0, x1 = points[0][0], points[-1][0]
    span_days = max((end - start).days, 1)
    by_day = {}
    for x, y in points:
        day = start + timedelta(days=round((x - x0) / (x1 - x0) * span_days))
        price = price_hi - (y - y_hi) / (y_lo - y_hi) * (price_hi - price_lo)
        by_day[day.date()] = tidy_price(price)
    series = sorted(by_day.items())
    return asof, series


def last_days(series, days=15):
    return series[-days:]


def format_price(price):
    if float(price).is_integer():
        return str(int(price))
    return "{:.2f}".format(price)


def change_text(window):
    first = window[0][1]
    last = window[-1][1]
    if not first:
        return "无对比"
    delta = last - first
    pct = delta / first * 100
    sign = "+" if delta > 0 else ""
    return "{}{} 元（{}{:.1f}%）".format(sign, format_price(delta), sign, pct)


def load_products(days=15):
    loaded = []
    for product in PRODUCTS:
        html = fetch_html(product["url"])
        asof, series = parse_series(html)
        window = last_days(series, days)
        if len(window) < 2:
            raise RuntimeError("{} 的近 {} 日数据不足".format(product["name"], days))
        item = dict(product)
        item["asof"] = asof
        item["window"] = window
        loaded.append(item)
        print("{} {} -> {} ({})".format(
            item["name"], format_price(window[0][1]), format_price(window[-1][1]), asof
        ))
    return loaded


def find_cjk_font():
    windows_fonts = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyh.ttf",
    ]
    for path in windows_fonts:
        if os.path.exists(path):
            return path
    if os.path.isdir("/usr/share/fonts"):
        for root, _dirs, files in os.walk("/usr/share/fonts"):
            for name in files:
                if name.startswith("NotoSansCJK") or name.startswith("NotoSansSC"):
                    return os.path.join(root, name)
    return None


def render_charts(products, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    font_path = find_cjk_font()
    if font_path:
        font_manager.fontManager.addfont(font_path)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=font_path).get_name()
    plt.rcParams["axes.unicode_minus"] = False

    colors = ["#c2410c", "#1d4ed8", "#047857", "#7c3aed", "#b45309"]
    groups = []
    for name in ("显卡", "CPU与内存"):
        if name == "显卡":
            rows = [item for item in products if item["group"] == "显卡"]
        else:
            rows = [item for item in products if item["group"] != "显卡"]
        groups.append((name, rows))

    paths = []
    for index, (title, rows) in enumerate(groups):
        fig, ax = plt.subplots(figsize=(10.5, 5.6), dpi=140)
        fig.patch.set_facecolor("#fafaf8")
        ax.set_facecolor("#ffffff")
        for color_index, item in enumerate(rows):
            dates = [day for day, _price in item["window"]]
            prices = [price for _day, price in item["window"]]
            label = "{}  {}".format(item["name"], format_price(prices[-1]))
            ax.plot(
                dates,
                prices,
                color=colors[color_index % len(colors)],
                linewidth=2.2,
                marker="o",
                markersize=4.5,
                label=label,
            )
            ax.annotate(
                format_price(prices[-1]),
                (dates[-1], prices[-1]),
                textcoords="offset points",
                xytext=(6, 6),
                fontsize=9,
                color=colors[color_index % len(colors)],
            )
        ax.set_title("近15日券后最低价 · {}".format(title), loc="left", fontsize=15, pad=12)
        ax.set_ylabel("元")
        ax.grid(True, axis="y", color="#e7e5e4", linewidth=0.8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=1)
        fig.text(
            0.01,
            0.01,
            "粉象比价 · 京东/天猫每日最低券后价 · 截至各商品页标注日期",
            color="#78716c",
            fontsize=9,
        )
        fig.tight_layout(rect=(0, 0.08, 1, 1))
        path = os.path.join(output_dir, "pc-price-{}.png".format(index + 1))
        fig.savefig(path)
        plt.close(fig)
        paths.append(path)
        print("chart:", path)
    return paths


def build_message(products):
    lines = [
        "装机价格 · 近15天",
        "粉象比价监测的京东、天猫每日最低券后价",
        "",
    ]
    current_group = None
    for item in products:
        if item["group"] != current_group:
            current_group = item["group"]
            lines.append(current_group)
        start_day, start_price = item["window"][0]
        end_day, end_price = item["window"][-1]
        lines.append(item["name"])
        lines.append("{} 元（{}）".format(format_price(end_price), end_day.strftime("%m-%d")))
        lines.append("较 {} 的 {} 元，变动 {}".format(
            start_day.strftime("%m-%d"), format_price(start_price), change_text(item["window"])
        ))
        lines.append(item["url"])
        if item.get("note"):
            lines.append(item["note"])
        lines.append("")
    return "\n".join(lines).strip()


def main():
    products = load_products()
    print(build_message(products))
    render_charts(products, os.path.join(os.path.dirname(__file__), "_pc_price_out"))


if __name__ == "__main__":
    main()
