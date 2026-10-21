#!/usr/bin/env python3
"""Read only LAN INFO; never open a control session or submit an image."""
import argparse
import json
import socket
import struct


def info(target):
    host, _, port = target.partition(':')
    socket.inet_pton(socket.AF_INET, host)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(3)
        sock.connect((host, int(port or 32342)))
        sock.send(b'ZL\x01\x01' + struct.pack('>QI', 0, 1))
        packet = sock.recv(1200)
    if len(packet) < 20 or packet[:4] != b'ZL\x01\x81' or packet[12:16] != struct.pack('>I', 1):
        raise ValueError('无效 INFO 响应')
    body = packet[16:]
    if body[0] != 0:
        raise ValueError('设备拒绝 INFO 请求')
    n = body[2]
    if len(body) < 4+n:
        raise ValueError('截断的 INFO 响应')
    device_id = body[3:3+n].decode('utf-8')
    m = body[3+n]
    if len(body) != 4+n+m+12:
        raise ValueError('截断的 INFO 字段')
    name = body[4+n:4+n+m].decode('utf-8')
    canvas = struct.unpack('>HHHHHH', body[4+n+m:])
    return {'id': device_id, 'name': name, 'busy': bool(body[1]),
            'width': canvas[0], 'height': canvas[1], 'canvas_fields': list(canvas)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', help='NOTE4 IPv4 或 IPv4:端口')
    args = parser.parse_args()
    try:
        print(json.dumps(info(args.target), ensure_ascii=False, indent=2))
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(1, f'设备查询失败：{exc}\n')
