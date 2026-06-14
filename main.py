import requests
import time
import statistics
import os
from datetime import datetime

BASE_URL = "https://api.lbkex.com/v2"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = "8764455139"

SCAN_INTERVAL = 15 * 60


def send_telegram(message):
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN не задан!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=10)
    except Exception as e:
        print(f"Ошибка: {e}")


def get_all_pairs():
    try:
        r = requests.get(f"{BASE_URL}/currencyPairs.do", timeout=10)
        data = r.json()
        if data.get("result") == "true":
            return data["data"]
    except Exception as e:
        print(f"Ошибка: {e}")
    return []


def get_candles(symbol, size=96):
    try:
        params = {"symbol": symbol, "type": "minute15", "size": size}
        r = requests.get(f"{BASE_URL}/kline.do", params=params, timeout=10)
        data = r.json()
        if data.get("result") == "true":
            return data["data"]
    except Exception:
        pass
    return []


def get_orderbook_volume(symbol):
    try:
        params = {"symbol": symbol, "size": 10}
        r = requests.get(f"{BASE_URL}/depth.do", params=params, timeout=10)
        data = r.json()
        if data.get("result") == "true":
            depth = data["data"]
            volumes = []
            for price, qty in depth.get("asks", [])[:5]:
                volumes.append(float(price) * float(qty))
            for price, qty in depth.get("bids", [])[:5]:
                volumes.append(float(price) * float(qty))
            if volumes:
                return statistics.mean(volumes)
    except Exception:
        pass
    return 0


def find_flat_channel(candles, min_range_pct=3.0, min_touches=3):
    if len(candles) < 20:
        return None
    highs = [float(c[2]) for c in candles]
    lows = [float(c[3]) for c in candles]
    closes = [float(c[4]) for c in candles]
    resistance = max(highs)
    support = min(lows)
    if support == 0:
        return None
    channel_pct = (resistance - support) / support * 100
    if channel_pct < min_range_pct:
        return None
    recent = closes[-20:]
    if recent[-1] > recent[0] * 1.05:
        return None
    if recent[-1] < recent[0] * 0.95:
        return None
    touch_zone = channel_pct * 0.01
    res_touches = sum(1 for h in highs if h >= resistance * (1 - touch_zone / 100))
    sup_touches = sum(1 for l in lows if l <= support * (1 + touch_zone / 100))
    if res_touches < min_touches or sup_touches < min_touches:
        return None
    current = closes[-1]
    position = (current - support) / (resistance - support) * 100
    return {
        "support": support,
        "resistance": resistance,
        "channel_pct": round(channel_pct, 2),
        "res_touches": res_touches,
        "sup_touches": sup_touches,
        "current": current,
        "position": round(position, 1),
    }


def scan():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Сканирование...")
    pairs = get_all_pairs()
    usdt_pairs = [p for p in pairs if p.endswith("_usdt")]
    results = []
    for i, symbol in enumerate(usdt_pairs[:300]):
        candles = get_candles(symbol)
        if not candles:
            continue
        channel = find_flat_channel(candles)
        if not channel:
            continue
        vol = get_orderbook_volume(symbol)
        if vol < 100:
            continue
        results.append({"symbol": symbol.upper().replace("_", "/"), **channel, "volume": round(vol, 2)})
        time.sleep(0.15)
    if not results:
        send_telegram("🔍 Сканирование завершено. Флэт-каналов не найдено.")
        return
    results.sort(key=lambda x: x["channel_pct"], reverse=True)
    msg = f"📊 <b>LBank Flat Scanner</b> | {datetime.now().strftime('%H:%M')}\nНайдено пар: {len(results)}\n\n"
    for r in results[:10]:
        if r["position"] < 20:
            pos = "⬇️ у поддержки"
        elif r["position"] > 80:
            pos = "⬆️ у сопротивления"
        else:
            pos = "↔️ в середине"
        msg += f"<b>{r['symbol']}</b> | канал {r['channel_pct']}%\n  Поддержка: {r['support']}\n  Сопротивление: {r['resistance']}\n  Цена: {r['current']} ({pos})\n  Объём стакана: ~${r['volume']}\n\n"
    send_telegram(msg)


def main():
    send_telegram("🚀 LBank Scanner запущен!")
    while True:
        try:
            scan()
        except Exception as e:
            send_telegram(f"⚠️ Ошибка: {e}")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
