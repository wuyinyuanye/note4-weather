"""NOTE4 3.7.2 local weather application: pages, scheduling, and persistent SDK session."""
from __future__ import annotations
import argparse
import io
import json
import queue
import signal
import socket
import struct
import subprocess
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from clock_page import HERE, TZ
from weather import WeatherStore
from weather_page import render

DEFAULTS={'city':'南京','latitude':32.06167,'longitude':118.77778,
          'target':'','expected_id':'','weather_interval_seconds':3600}
DATA=Path.home()/'Library/Application Support/ZectrixNote4/weather-app'
PAGES=('home','details')
BRIDGE=HERE/'bridge/target/debug/note4-weather-bridge'


def probe(target, expected_id):
    """Read-only INFO, verify identity/canvas BEFORE taking device ownership."""
    if not target or not expected_id or expected_id == 'YOUR_DEVICE_ID':
        raise ValueError('请先在 config.json 中填写自己的 target 和 expected_id')
    host,_,port=target.partition(':')
    socket.inet_aton(host)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.settimeout(3);sock.connect((host,int(port or 32342)))
        sock.send(b'ZL\x01\x01'+struct.pack('>QI',0,1))
        packet=sock.recv(1200)
    if len(packet)<20 or packet[:4]!=b'ZL\x01\x81' or packet[12:16]!=struct.pack('>I',1):
        raise ValueError('设备 INFO 响应无效')
    b=packet[16:]
    if b[0]!=0: raise ValueError('设备 INFO 请求失败')
    n=b[2];device_id=b[3:3+n].decode();m=b[3+n]
    dimensions=b[4+n+m:]
    if device_id.lower()!=expected_id.lower(): raise ValueError('设备身份不匹配，取消连接')
    if dimensions!=bytes([1,144,1,44,0,0,0,0,0,0,0,0]): raise ValueError('设备不支持完整画布')
    if b[1]: raise ValueError('设备正在其他会话中')
    return device_id


class App:
    def __init__(self, config, directory=DATA):
        self.config=config;self.directory=directory;directory.mkdir(parents=True,exist_ok=True)
        self.store=WeatherStore(config,directory)
        self.events=queue.Queue(maxsize=64)
        self.lock=threading.RLock();self.stop=threading.Event()
        self.page='home';self.process=None
        self.connection='未连接';self.error=None;self.palette=None;self.palette4=None;self.device=None;self.telemetry=None
        self.recording=False;self.blocked=False;self.inflight=None;self.pending=False
        self.generation=0;self.displayed=None;self.display_count=0;self.displayed_page=None
        self.last_render=None;self.last_fetch=0;self.last_status=0;self.fetching=False;self.initial_connect=False
        self.preview=b'';self.last_event=None;self.revision=0
        self.load_telemetry()
        # Preserve the hourly fetch cadence across local app restarts.
        if self.store.snapshot:
            try:
                age=(datetime.now(TZ)-datetime.fromisoformat(self.store.snapshot['fetched_at'])).total_seconds()
                if 0<=age<self.config['weather_interval_seconds']:
                    self.last_fetch=time.monotonic()-age
            except (ValueError,TypeError,KeyError): pass
        self.render()

    def load_telemetry(self):
        try:
            saved=json.loads((self.directory/'device-status.json').read_text())
            recorded=datetime.fromisoformat(saved['recorded_at'])
            age=(datetime.now(TZ)-recorded).total_seconds()
            status=saved['status'];percent=status.get('battery_percent')
            valid=percent is None or (type(percent) is int and 0<=percent<=100)
            if saved.get('expected_id')==self.config['expected_id'] and -30<=age<=7200 and valid:
                self.telemetry=status
        except (OSError,ValueError,KeyError,TypeError,AttributeError): pass

    def render(self, now=None, force=False, reason='page'):

        now=now or datetime.now(TZ)
        snapshot,freshness=self.store.view(now)
        image=render(now,snapshot,freshness,self.page,self.config['city'],home_frame=self.config.get('home_frame',True),status=self.telemetry)
        output=io.BytesIO();image.save(output,format='PNG');png=output.getvalue()
        self.last_render=now.strftime('%Y-%m-%dT%H:%M')
        if png==self.preview and not force: return
        self.preview=png;self.revision+=1;self.pending_reason=reason
        temporary=self.directory/'preview.tmp';temporary.write_bytes(self.preview);temporary.replace(self.directory/'preview.png')
        self.pending=True;self.dispatch()

    def tick(self, now=None, monotonic_now=None):
        now=now or datetime.now(TZ)
        monotonic_now=time.monotonic() if monotonic_now is None else monotonic_now
        if monotonic_now-self.last_fetch>=self.config['weather_interval_seconds']: self.fetch()
        if self.last_render and now.date().isoformat()!=self.last_render[:10]:
            self.render(now=now,reason='date')

    def send(self, value):
        if self.process and self.process.poll() is None:
            try:
                self.process.stdin.write(json.dumps(value)+'\n');self.process.stdin.flush()
            except (BrokenPipeError,OSError): self.connection='连接已结束';self.pending=False

    def dispatch(self):
        if self.connection!='已连接' or self.inflight is not None or self.recording or self.blocked or not self.pending: return
        self.generation+=1
        path=self.directory/'inflight.png';path.write_bytes(self.preview)
        self.inflight=self.generation;self.inflight_page=self.page;self.inflight_reason=self.pending_reason;self.pending=False
        self.send({'command':'show','id':self.inflight,'path':str(path)})

    def fetch(self):
        if self.fetching: return
        self.fetching=True;self.last_fetch=time.monotonic()
        def worker():
            # Store is only swapped on the application loop.
            store=WeatherStore(self.config,self.directory)
            success=store.update()
            self.events.put(('weather',(store,success)))
        threading.Thread(target=worker,daemon=True).start()

    def connect(self):
        if self.process and self.process.poll() is None: return
        self.connection='正在连接';self.error=None;self.blocked=False;self.recording=False;self.inflight=None
        try:
            probe(self.config['target'],self.config['expected_id'])
            initial=self.directory/'initial.png';initial.write_bytes(self.preview)
            log=(self.directory/'bridge.stderr.log').open('a')
            self.process=subprocess.Popen([str(BRIDGE),self.config['target'],self.config['expected_id'],str(initial)],
                                          stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
            log.close()
            process=self.process
            self.inflight=0;self.inflight_page=self.page;self.inflight_reason='connect';self.pending=False
            def reader():
                for line in process.stdout:
                    try: self.events.put(('bridge',json.loads(line)))
                    except ValueError: pass
                code=process.wait();self.events.put(('ended',(process,code)))
            threading.Thread(target=reader,daemon=True).start()
        except Exception as exc:
            self.connection='连接失败';self.error=('设备未响应，请唤醒设备并开启“待机保持 Wi-Fi”' if isinstance(exc,TimeoutError) else str(exc))

    def disconnect(self):
        self.send({'command':'close'})
        self.connection='正在关闭';self.pending=False;self.initial_connect=False

    def action(self, action):
        if action in PAGES:
            self.page=action;self.render()
        elif action in ('up','down'):
            self.page=PAGES[(PAGES.index(self.page)+(-1 if action=='up' else 1))%len(PAGES)];self.render()
        elif action=='confirm':
            self.page='details' if self.page=='home' else 'home'
            self.render()
        elif action=='refresh': self.fetch()
        elif action=='connect': self.connect()
        elif action=='disconnect': self.disconnect()
        elif action=='retry_display':
            self.blocked=False;self.error=None;self.render(force=True)

    def bridge_event(self, event):
        kind=event.get('event');self.last_event=kind
        if kind=='connected':
            self.connection='已连接';self.device=event['device'];self.palette=event['gray16'];self.palette4=event.get('gray4');self.last_status=0
        elif kind=='displayed':
            self.displayed=datetime.now(TZ).isoformat();self.display_count+=1;self.displayed_page=self.inflight_page
            self.last_display_reason=getattr(self,'inflight_reason','unknown')
            receipt={'displayed_at':self.displayed,'page':self.displayed_page,'reason':getattr(self,'inflight_reason','unknown'),'target':self.config['target'],
                     'device_id':self.device['id'] if self.device else None,'format':'Gray16',
                     'gray16':self.palette,'wire_format':'Gray16','meaning':'SDK reported display complete; visual acceptance pending'}
            (self.directory/'last-display.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
            with (self.directory/'display-history.jsonl').open('a') as history:
                history.write(json.dumps(receipt,ensure_ascii=False)+'\n')
            self.inflight=None;self.error=None;self.dispatch()
        elif kind=='display_error':
            self.inflight=None;self.error=event['error']
            # ResultUnknown/transport errors latch until an explicit user action.
            self.blocked=event.get('kind')!='Busy'
            if not self.blocked: self.pending=True
        elif kind=='key':
            if event.get('action')=='Short': self.action({'Up':'up','Down':'down','Confirm':'confirm'}[event['key']])
            elif event.get('key') in ('Up','Down'): self.action('home' if event['key']=='Up' else 'details')
        elif kind=='recording_started': self.recording=True
        elif kind=='recording_finished':
            self.recording=False;self.dispatch()
        elif kind=='status':
            # Cache telemetry only. A Gray16 image must never be submitted by a
            # battery/charging/RSSI poll, even when those readings change.
            self.telemetry=event['status']
            cached={'expected_id':self.config['expected_id'],'recorded_at':datetime.now(TZ).isoformat(),'status':self.telemetry}
            (self.directory/'device-status.json').write_text(json.dumps(cached,ensure_ascii=False))
        elif kind=='disconnected':
            self.connection='连接已结束';self.error=event.get('reason',event.get('error'));self.blocked=True;self.inflight=None
            self.send({'command':'close'})

    def state(self):
        with self.lock:
            snapshot,freshness=self.store.view()
            return {'city':self.config['city'],'page':self.page,'connection':self.connection,'target':self.config['target'],
                    'device':self.device,'gray16':self.palette,'gray4':self.palette4,'clock_visible':False,'status':self.telemetry,'weather':snapshot,
                    'freshness':freshness,'weather_error':self.store.error,'error':self.error,'recording':self.recording,
                    'display_blocked':self.blocked,'displayed_at':self.displayed,'display_count':self.display_count,
                    'displayed_page':self.displayed_page,'inflight':self.inflight,'fetching':self.fetching,'last_event':self.last_event,'revision':self.revision,'weather_interval_seconds':self.config['weather_interval_seconds'],'battery_refresh':'with_weather_or_navigation','last_display_reason':getattr(self,'last_display_reason',None)}

    def run(self):
        while not self.stop.is_set():
            try: kind,value=self.events.get(timeout=0.4)
            except queue.Empty: kind,value=None,None
            with self.lock:
                try:
                    if kind=='action': self.action(value)
                    elif kind=='weather':
                        self.store,success=value;self.fetching=False
                        self.render(reason='weather')
                        if self.initial_connect:
                            self.initial_connect=False;self.connect()
                    elif kind=='bridge': self.bridge_event(value)
                    elif kind=='ended' and value[0] is self.process:
                        self.connection='已断开';self.inflight=None;self.pending=False;self.recording=False
                        if value[1]: self.error=f'SDK 进程退出（{value[1]}），查看本地日志'
                    self.tick()
                    if self.initial_connect and not self.fetching:
                        self.initial_connect=False;self.connect()
                    if self.connection=='已连接' and self.inflight is None and time.monotonic()-self.last_status>=60:
                        self.last_status=time.monotonic();self.send({'command':'status'})
                except Exception as exc:
                    self.error=str(exc)
        self.send({'command':'close'})
        if self.process:
            try: self.process.wait(timeout=4)
            except subprocess.TimeoutExpired: self.process.terminate()


class Server(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True


def handler(app, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,code,body,mime):
            self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def trusted(self): return self.headers.get('Host') in (f'127.0.0.1:{port}',f'localhost:{port}')
        def do_GET(self):
            if not self.trusted(): return self.reply(403,b'Forbidden','text/plain')
            path=urlsplit(self.path).path
            if path=='/': return self.reply(200,(HERE/'index.html').read_bytes(),'text/html; charset=utf-8')
            if path=='/api/state': return self.reply(200,json.dumps(app.state(),ensure_ascii=False).encode(),'application/json; charset=utf-8')
            if path=='/preview.png':
                with app.lock: image=app.preview
                return self.reply(200,image,'image/png')
            return self.reply(404,b'Not found','text/plain')
        def do_POST(self):
            if not self.trusted(): return self.reply(403,b'Forbidden','text/plain')
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{port}',f'http://localhost:{port}'):
                return self.reply(403,b'Forbidden','text/plain')
            if self.path!='/api/action' or self.headers.get('Content-Type')!='application/json':
                return self.reply(400,b'Invalid request','text/plain')
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<1024: raise ValueError()
                action=json.loads(self.rfile.read(length))['action']
                if action not in (*PAGES,'up','down','confirm','refresh','connect','disconnect','retry_display'): raise ValueError()
                app.events.put_nowait(('action',action))
            except (ValueError,KeyError,TypeError,queue.Full): return self.reply(400,b'Invalid action','text/plain')
            self.reply(202,b'{"accepted":true}','application/json')
    return Handler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=18772);parser.add_argument('--connect',action='store_true')
    parser.add_argument('--config',type=Path);parser.add_argument('--data-dir',type=Path,default=DATA)
    args=parser.parse_args();config=DEFAULTS.copy()
    config_path=args.config or args.data_dir/'config.json'
    if config_path.exists(): config.update(json.loads(config_path.read_text()))
    if config['weather_interval_seconds']<60: parser.error('天气取数间隔至少60秒')
    app=App(config,args.data_dir)
    # Bind first: a second instance fails without taking another SDK session.
    server=Server(('127.0.0.1',args.port),handler(app,args.port))
    app.initial_connect=args.connect
    thread=threading.Thread(target=app.run,daemon=True);thread.start()
    def shutdown(*_): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,shutdown)
    print(f'NOTE4 {config["city"]}天气：http://127.0.0.1:{args.port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close();app.stop.set();thread.join(timeout=6)


if __name__=='__main__': main()
