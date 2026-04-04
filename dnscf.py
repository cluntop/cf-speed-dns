#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import traceback
import time
import os

import requests

# API 配置
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_ZONE_ID = os.environ.get("CF_ZONE_ID")
CF_DNS_NAME = os.environ.get("CF_DNS_NAME")
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN")

# 默认超时时间（秒）
DEFAULT_TIMEOUT = 30

# 创建全局 Session 以复用 TCP/TLS 连接 [1, Section: "Advanced Usage" - "Session Objects"]
session = requests.Session()
session.headers.update({
    'Authorization': f'Bearer {CF_API_TOKEN}',
    'Content-Type': 'application/json'
})


def get_cf_speed_test_ip(timeout=10, max_retries=5):

    for attempt in range(max_retries):
        try:
            # 使用 session 复用连接 [1, Section: "Advanced Usage" - "Session Objects"]
            response = session.get(
                'https://ip.164746.xyz/ipTop.html',
                timeout=timeout
            )
            if response.status_code == 200:
                return response.text
        except Exception as e:
            print(f"获取优选 IP 失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                traceback.print_exc()
    return None


def get_dns_records(name):

    records = []
    url = f'https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records'

    # 采用 API 侧过滤和分页 [2, Section: "DNS Records for a Zone" - "List DNS Records"]
    params = {
        'name': name,
        'type': 'A',
        'per_page': 100  # [2, Section: "Fundamentals" - "Pagination"]
    }

    try:
        response = session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        if response.status_code == 200:
            result = response.json().get('result', [])
            for record in result:
                records.append({
                    'id': record['id'],
                    'content': record.get('content', '')
                })
        else:
            print(f'获取 DNS 记录失败: {response.text}')
    except Exception as e:
        print(f'获取 DNS 记录异常: {e}')
        traceback.print_exc()

    return records


def update_dns_record(record_info, name, cf_ip):

    record_id = record_info['id']
    current_ip = record_info.get('content', '')

    # 如果 IP 相同则跳过更新
    if current_ip == cf_ip:
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        print(f"cf_dns_change skip: ---- Time: {current_time} ---- ip：{cf_ip} (已是最新)")
        return f"ip:{cf_ip} 解析 {name} 跳过 (已是最新)"

    url = f'https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records/{record_id}'
    data = {
        'type': 'A',
        'name': name,
        'content': cf_ip,
        'ttl': 1
    }

    try:
        # 使用 session 提交数据 [1, Section: "Advanced Usage" - "Session Objects"]
        response = session.put(url, json=data, timeout=DEFAULT_TIMEOUT)
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        if response.status_code == 200:
            print(f"cf_dns_change success: ---- Time: {current_time} ---- ip：{cf_ip}")
            return f"ip:{cf_ip} 解析 {name} 成功"
        else:
            print(f"cf_dns_change ERROR: ---- Time: {current_time} ---- MESSAGE: {response.text}")
            return f"ip:{cf_ip} 解析 {name} 失败"
    except Exception as e:
        traceback.print_exc()
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        print(f"cf_dns_change ERROR: ---- Time: {current_time} ---- MESSAGE: {e}")
        return f"ip:{cf_ip} 解析 {name} 失败"


def push_plus(content):

    if not PUSHPLUS_TOKEN:
        print("PUSHPLUS_TOKEN 未设置，跳过消息推送")
        return

    url = 'http://www.pushplus.plus/send'
    data = {
        "token": PUSHPLUS_TOKEN,
        "title": "IP优选DNSCF推送",
        "content": content,
        "template": "markdown",
        "channel": "wechat"
    }

    try:
        # 简化 JSON 序列化 [1, Section: "Developer Interface" - "More complicated POST requests"]
        session.post(url, json=data, timeout=DEFAULT_TIMEOUT)
    except Exception as e:
        print(f"消息推送失败: {e}")


def main():

    # 检查必要的环境变量
    if not all([CF_API_TOKEN, CF_ZONE_ID, CF_DNS_NAME]):
        print("错误: 缺少必要的环境变量 (CF_API_TOKEN, CF_ZONE_ID, CF_DNS_NAME)")
        return

    # 获取最新优选 IP
    ip_addresses_str = get_cf_speed_test_ip()
    if not ip_addresses_str:
        print("错误: 无法获取优选 IP")
        return
        
    raw_ips = []

        raw_ips = [ip.strip() for ip in ip_addresses_str.split(',') if ip.strip()]
    # 利用字典键的唯一性进行去重，并保持原有的优选 IP 排序
    ip_addresses = list(dict.fromkeys(raw_ips)) 

    if not ip_addresses:
        print("错误: 未解析到有效 IP 地址")
        return

    # 获取 DNS 记录
    dns_records = get_dns_records(CF_DNS_NAME)
    if not dns_records:
        print(f"错误: 未找到 {CF_DNS_NAME} 的 DNS 记录")
        return

    # 检查记录数量是否足够
    if len(ip_addresses) > len(dns_records):
        print(f"警告: IP 数量({len(ip_addresses)})超过 DNS 记录数量({len(dns_records)})，只更新前 {len(dns_records)} 个")
        ip_addresses = ip_addresses[:len(dns_records)]

    # 更新 DNS 记录
    push_plus_content = []
    for index, ip_address in enumerate(ip_addresses):
        dns = update_dns_record(dns_records[index], CF_DNS_NAME, ip_address)
        push_plus_content.append(dns)

    # 发送推送
    if push_plus_content:
        push_plus('\n'.join(push_plus_content))


if __name__ == '__main__':
    main()