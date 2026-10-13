import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from bridge import Store, Bridge, ApiError


class FakePort:
    def __init__(self): self.lines=[]
    def write(self,value): self.lines.append(value.decode().strip())


class FakeApi:
    def __init__(self): self.calls=[]; self.failed=False
    def post(self,path,payload,key=None,**options):
        self.calls.append((path,payload,key))
        if self.failed: raise ApiError(503)
        now=datetime.now(timezone.utc)
        direction=payload.get('direction','entry')
        return {'result':{'approved':True,'grantId':'fake-grant','direction':'entry' if direction=='auto' else direction,'serverTime':now.isoformat(),'expiresAt':(now+timedelta(seconds=30)).isoformat()}}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.folder.name)/'queue.sqlite3')
        self.api=FakeApi(); self.port=FakePort()
        self.bridge=Bridge(self.api,self.store,self.port)
        self.bridge.handle('READY|5'); self.bridge.handle('HEALTH|ready')
    def tearDown(self): self.store.db.close(); self.folder.cleanup()
    def authorize(self): self.bridge.handle('SCAN|1|FA000001|E')
    def prototype(self):
        self.bridge=Bridge(self.api,self.store,self.port,allow_prototype=True)
        self.bridge.handle('READY|7'); self.bridge.handle('HEALTH|ready')
        original=self.api.post
        def post(path,payload,key=None,**options):
            response=original(path,payload,key,**options)
            if path=='access/authorize': response['result']['validationMode']='single_sensor_prototype'
            return response
        self.api.post=post

    def test_prototype_requires_explicit_bridge_permission(self):
        bridge=Bridge(self.api,self.store,self.port)
        bridge.handle('READY|7'); bridge.handle('SCAN|1|FA000001|A')
        self.assertFalse(bridge.ready); self.assertEqual(self.api.calls,[])

    def test_prototype_visit_direction_and_single_event_retry(self):
        self.prototype(); self.bridge.handle('SCAN|1|FA000001|A')
        self.assertEqual(self.api.calls[-1][1],{'credential':'FA000001','direction':'auto','validationMode':'single_sensor_prototype'})
        self.bridge.handle('PASS|1|E|300|1|single_sensor_prototype')
        self.bridge.handle('PASS|1|E|300|1|single_sensor_prototype')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],1)
        import json
        payload=json.loads(self.store.db.execute('SELECT payload FROM events').fetchone()[0])
        self.assertEqual(payload['triggeringSensor'],1)
        self.assertEqual(payload['validationMode'],'single_sensor_prototype')

    def test_prototype_requires_mode_ack_and_rejects_unmatched_or_old_frame(self):
        self.prototype()
        self.bridge.handle('PASS|1|E|300|0|single_sensor_prototype')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],0)
        self.bridge.handle('SCAN|1|FA000001|A')
        self.bridge.handle('PASS|1|E|300')
        self.bridge.handle('PASS|1|X|300|0|single_sensor_prototype')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],0)

    def test_prototype_mode_is_cleared_on_normal_reconnect(self):
        self.prototype(); self.bridge.handle('READY|6')
        self.assertEqual(self.bridge.telemetry['validationMode'],'two_sensor')
    def test_grant_not_visit(self):
        self.authorize()
        self.assertTrue(self.port.lines[-1].startswith('ALLOW|1|E'))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],0)
    def test_explicit_exit_from_inner_sensor(self):
        self.bridge.handle('SCAN|1|FA000001|X')
        self.assertEqual(self.api.calls[-1][1]['direction'],'exit')
        self.assertTrue(self.port.lines[-1].startswith('ALLOW|1|X'))
    def test_outer_sensor_requests_entry_not_auto(self):
        self.authorize()
        self.assertEqual(self.api.calls[-1][1]['direction'],'entry')
    def test_ambiguous_missing_or_invalid_sensor_direction_denied(self):
        for way in ['B','N','F','C','invalid']:
            self.bridge.handle(f'SCAN|1|FA000001|{way}')
            self.assertTrue(self.port.lines[-1].startswith('DENY|1|'))
        self.assertEqual(self.api.calls,[])
    def test_old_firmware_cannot_authorize(self):
        bridge=Bridge(self.api,self.store,self.port)
        bridge.handle('READY|2');bridge.handle('SCAN|1|FA000001')
        self.assertFalse(bridge.ready)
        self.assertEqual(self.api.calls,[])
    def test_server_cannot_override_sensor_direction(self):
        original=self.api.post
        def wrong(path,payload,key=None,**options):
            result=original(path,payload,key,**options)
            if path=='access/authorize': result['result']['direction']='exit'
            return result
        self.api.post=wrong
        self.authorize()
        self.assertEqual(self.port.lines[-1],'DENY|1|Yon uyusmazligi')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM grants').fetchone()[0],0)
    def test_passage_persisted_before_ack(self):
        self.authorize(); self.bridge.handle('PASS|1|E|1500')
        self.assertEqual(self.port.lines[-1],'ACK|1')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],1)
    def test_duplicate_passage_single_queue_item(self):
        self.authorize()
        self.bridge.handle('PASS|1|E|1500'); self.bridge.handle('PASS|1|E|1500')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],1)
    def test_wrong_direction_not_counted(self):
        self.authorize(); self.bridge.handle('PASS|1|X|1500')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],0)
    def test_unknown_grant_not_counted(self):
        self.bridge.handle('PASS|999|E|1500')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],0)
    def test_server_failure_denies(self):
        self.api.failed=True; self.authorize()
        self.assertTrue(self.port.lines[-1].startswith('DENY|'))
    def test_sensor_fault_denies(self):
        self.bridge.handle('HEALTH|fault'); self.authorize()
        self.assertTrue(self.port.lines[-1].startswith('DENY|'))
        self.assertEqual(len(self.api.calls),0)
    def test_queue_survives_failure_and_retry(self):
        self.authorize(); self.bridge.handle('PASS|1|E|1500')
        self.api.failed=True; self.store.flush_one(self.api)
        self.assertEqual(self.store.db.execute('SELECT status FROM events').fetchone()[0],'pending')
        self.api.failed=False; self.store.flush_one(self.api)
        self.assertEqual(self.store.db.execute('SELECT status FROM events').fetchone()[0],'sent')
        self.assertEqual(self.api.calls[-1][2],self.api.calls[-2][2])
    def test_invalid_event_retained_for_review(self):
        self.authorize(); self.bridge.handle('PASS|1|E|1500')
        class RejectApi:
            def post(self,*args): raise ApiError(400)
        self.store.flush_one(RejectApi())
        self.assertEqual(self.store.db.execute('SELECT status FROM events').fetchone()[0],'review')

    def test_capture_does_not_authorize_or_require_sensors(self):
        self.bridge.capture={'id':'capture-test'}; self.bridge.capture_armed=True
        self.bridge.health='fault'; self.authorize()
        self.assertEqual(self.port.lines[-1],'CAPTURED|1')
        self.assertEqual([call[0] for call in self.api.calls],['capture/read'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM grants').fetchone()[0],0)

    def test_capture_not_armed_cannot_open_gate(self):
        self.bridge.capture={'id':'capture-test'}; self.authorize()
        self.assertEqual(self.port.lines[-1],'CAPTURED|1|error')
        self.assertEqual(self.api.calls,[])

    def test_measurements_forwarded_once_per_new_frame(self):
        self.bridge.handle('DIST|45|-1');self.bridge.push_measurements();self.bridge.push_measurements()
        self.assertEqual([c[0] for c in self.api.calls],['measurements'])
        self.assertEqual(self.api.calls[0][1],{'outsideCm':45,'insideCm':None})
        self.bridge.handle('DIST|46|80');self.bridge.push_measurements()
        self.assertEqual(len(self.api.calls),2)

    def test_duplicate_scan_does_not_reauthorize(self):
        self.authorize(); first=self.port.lines[-1]
        self.authorize()
        self.assertEqual(self.port.lines[-1],first)
        self.assertEqual(sum(c[0]=='access/authorize' for c in self.api.calls),1)

    def test_conflicting_scan_id_denied(self):
        self.authorize(); self.bridge.handle('SCAN|1|11111111|E')
        self.assertEqual(self.port.lines[-1],'DENY|1|Olay cakismasi')
        self.assertEqual(sum(c[0]=='access/authorize' for c in self.api.calls),1)

    def test_v3_cannot_grant_access(self):
        bridge=Bridge(self.api,self.store,self.port)
        bridge.handle('READY|3'); bridge.handle('HEALTH|ready'); bridge.handle('SCAN|1|FA000001|E')
        self.assertFalse(bridge.ready); self.assertEqual(self.api.calls,[])

    def test_components_are_not_inferred_from_sensor_health(self):
        self.assertNotIn('rfid',self.bridge.telemetry)
        self.bridge.handle('COMP|ready|closed|fault')
        self.assertEqual(self.bridge.telemetry['rfid'],'ready')
        self.assertEqual(self.bridge.telemetry['lcd'],'fault')
        self.bridge.handle('COMP|fake|open|ready')
        self.assertEqual(self.bridge.telemetry['servo'],'closed')

    def test_no_passage_on_fault_or_timeout(self):
        self.authorize(); self.bridge.handle('FAULT|1|Gecis zaman asimi')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],0)

    def test_personnel_scan_uses_same_physical_grant_not_immediate_attendance(self):
        self.bridge.purpose='attendance'
        original=self.api.post
        def post(path,payload,key=None,**options):
            response=original(path,payload,key,**options)
            if path=='heartbeat': return {'purpose':'attendance','mode':'auto'}
            return response
        self.api.post=post
        self.bridge.handle('SCAN|1|FA000001|E')
        self.assertTrue(self.port.lines[-1].startswith('ALLOW|1|E'))
        self.assertEqual([c[0] for c in self.api.calls],['heartbeat','access/authorize'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM grants').fetchone()[0],1)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],0)

    def test_v4_cannot_use_unified_protocol(self):
        bridge=Bridge(self.api,self.store,self.port); bridge.handle('READY|4')
        self.assertFalse(bridge.ready)

    def test_v6_card_authorization_precedes_sensor_direction(self):
        self.bridge.handle('READY|6'); self.bridge.handle('HEALTH|ready')
        self.bridge.handle('SCAN|1|FA000001|A')
        self.assertEqual(self.api.calls[-1][1]['direction'],'auto')
        self.assertTrue(self.port.lines[-1].startswith('ALLOW|1|E'))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],0)

    def test_v6_progress_does_not_complete_visit(self):
        self.bridge.handle('READY|6'); self.bridge.handle('HEALTH|ready')
        self.bridge.handle('SCAN|1|FA000001|A')
        self.bridge.handle('PROGRESS|1|detected|E')
        self.assertEqual(self.bridge.telemetry['detectedDirection'],'entry')
        self.assertEqual(self.bridge.telemetry['passageState'],'detected')
        self.bridge.handle('PROGRESS|1|waiting_clear|E')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],0)
        self.bridge.handle('PASS|1|E|1500')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],1)

    def test_v6_auto_authorization_can_match_existing_exit(self):
        self.bridge.handle('READY|6'); self.bridge.handle('HEALTH|ready')
        original=self.api.post
        def post(path,payload,key=None,**options):
            result=original(path,payload,key,**options)
            if path=='access/authorize': result['result']['direction']='exit'
            return result
        self.api.post=post
        self.bridge.handle('SCAN|1|FA000001|A')
        self.assertTrue(self.port.lines[-1].startswith('ALLOW|1|X'))
        self.bridge.handle('PASS|1|E|1500')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],0)

    def test_v5_cannot_request_v6_auto_scan(self):
        self.bridge.handle('SCAN|1|FA000001|A')
        self.assertTrue(self.port.lines[-1].startswith('DENY|1|'))

    def test_lcd_and_indicator_frames_are_reported_without_visits(self):
        self.bridge.handle('LCD|MESAI BASLADI|KAYIT TAMAMLANDI')
        self.bridge.handle('IO|1|0')
        self.assertEqual(self.bridge.telemetry['lcdTop'],'MESAI BASLADI')
        self.assertTrue(self.bridge.telemetry['buzzer']); self.assertFalse(self.bridge.telemetry['led'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],0)

    def test_diagnostic_poll_and_report_cannot_authorize(self):
        identifier=str(__import__('uuid').uuid4())
        class DiagnosticsApi:
            def post(self,path,payload,**options):
                return {'command':{'id':identifier,'action':'lcd'}} if path=='commands/poll' else {'ok':True}
        self.bridge.api=DiagnosticsApi(); self.bridge.sync_diagnostics()
        self.assertEqual(self.port.lines[-1],f'DIAG|{identifier}|lcd')
        self.bridge.handle(f'DIAGDONE|{identifier}|ok|done'); self.assertEqual(len(self.bridge.diagnostic_results),1)
        self.bridge.active_scan='1'; self.bridge.sync_diagnostics()
        self.assertEqual(len(self.bridge.diagnostic_results),0)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM grants').fetchone()[0],0)

    def test_measurements_keep_reported_components(self):
        self.bridge.handle('COMP|ready|closed|ready'); self.bridge.handle('DIST|15|40')
        self.bridge.push_measurements()
        self.assertEqual(self.bridge.telemetry['rfid'],'ready')
        self.assertEqual(self.api.calls[-1][1],{'outsideCm':15,'insideCm':40})

    def test_port_mutex_rejects_other_process(self):
        import os, subprocess, sys
        from bridge import PortLock
        if os.name!='nt': self.skipTest('Windows port mutex')
        lock=PortLock('COM999')
        try:
            result=subprocess.run([sys.executable,'-c',"from bridge import PortLock; PortLock('COM999')"],cwd=Path(__file__).parent,capture_output=True,timeout=10)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b'zaten calisiyor',result.stderr)
        finally: lock.close()

