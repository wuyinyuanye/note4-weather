"""Public weather-only API and read-only device discovery regression checks."""
import json
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from app import App, DEFAULTS, Server, handler
from scripts.device_info import info


class PublicReleaseTests(unittest.TestCase):
    def test_placeholder_configuration_never_touches_network(self):
        with tempfile.TemporaryDirectory() as d:
            config = json.loads((Path(__file__).parent/'config.example.json').read_text())
            app = App(config, Path(d))
            with patch('app.socket.socket') as udp, patch('app.subprocess.Popen') as process:
                app.connect()
                udp.assert_not_called()
                process.assert_not_called()
                self.assertIn('config.json', app.error)

    def test_long_keys_select_weather_pages_only(self):
        with tempfile.TemporaryDirectory() as d:
            app = App(DEFAULTS, Path(d))
            app.bridge_event({'event': 'key', 'key': 'Down', 'action': 'Long'})
            self.assertEqual(app.page, 'details')
            app.bridge_event({'event': 'key', 'key': 'Up', 'action': 'Long'})
            self.assertEqual(app.page, 'home')
            self.assertNotIn('album', app.state())

    def test_weather_only_http_routes_and_origin_guard(self):
        with tempfile.TemporaryDirectory() as d:
            app = App(DEFAULTS, Path(d))
            server = Server(('127.0.0.1', 0), handler(app, 0))
            port = server.server_address[1]
            server.RequestHandlerClass = handler(app, port)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{port}'
            try:
                with urlopen(base+'/', timeout=2) as response:
                    html = response.read().decode()
                    self.assertNotIn('相册', html)
                    self.assertNotIn('/api/album', html)
                with self.assertRaises(HTTPError) as error:
                    urlopen(base+'/album/photo/example', timeout=2)
                self.assertEqual(error.exception.code, 404)
                error.exception.close()
                for path, body, headers, status in [
                    ('/api/album/upload', b'photo', {'Content-Type':'application/octet-stream'}, 400),
                    ('/api/action', b'{"action":"album"}', {'Content-Type':'application/json'}, 400),
                    ('/api/action', b'{"action":"connect"}', {'Content-Type':'application/json','Origin':'https://example.com'}, 403),
                ]:
                    with self.assertRaises(HTTPError) as error:
                        urlopen(Request(base+path, data=body, headers=headers), timeout=2)
                    self.assertEqual(error.exception.code, status)
                    error.exception.close()
                self.assertTrue(app.events.empty())
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_device_info_queries_without_opening_session(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.bind(('127.0.0.1',0));udp.settimeout(2)
            received = []
            def reply():
                packet, address = udp.recvfrom(1024); received.append(packet)
                identity = b'000000000001';name = b'NOTE4 demo'
                body = bytes([0,0,len(identity)])+identity+bytes([len(name)])+name+struct.pack('>HHHHHH',400,300,0,0,0,0)
                udp.sendto(b'ZL\x01\x81'+struct.pack('>QI',0,1)+body,address)
            thread = threading.Thread(target=reply);thread.start()
            result = info(f'127.0.0.1:{udp.getsockname()[1]}');thread.join()
            self.assertEqual(result['id'],'000000000001')
            self.assertEqual((result['width'],result['height']),(400,300))
            self.assertEqual(received,[b'ZL\x01\x01'+struct.pack('>QI',0,1)])


if __name__ == '__main__':
    unittest.main()
