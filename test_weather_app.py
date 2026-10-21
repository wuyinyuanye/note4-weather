import copy
from datetime import datetime,timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from clock_page import TZ
from weather import WeatherStore,parse,CURRENT,HOURLY,DAILY
from weather_page import render,art_name
from app import App,DEFAULTS,probe
DEFAULTS={**DEFAULTS,"target":"192.0.2.10","expected_id":"000000000001"}

NOW=datetime(2026,10,21,16,30,tzinfo=TZ)
def raw():
    return {'current_units':{'temperature_2m':'°C'},'current':{'time':'2026-10-21T16:30',
      **dict(zip(CURRENT.split(','),[17.5,60,17,1,0,1,12]))},
      'hourly':{'time':[f'2026-10-21T{h:02d}:00' for h in range(24)],
        **{k:[18 if k=='temperature_2m' else 1]*24 for k in HOURLY.split(',')}},
      'daily':{'time':[f'2026-10-{d}' for d in range(21,28)],
        **{k:([f'2026-10-21T06:00']*7 if k in ('sunrise','sunset') else [22]*7) for k in DAILY.split(',')}}}

class WeatherTests(unittest.TestCase):
    def test_null_and_old_data_rejected(self):
        data=raw();data['current']['temperature_2m']=None
        with self.assertRaises(ValueError): parse(data,'南京',32,118,NOW)
        with self.assertRaises(ValueError): parse(raw(),'南京',32,118,NOW+timedelta(days=1))
    def test_cache_failure_and_expiry(self):
        with tempfile.TemporaryDirectory() as d:
            store=WeatherStore(DEFAULTS,Path(d),lambda _:raw())
            self.assertTrue(store.update(NOW));original=store.snapshot
            store.fetch=lambda _:(_ for _ in ()).throw(OSError('offline'))
            self.assertFalse(store.update(NOW+timedelta(minutes=15)))
            self.assertIs(store.view(NOW)[0],original);self.assertIn('缓存',store.view(NOW)[1])
            self.assertIsNone(store.view(NOW+timedelta(hours=7))[0])
            self.assertIsNotNone(WeatherStore(DEFAULTS,Path(d)).snapshot)
            changed={**DEFAULTS,'city':'北京'}
            self.assertIsNone(WeatherStore(changed,Path(d)).snapshot)
    def test_pages_and_extreme_temperature_layout(self):
        snap=parse(raw(),'南京',32,118,NOW)
        for temp in (-40,0,99):
            snap['current']['temperature_2m']=temp
            for hour in (0,8,11,23):
                for page in ('home','details'):
                    image=render(NOW.replace(hour=hour),snap,'缓存 16:30',page)
                    self.assertEqual(image.size,(400,300));self.assertEqual(image.mode,'L')
        image=render(NOW,None,'天气已过期')
        self.assertEqual(image.size,(400,300))
    def test_condition_day_night_mapping(self):
        self.assertEqual(art_name(1,1),'original');self.assertEqual(art_name(1,0),'partly-cloudy-night')
        for code in (45,51,63,67,75,82,95,99): self.assertNotEqual(art_name(code,1),'original')
        self.assertIsNone(art_name(999,1))
    def test_icon_system_covers_all_weather_codes_without_mixed_library(self):
        import hashlib
        from weather import CODES
        from weather_page import ICON_ROOT,ICON_SET,artwork
        for code in CODES:
            for day in (0,1):
                name=art_name(code,day)
                self.assertIn(name,ICON_SET['assets'])
                spec=ICON_SET['assets'][name]
                path=ICON_ROOT/spec['file']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),spec['sha256'])
                self.assertIsNotNone(artwork(name))
        master=ICON_ROOT/'original.png'
        self.assertEqual(master.read_bytes(),(ICON_ROOT.parent/'partly-cloudy.png').read_bytes())

    def test_only_two_pages_for_every_short_key(self):
        from app import PAGES
        self.assertEqual(PAGES,('home','details'))
        with tempfile.TemporaryDirectory() as d:
            app=App(DEFAULTS,Path(d))
            for key in ('up','down','confirm'):
                app.page='home'
                for expected in ('details','home','details','home'):
                    app.bridge_event({'event':'key','key':{'up':'Up','down':'Down','confirm':'Confirm'}[key],'action':'Short'})
                    self.assertEqual(app.page,expected)

    def test_combined_unknown_and_missing_forecasts(self):
        snap=parse(raw(),'南京',32,118,NOW)
        snap['current']['weather_code']=999
        snap['hourly']=[];snap['daily']=[]
        self.assertEqual(render(NOW,snap,'缓存 16:30','details').size,(400,300))

    def test_home_has_no_clock_and_no_minute_refresh(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(DEFAULTS,Path(d));app.render(now=NOW);app.last_fetch=10
            before=app.preview
            with patch.object(app,'fetch') as fetch,patch.object(app,'render') as repaint:
                for minute in (1,2,15,59):
                    app.tick(now=NOW+timedelta(minutes=minute),monotonic_now=10+minute*60)
                fetch.assert_not_called();repaint.assert_not_called()
            app.render(now=NOW+timedelta(minutes=1))
            self.assertEqual(app.preview,before)

    def test_details_is_quiet_and_fetch_runs_hourly(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(DEFAULTS,Path(d));app.action('details');app.last_fetch=10
            with patch.object(app,'fetch') as fetch,patch.object(app,'render') as repaint:
                app.tick(now=NOW+timedelta(minutes=1),monotonic_now=70)
                app.tick(now=NOW+timedelta(minutes=59),monotonic_now=3609)
                fetch.assert_not_called();repaint.assert_not_called()
                app.tick(now=NOW+timedelta(hours=1),monotonic_now=3610)
                fetch.assert_called_once();repaint.assert_not_called()

    def test_identical_image_is_not_submitted_again(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(DEFAULTS,Path(d));app.render(now=NOW)
            revision=app.revision
            with patch.object(app,'dispatch') as send:
                app.render(now=NOW)
                send.assert_not_called();self.assertEqual(app.revision,revision)
                app.render(now=NOW,force=True)
                send.assert_called_once()

    def test_battery_unknown_zero_full_and_charging_layout(self):
        snapshot=parse(raw(),'南京',32,118,NOW)
        for value in (None,0,1,92,100):
            for page in ('home','details'):
                image=render(NOW,snapshot,'更新 16:30',page,status={'battery_percent':value,'charging':True})
                self.assertEqual(image.size,(400,300))
        with self.assertRaises(ValueError):
            render(NOW,snapshot,'更新 16:30',status={'battery_percent':101})

    def test_changing_battery_status_never_repaints_or_submits(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(DEFAULTS,Path(d));app.render(now=NOW)
            original=app.preview;revision=app.revision
            with patch.object(app,'render') as repaint,patch.object(app,'dispatch') as submit:
                for percent,charging in ((100,True),(99,False),(97,False),(98,False),(None,None),(0,False)):
                    app.bridge_event({'event':'status','status':{'battery_percent':percent,'charging':charging,'wifi_rssi_dbm':-40}})
                repaint.assert_not_called();submit.assert_not_called()
            self.assertEqual(app.preview,original);self.assertEqual(app.revision,revision)
            self.assertEqual(app.telemetry['battery_percent'],0)
            restored=App(DEFAULTS,Path(d))
            self.assertEqual(restored.telemetry['battery_percent'],0)

    def test_restart_uses_fresh_cache_without_extra_fetch_and_can_connect(self):
        import time
        now=datetime.now(TZ)
        response=raw();response['current']['time']=now.isoformat()
        with tempfile.TemporaryDirectory() as d:
            store=WeatherStore(DEFAULTS,Path(d),lambda _:response)
            self.assertTrue(store.update(now))
            app=App(DEFAULTS,Path(d));app.initial_connect=True
            self.assertLess(time.monotonic()-app.last_fetch,5)
            app.events.put(('noop',None))
            with patch.object(app,'fetch') as fetch,patch.object(app,'connect',side_effect=app.stop.set) as connect:
                app.run()
                fetch.assert_not_called();connect.assert_called_once()

    def test_identity_failure_never_opens_sdk(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(DEFAULTS,Path(d))
            with patch('app.probe',side_effect=ValueError('设备身份不匹配')), patch('app.subprocess.Popen') as spawn:
                app.connect()
                spawn.assert_not_called()
                self.assertEqual(app.connection,'连接失败')
                self.assertIn('身份',app.error)

    def test_latest_only_recording_and_unknown_latch(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(DEFAULTS,Path(d));app.connection='已连接';app.inflight=1;app.inflight_page='home'
            sent=[];app.send=sent.append
            app.action('details');app.action('home');app.action('details')
            self.assertEqual(sent,[])
            app.bridge_event({'event':'displayed','id':1})
            self.assertEqual(len(sent),1);self.assertEqual(app.inflight_page,'details')
            app.bridge_event({'event':'display_error','kind':'ResultUnknown','unknown':True,'error':'unknown'})
            app.action('home');self.assertEqual(len(sent),1)
            app.action('retry_display');self.assertEqual(len(sent),2)
            app.inflight=None;app.recording=True;app.action('details');self.assertEqual(len(sent),2)
            app.bridge_event({'event':'recording_finished'});self.assertEqual(len(sent),3)

if __name__=='__main__': unittest.main()
