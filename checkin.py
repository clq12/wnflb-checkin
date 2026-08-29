#!/usr/bin/env python3
"""
福利吧论坛 (wnflb2023.com) 自动签到脚本
- 使用 Cookies 认证，无需浏览器
- 自动检测登录状态和签到状态
- 支持 PushPlus / Server酱 微信推送通知
- 早上9点签到 + 晚上10点复查
"""

import os
import re
import sys
import time
import requests
from datetime import datetime, timezone, timedelta

# ========== 配置 ==========
FORUM_URL = "https://www.wnflb2023.com/forum.php"
BASE_URL = "https://www.wnflb2023.com"
TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


# ========== 工具函数 ==========

def get_cst_time():
    utc_now = datetime.now(timezone.utc)
    return (utc_now + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")


def parse_cookies(raw):
    """将 Cookie 字符串解析为字典"""
    cookies = {}
    for item in raw.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def create_session(cookie_str):
    """创建会话，用 session.cookies 设置 Cookie（非 header）"""
    session = requests.Session()
    session.headers.update(HEADERS)
    cookies = parse_cookies(cookie_str)
    session.cookies.update(cookies)
    return session


def fetch_forum(session):
    """访问论坛首页，让服务器返回最新 sid 等 cookie"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(FORUM_URL, timeout=TIMEOUT)
            return resp
        except requests.RequestException as e:
            print(f"  第 {attempt}/{MAX_RETRIES} 次请求失败: {e}")
            if attempt < MAX_RETRIES:
                print(f"  {RETRY_DELAY} 秒后重试...")
                time.sleep(RETRY_DELAY)
    return None


def get_page_text(resp):
    """获取页面文本，优先检测 GBK 编码"""
    if resp.encoding and resp.encoding.lower() in ("gbk", "gb2312", "gb18030"):
        return resp.text
    try:
        return resp.content.decode("gbk")
    except (UnicodeDecodeError, LookupError):
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text


def check_logged_in(html):
    """检测是否已登录"""
    # 登录标志
    logged_signs = [
        'class="logout"',
        "退出</a>",
        "退出登录",
        "mod=logging&action=logout",
        "fx_checkin",  # 签到插件只有登录后显示
    ]
    if any(s in html for s in logged_signs):
        return True

    # 明确未登录标志
    not_logged_signs = [
        'name="username"',
        'name="password"',
        "action=login",
    ]
    if any(s in html for s in not_logged_signs):
        return False

    return True  # 默认假设已登录


def check_already_signed(html):
    """检测今日是否已签到"""
    match = re.search(r"fx_chk_menu\s*=\s*(true|false)", html)
    if match:
        return match.group(1) == "true"
    return False


def extract_formhash(html):
    """提取签到所需的 formhash"""
    match = re.search(
        r"fx_checkin:checkin&formhash=([a-f0-9]+)&([a-f0-9]+)", html
    )
    if match:
        return match.group(1), match.group(2)
    return None, None


def do_checkin(session, formhash, fx_formhash):
    """执行签到请求"""
    url = (
        f"{BASE_URL}/plugin.php?id=fx_checkin:checkin"
        f"&formhash={formhash}&{fx_formhash}&inajax=1"
    )
    headers = {
        "Referer": FORUM_URL,
        "X-Requested-With": "XMLHttpRequest",
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=TIMEOUT, headers=headers)
            return resp.text
        except requests.RequestException as e:
            print(f"  第 {attempt}/{MAX_RETRIES} 次请求失败: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    return None


def parse_result(text):
    """解析签到结果"""
    if text is None:
        return False, "网络请求失败"

    # 检查 CDATA
    cdata_match = re.search(r"<!\[CDATA\[(.*?)\]\]>", text, re.DOTALL)
    content = cdata_match.group(1) if cdata_match else text

    # 去除 HTML 标签
    clean = re.sub(r"<[^>]+>", " ", content).strip()
    clean = re.sub(r"\s+", " ", clean)

    if "签到成功" in clean:
        rank = re.search(r"第\s*(\d+)\s*个", clean)
        if rank:
            return True, f"签到成功！今日第 {rank.group(1)} 个签到"
        return True, "签到成功！"

    if "已经签到" in clean or "已签到" in clean:
        return True, "今日已签到（重复签到）"

    if "先登录" in clean or "请登录" in clean:
        return False, "Cookie 已过期，请重新获取"

    if "补签" in clean and "成功" in clean:
        return True, "补签成功"

    return False, f"未知响应: {clean[:200]}"


def send_notification(title, content):
    """发送微信通知"""
    token = os.environ.get("PUSHPLUS_TOKEN", "")
    if token:
        try:
            resp = requests.post(
                "http://www.pushplus.plus/send",
                json={"token": token, "title": title, "content": content, "template": "txt"},
                timeout=10,
            )
            print(f"  [PushPlus] {resp.json().get('msg', 'unknown')}")
        except Exception as e:
            print(f"  [PushPlus] 发送失败: {e}")

    key = os.environ.get("SERVERCHAN_KEY", "")
    if key:
        try:
            resp = requests.post(
                f"https://sctapi.ftqq.com/{key}.send",
                data={"title": title, "desp": content},
                timeout=10,
            )
            print(f"  [Server酱] {resp.json().get('message', 'unknown')}")
        except Exception as e:
            print(f"  [Server酱] 发送失败: {e}")

    if not token and not key:
        print("  (未配置推送通知)")


# ========== 主流程 ==========

def main():
    cookie_str = os.environ.get("FORUM_COOKIE", "")
    mode = os.environ.get("CHECKIN_MODE", "checkin")
    now = get_cst_time()

    print("=" * 50)
    print("  福利吧论坛自动签到")
    print(f"  模式: {'早起签到' if mode == 'checkin' else '晚间复查'}")
    print(f"  时间: {now}")
    print("=" * 50)
    print()

    if not cookie_str:
        print("[FATAL] 未设置 FORUM_COOKIE 环境变量")
        sys.exit(1)

    # Step 1: 创建会话
    print("[1/4] 创建会话并访问论坛...")
    session = create_session(cookie_str)
    resp = fetch_forum(session)

    if resp is None:
        msg = "访问论坛失败（网络错误）"
        print(f"[FAIL] {msg}")
        send_notification(f"[签到失败] {mode}", f"时间: {now}\n模式: {mode}\n错误: {msg}")
        sys.exit(1)

    html = get_page_text(resp)

    # Step 2: 检查登录
    print("[2/4] 检查登录状态...")
    if not check_logged_in(html):
        msg = "Cookie 已过期，请重新获取并更新 GitHub Secrets"
        print(f"[FAIL] {msg}")
        send_notification(f"[签到失败] Cookie过期", f"时间: {now}\n模式: {mode}\n错误: {msg}")
        sys.exit(1)
    print("  -> 登录状态正常")

    # Step 3: 检查签到状态
    print("[3/4] 检查签到状态...")
    if check_already_signed(html):
        print("[OK] 今日已签到，无需重复操作（成功不推送）")
        sys.exit(0)
    print("  -> 今日尚未签到")

    # Step 4: 执行签到
    print("[4/4] 提取 formhash 并执行签到...")
    formhash, fx_formhash = extract_formhash(html)

    if not formhash:
        msg = "无法提取 formhash，页面结构可能已变化"
        print(f"[FAIL] {msg}")
        send_notification(f"[签到失败] {mode}", f"时间: {now}\n模式: {mode}\n错误: {msg}")
        sys.exit(1)

    print(f"  -> formhash: {formhash}")
    print(f"  -> fx_formhash: {fx_formhash}")

    text = do_checkin(session, formhash, fx_formhash)
    success, message = parse_result(text)

    if success:
        print(f"[OK] {message}（成功不推送）")
    else:
        print(f"[FAIL] {message}")
        send_notification(
            f"[签到失败] {mode}",
            f"时间: {now}\n模式: {mode}\n结果: {message}",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
