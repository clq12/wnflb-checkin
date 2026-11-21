#!/usr/bin/env python3
"""
福利吧论坛 (wnflb2023.com) 自动签到脚本
- 使用 Cookies 认证，无需浏览器
- 自动检测登录状态和签到状态
- 仅签到失败时通过 PushPlus 推送微信通知（成功/已签到不打扰）
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
    logged_signs = [
        'class="logout"',
        "退出</a>",
        "退出登录",
        "mod=logging&action=logout",
        "fx_checkin",
    ]
    if any(s in html for s in logged_signs):
        return True

    not_logged_signs = [
        'name="username"',
        'name="password"',
        "action=login",
    ]
    if any(s in html for s in not_logged_signs):
        return False

    return True


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

    cdata_match = re.search(r"<!\[CDATA\[(.*?)\]\]>", text, re.DOTALL)
    content = cdata_match.group(1) if cdata_match else text

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


# ========== 推送（仅失败时调用） ==========

def send_pushplus(title, content):
    """通过 PushPlus 推送微信通知；只在签到失败时调用"""
    token = os.environ.get("PUSHPLUS_TOKEN", "")
    if not token:
        print("  [PushPlus] 未配置 PUSHPLUS_TOKEN，跳过推送")
        return
    try:
        resp = requests.post(
            "https://www.pushplus.plus/send",
            json={"token": token, "title": title, "content": content, "template": "txt"},
            timeout=15,
        )
        result = resp.json()
        if result.get("code") == 200:
            print("  [PushPlus] 推送成功")
        else:
            print(f"  [PushPlus] 推送返回异常: {result}")
    except Exception as e:
        print(f"  [PushPlus] 推送失败: {e}")


def fail_and_notify(title, reason, now, mode):
    """统一失败出口：打印日志 + PushPlus 推送 + 非零退出"""
    print(f"[FAIL] {reason}")
    send_pushplus(title, f"时间: {now}\n模式: {mode}\n错误: {reason}")
    sys.exit(1)


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
        fail_and_notify("[签到失败] 配置缺失", "未设置 FORUM_COOKIE 环境变量", now, mode)

    # Step 1: 创建会话
    print("[1/4] 创建会话并访问论坛...")
    session = create_session(cookie_str)
    resp = fetch_forum(session)

    if resp is None:
        fail_and_notify("[签到失败] 网络错误", "访问论坛失败（网络错误）", now, mode)

    html = get_page_text(resp)

    # Step 2: 检查登录
    print("[2/4] 检查登录状态...")
    if not check_logged_in(html):
        fail_and_notify(
            "[签到失败] Cookie过期",
            "Cookie 已过期，请重新获取并更新 GitHub Secrets",
            now,
            mode,
        )
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
        fail_and_notify(
            "[签到失败] 页面异常",
            "无法提取 formhash，页面结构可能已变化",
            now,
            mode,
        )

    print(f"  -> formhash: {formhash}")
    print(f"  -> fx_formhash: {fx_formhash}")

    text = do_checkin(session, formhash, fx_formhash)
    success, message = parse_result(text)

    if success:
        print(f"[OK] {message}（成功不推送）")
    else:
        fail_and_notify("[签到失败] 签到未成功", message, now, mode)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        # 任何未捕获异常也推送，避免失败静默
        now = get_cst_time()
        mode = os.environ.get("CHECKIN_MODE", "checkin")
        detail = f"{type(e).__name__}: {e}"
        print(f"[FATAL] 脚本异常: {detail}")
        send_pushplus("[签到失败] 脚本异常", f"时间: {now}\n模式: {mode}\n错误: {detail}")
        sys.exit(1)
