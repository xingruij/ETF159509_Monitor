#!/usr/bin/env python3
"""Hourly ETF premium threshold monitor. Eastmoney f402 interpretation must be verified by user."""
import argparse
import json
import os
import sys
from email.header import Header
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "state.json"


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


def fetch_quote(config):
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": "f2,f12,f13,f14,f18,f402",
        "secids": config.get("secid", "0.159509"),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
        "Accept": "application/json,text/plain,*/*",
    }
    timeout = int(config.get("api_timeout_seconds", 15))
    errors = []
    for base in config.get("quote_base_urls", []):
        url = base.rstrip("/") + "/api/qt/ulist.np/get"
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") or {}
            diff = data.get("diff")
            if isinstance(diff, list):
                item = next((x for x in diff if str(x.get("f12", "")) == str(config.get("expected_code", "159509"))), None)
            elif isinstance(diff, dict):
                item = diff
            else:
                item = None
            if not item:
                raise RuntimeError("响应中没有目标 ETF 的 data.diff 项")
            if str(item.get("f12", "")) != str(config.get("expected_code", "159509")):
                raise RuntimeError(f"代码不匹配：f12={item.get('f12')!r}")
            name = str(item.get("f14", ""))
            expected = str(config.get("expected_name_contains", "纳指科技"))
            if expected and expected not in name:
                raise RuntimeError(f"名称不匹配：f14={name!r}，期望包含 {expected!r}；请核验接口后再修改配置")
            return payload, item, url
        except Exception as exc:
            errors.append(f"{base}: {type(exc).__name__}: {exc}")
    raise RuntimeError("所有行情接口均失败：\n" + "\n".join(errors))


def as_number(value, label):
    if value is None or value == "" or value == "-":
        raise RuntimeError(f"行情字段 {label} 为空或不可用：{value!r}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"行情字段 {label} 不是数字：{value!r}") from exc


def publish_ntfy(topic, title, message, priority="default"):
    if not topic:
        raise RuntimeError("未设置 NTFY_TOPIC secret")
    # Topic is deliberately not logged.
    response = requests.post(
        "https://ntfy.sh/" + topic,
        data=message.encode("utf-8"),
        headers={"Title": Header(title, "utf-8").encode(), "Priority": priority, "Tags": "chart_decreasing"},
        timeout=20,
    )
    response.raise_for_status()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostics", action="store_true", help="print raw quote JSON and interpreted fields")
    parser.add_argument("--test-notify", action="store_true", help="send a test notification only")
    args = parser.parse_args()

    config = load_json(CONFIG_PATH, {})
    if args.test_notify:
        publish_ntfy(os.getenv("NTFY_TOPIC", ""), "159509 提醒测试", "ntfy 测试成功。若你收到这条通知，推送链路可用。")
        print("NTFY_TEST_SENT (topic redacted)")
        return 0

    threshold = float(config.get("threshold_pct", 10.0))
    if not -100 <= threshold <= 1000:
        raise RuntimeError(f"阈值异常：{threshold}，请检查 config.json")
    payload, item, source_url = fetch_quote(config)
    price = as_number(item.get(config.get("price_field", "f2")), config.get("price_field", "f2"))
    raw_premium = as_number(item.get(config.get("premium_field", "f402")), config.get("premium_field", "f402"))
    premium = raw_premium * float(config.get("premium_sign", -1))
    name = str(item.get("f14", "景顺纳指科技ETF"))
    code = str(item.get("f12", "159509"))
    now = utc_now()

    if args.diagnostics:
        print("SOURCE_URL:", source_url)
        print("RAW_QUOTE_JSON:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("INTERPRETED:")
        print(json.dumps({
            "code": code,
            "name": name,
            "price_field": config.get("price_field", "f2"),
            "price": price,
            "premium_field": config.get("premium_field", "f402"),
            "raw_premium_field_value": raw_premium,
            "premium_sign": config.get("premium_sign", -1),
            "interpreted_premium_pct": premium,
            "threshold_pct": threshold,
            "note": "请在交易时段与券商行情同一时刻核验；不要只凭字段名称认定准确。"
        }, ensure_ascii=False, indent=2))
        return 0

    state = load_json(STATE_PATH, {"armed": True})
    state.setdefault("armed", True)
    state["last_premium_pct"] = round(premium, 6)
    state["last_price"] = price
    state["last_seen_at_utc"] = now

    if premium >= threshold:
        state["armed"] = True
        print(f"REARMED_OR_ARMED premium={premium:.4f}% threshold={threshold:.4f}%")
    elif state.get("armed", True):
        message = (
            f"{name}（{code}）溢价率已跌破阈值\n"
            f"当前溢价率：{premium:.2f}%\n"
            f"阈值：{threshold:.2f}%\n"
            f"场内价格：{price:.3f}\n"
            f"时间（UTC）：{now}\n"
            "本次区间仅提醒一次；溢价率恢复到阈值或以上后会重新布防。"
        )
        publish_ntfy(os.getenv("NTFY_TOPIC", ""), "159509 溢价率跌破阈值", message, priority="high")
        state["armed"] = False
        state["last_alert_at_utc"] = now
        state["last_alert_premium_pct"] = round(premium, 6)
        print(f"ALERT_SENT premium={premium:.4f}% threshold={threshold:.4f}% (topic redacted)")
    else:
        print(f"ALREADY_ALERTED premium={premium:.4f}% threshold={threshold:.4f}% (not sending duplicate)")

    save_json(STATE_PATH, state)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
