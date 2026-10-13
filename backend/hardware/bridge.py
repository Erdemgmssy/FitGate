"""USB serial bridge. Never grants access without a successful server decision."""
import argparse
import json
import logging
import os
import sqlite3
import time
import uuid
import unicodedata
import ctypes
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import serial
from serial.tools import list_ports
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
LOG = logging.getLogger('fitgate.usb')


class ApiError(Exception):
    def __init__(self, status):
        super().__init__(f'API status {status}')
        self.status = status


class Api:
    def __init__(self, base, code, key):
        parsed = urlparse(base)
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ['127.0.0.1', 'localhost']):
            raise ValueError('Use HTTPS except for a local loopback server.')
        self.base, self.code, self.key = base.rstrip('/'), code, key

    def post(self, path, payload, key=None, timeout=2):
        headers = {'Content-Type':'application/json', 'X-Device-Code':self.code, 'X-Device-Key':self.key}
        if key: headers['Idempotency-Key'] = key
        request = Request(f'{self.base}/api/v1/device/{path}/', json.dumps(payload).encode(), headers, method='POST')
        try:
            with urlopen(request, timeout=timeout) as response: body=json.load(response)
            if not isinstance(body,dict) or body.get('ok') is not True: raise ApiError(502)
            return body
        except HTTPError as error: raise ApiError(error.code) from None
        except (ValueError,TypeError): raise ApiError(502) from None


def lcd_text(value):
    text=unicodedata.normalize('NFKD',str(value).replace('ı','i')).encode('ascii',errors='ignore').decode()
    return ''.join(ch for ch in text if 32<=ord(ch)<127 and ch!='|')[:16]


def denial_text(reason):
    value=str(reason).lower()
    if 'seans' in value: return 'SEANS YETERSIZ'
    if 'dondur' in value: return 'UYELIK DONUK'
    if 'üyelik geçerli' in value or 'süresi' in value: return 'UYELIK BITMIS'
    if 'sens' in value: return 'SENSOR HATASI'
    return lcd_text(reason)


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS grants (
              session TEXT, scan TEXT, grant_id TEXT, direction TEXT, server_at TEXT,
              expires_at TEXT, PRIMARY KEY(session,scan));
            CREATE TABLE IF NOT EXISTS events (
              key TEXT PRIMARY KEY, payload TEXT, status TEXT DEFAULT 'pending',
              attempts INTEGER DEFAULT 0, error TEXT DEFAULT '');
        ''')

    def grant(self, session, scan, result):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO grants VALUES (?,?,?,?,?,?)',
                (session,scan,result['grantId'],result['direction'],result['serverTime'],result['expiresAt']))

    def enqueue(self, session, scan, direction, elapsed_ms, validation_mode='two_sensor', triggering_sensor=None):
        row=self.db.execute('SELECT grant_id,direction,server_at,expires_at FROM grants WHERE session=? AND scan=?',(session,scan)).fetchone()
        if not row or row[1]!=direction or not 0<=elapsed_ms<=10000: raise ValueError('Unmatched sensor event')
        occurred=datetime.fromisoformat(row[2])+timedelta(milliseconds=elapsed_ms)
        if occurred>datetime.fromisoformat(row[3]): raise ValueError('Sensor event after grant expiry')
        key=str(uuid.uuid5(uuid.NAMESPACE_URL,f'fitgate:{session}:{scan}:passage'))
        event={'grantId':row[0],'eventId':key,'direction':direction,'occurredAt':occurred.isoformat()}
        if validation_mode=='single_sensor_prototype':
            if type(triggering_sensor) is not int or triggering_sensor not in [0,1]: raise ValueError('Invalid prototype sensor')
            event.update(validationMode=validation_mode,triggeringSensor=triggering_sensor)
        elif validation_mode!='two_sensor': raise ValueError('Invalid evidence mode')
        payload=json.dumps(event,sort_keys=True)
        existing=self.db.execute('SELECT payload FROM events WHERE key=?',(key,)).fetchone()
        if existing and existing[0]!=payload: raise ValueError('Conflicting duplicate sensor event')
        with self.db: self.db.execute('INSERT OR IGNORE INTO events(key,payload) VALUES (?,?)',(key,payload))
        return key

    def flush_one(self, api):
        row=self.db.execute("SELECT key,payload FROM events WHERE status='pending' ORDER BY rowid LIMIT 1").fetchone()
        if not row: return
        try:
            response=api.post('passage-events',json.loads(row[1]),row[0])
            with self.db: self.db.execute("UPDATE events SET status='sent',error='' WHERE key=?",(row[0],))
            LOG.info('Single sensor prototype event recorded.' if json.loads(row[1]).get('validationMode')=='single_sensor_prototype' else 'Physical passage recorded.')
            return json.loads(row[1]),response.get('result')
        except ApiError as error:
            # Rejected events remain available for an administrator; never discard them.
            state='review' if error.status in [400,409] else 'pending'
            with self.db: self.db.execute('UPDATE events SET status=?,attempts=attempts+1,error=? WHERE key=?',(state,str(error),row[0]))
            LOG.warning('Passage not recorded: %s; queue state: %s',error,state)
        except (URLError,TimeoutError,OSError):
            LOG.warning('Server unavailable; physical passage retained in local queue.')


class Bridge:
    def __init__(self, api, store, port, allow_prototype=False):
        self.api, self.store, self.port = api, store, port
        self.allow_prototype=allow_prototype
        self.session=str(uuid.uuid4())
        self.ready=False
        self.health='unknown'
        self.health_at=0
        self.capture=None
        self.capture_armed=False
        self.telemetry={}
        self.measurement_revision=0
        self.sent_revision=0
        self.logs=deque(maxlen=100)
        self.responses={}
        self.purpose='access'
        self.last_frame_at=time.monotonic()
        self.active_scan=None
        self.diagnostic_results=deque(maxlen=20)

    def report(self,event,detail=''): self.logs.append({'type':event,'detail':detail})

    def push_measurements(self):
        if self.measurement_revision==self.sent_revision: return
        try:
            self.api.post('measurements',{key:self.telemetry.get(key) for key in ['outsideCm','insideCm']},timeout=0.7)
            self.sent_revision=self.measurement_revision
        except (ApiError,URLError,TimeoutError,OSError): pass

    def flush_log(self):
        if not self.logs: return
        try:
            self.api.post('diagnostics',self.logs[0],timeout=0.5); self.logs.popleft()
        except (ApiError,URLError,TimeoutError,OSError): pass

    def sync_capture(self):
        try:
            item=self.api.post('capture/status',{})['capture']
            if item and (not self.capture or self.capture['id']!=item['id'] or not self.capture_armed):
                self.capture=item; self.capture_armed=False; self.send('CAPTURE|1')
            elif not item and self.capture:
                self.capture=None; self.capture_armed=False; self.send('CAPTURE|0')
        except (ApiError,URLError,TimeoutError,OSError,KeyError):
            if self.capture: self.capture=None; self.capture_armed=False; self.send('CAPTURE|0')

    def send(self, line): self.port.write((line+'\n').encode('ascii'))

    def heartbeat(self):
        result=self.api.post('heartbeat',{'connected':True,'sensor':self.health,'telemetry':self.telemetry})
        self.purpose=result.get('purpose','access')
        self.send('PING|'+self.telemetry.get('firmware','5'))
        self.send('PURPOSE|'+self.purpose)
        return result

    def handle(self, line):
        self.last_frame_at=time.monotonic()
        parts=line.strip().split('|')
        if len(parts)==2 and parts[0]=='READY' and (parts[1] in ['5','6'] or parts[1]=='7' and self.allow_prototype):
            self.session=str(uuid.uuid4()); self.ready=True; self.health='unknown'
            self.responses.clear()
            self.telemetry['firmware']=parts[1]
            self.telemetry['validationMode']='single_sensor_prototype' if parts[1]=='7' else 'two_sensor'
            for field in ['passageState','detectedDirection','progressAt']: self.telemetry.pop(field,None)
            self.send('HELLO|'+parts[1]); LOG.info('Compatible FitGate firmware connected.')
            self.report('connected')
        elif parts and parts[0]=='READY':
            self.ready=False
            self.telemetry['lastError']='Uyumlu firmware ve prototip icin acik yerel izin gerekli.'
            LOG.warning(self.telemetry['lastError'])
        elif parts==['MODE','capture']:
            self.capture_armed=True
            self.report('capture_mode')
        elif parts==['MODE','normal'] or parts==['MODE','busy']:
            self.capture_armed=False
            if parts[1]=='normal': self.report('normal_mode')
        elif parts==['REMOVED']:
            self.report('removed')
        elif len(parts)==3 and parts[0]=='DIST':
            try:
                values=[int(v) for v in parts[1:]]
                if all(v==-1 or 2<=v<=340 for v in values):
                    self.telemetry.update(dict(zip(['outsideCm','insideCm'],[None if v<0 else v for v in values])))
                    self.measurement_revision+=1
            except ValueError: pass
        elif len(parts)==2 and parts[0]=='HEALTH' and self.ready:
            self.health=parts[1] if parts[1] in ['ready','fault','disabled'] else 'fault'
            self.health_at=time.monotonic()
        elif len(parts)==4 and parts[0]=='COMP':
            if parts[1] in ['ready','fault'] and parts[2] in ['open','closed'] and parts[3] in ['ready','fault']:
                self.telemetry.update(rfid=parts[1],servo=parts[2],lcd=parts[3])
        elif len(parts)==3 and parts[0]=='LCD':
            self.telemetry.update(lcdTop=lcd_text(parts[1]),lcdBottom=lcd_text(parts[2]))
        elif len(parts)==4 and parts[0]=='PROGRESS' and self.ready and self.telemetry.get('firmware') in ['6','7']:
            scan,state,way=parts[1:]
            if scan.isdigit() and state in ['idle','authorizing','waiting_first','detected','waiting_clear','completed','prototype_triggered','fault'] and way in ['E','X','N']:
                if state in ['waiting_first','detected','waiting_clear','completed','prototype_triggered'] and scan!=self.active_scan: return
                self.telemetry.update(passageState=state,detectedDirection={'E':'entry','X':'exit','N':'none'}[way],progressAt=datetime.now(timezone.utc).isoformat())
                if state=='detected' and way in ['E','X']: self.report('entry_detected' if way=='E' else 'exit_detected')
        elif len(parts)==3 and parts[0]=='IO' and all(value in ['0','1'] for value in parts[1:]):
            self.telemetry.update(buzzer=parts[1]=='1',led=parts[2]=='1')
        elif len(parts)==4 and parts[0]=='DIAGDONE':
            try:
                identifier=str(uuid.UUID(parts[1]))
                if parts[2] in ['ok','error']: self.diagnostic_results.append({'id':identifier,'status':parts[2],'detail':parts[3][:80]})
            except ValueError: pass
        elif len(parts)==4 and parts[0]=='SCAN' and self.ready:
            scan,uid,way=parts[1:]
            if not scan.isdigit() or len(scan)>10 or not 8<=len(uid)<=20 or any(ch not in '0123456789ABCDEF' for ch in uid):
                return
            if scan in self.responses:
                previous_uid,previous_way,response=self.responses[scan]
                if previous_uid==uid and previous_way==way: self.send(response)
                else: self.send(f'DENY|{scan}|Olay cakismasi')
                return
            if len(self.responses)>=500: self.responses.pop(next(iter(self.responses)))
            self.report('rfid')
            self.telemetry['lastScanUid']=uid
            def reply(value):
                self.responses[scan]=(uid,way,value); self.send(value)
            if self.capture:
                try:
                    if not self.capture_armed: raise ValueError('Capture mode not acknowledged')
                    self.api.post('capture/read',{'captureId':self.capture['id'],'uid':uid})
                    reply(f'CAPTURED|{scan}')
                    LOG.info('RFID UID captured for member assignment; no access grant issued.')
                except (ApiError,URLError,TimeoutError,OSError,ValueError):
                    reply(f'CAPTURED|{scan}|error'); self.report('server_error')
                return
            if way not in (['E','X','A'] if self.telemetry.get('firmware') in ['6','7'] else ['E','X']):
                reason={'B':'Iki sensor yakin','N':'Sensor 20cm alti','F':'Sensor not ready','C':'Atama modu bitti'}.get(way,'Yon gecersiz')
                self.report('rfid'); self.report('fault',reason)
                reply(f'DENY|{scan}|{reason}'); return
            if self.health!='ready' or time.monotonic()-self.health_at>10:
                self.report('rfid')
                self.report('sensor_denied')
                reply(f'DENY|{scan}|Sensor not ready'); return
            key=str(uuid.uuid5(uuid.UUID(self.session),f'scan:{scan}'))
            started=time.monotonic()
            try:
                status=self.heartbeat()
                if self.purpose not in ['access','attendance','mixed'] or status.get('mode','auto')!='auto': raise ValueError('Device purpose changed')
                requested_direction={'E':'entry','X':'exit','A':'auto'}[way]
                payload={'credential':uid,'direction':requested_direction}
                if self.telemetry.get('firmware')=='7':
                    if requested_direction!='auto': raise ValueError('Prototype requires visit-derived direction')
                    payload['validationMode']='single_sensor_prototype'
                result=self.api.post('access/authorize',payload,key)['result']
                if not result['approved']:
                    reply(f"DENY|{scan}|{denial_text(result.get('reason','Access denied'))}"); LOG.info('Card access denied.'); return
                if self.telemetry.get('firmware')=='7' and result.get('validationMode')!='single_sensor_prototype':
                    raise ValueError('Server did not acknowledge prototype mode')
                if result['direction'] not in ['entry','exit'] or requested_direction!='auto' and result['direction'] != requested_direction:
                    reply(f'DENY|{scan}|Yon uyusmazligi'); self.report('fault','Yon uyusmazligi'); return
                remaining=(datetime.fromisoformat(result['expiresAt'])-datetime.fromisoformat(result['serverTime'])).total_seconds()
                if time.monotonic()-started>3 or remaining<9:
                    reply(f'DENY|{scan}|Response too late'); return
                self.store.grant(self.session,scan,result)
                self.active_scan=scan
                reply(f"ALLOW|{scan}|{'E' if result['direction']=='entry' else 'X'}|8000|{lcd_text(result.get('memberName','Gecis bekleniyor'))}")
                LOG.info('Access granted for %s; awaiting sensor area release.',requested_direction)
            except (ApiError,URLError,TimeoutError,OSError,ValueError,KeyError):
                self.report('server_error')
                reply(f'DENY|{scan}|Server unavailable'); LOG.warning('No access grant: server request failed.')
        elif len(parts) in [4,6] and parts[0]=='PASS' and self.ready:
            scan,way,elapsed=parts[1:4]
            try:
                if way not in ['E','X']: raise ValueError('Invalid direction')
                prototype=self.telemetry.get('firmware')=='7'
                if prototype != (len(parts)==6): raise ValueError('Evidence frame mismatch')
                if prototype and (parts[5]!='single_sensor_prototype' or parts[4] not in ['0','1']): raise ValueError('Invalid prototype evidence')
                self.store.enqueue(self.session,scan,'entry' if way=='E' else 'exit',int(elapsed),
                    'single_sensor_prototype' if prototype else 'two_sensor', int(parts[4]) if prototype else None)
                self.report('prototype_queued' if prototype else 'queued')
                self.send(f'ACK|{scan}')
                self.active_scan=None
            except ValueError: LOG.error('Unmatched passage needs physical/manual inspection.')
        elif parts[0]=='FAULT':
            LOG.warning('Arduino reported a sensor/sequence fault; no visit was inferred.')
            self.report('fault',parts[2] if len(parts)>2 else '')
            self.telemetry['lastError']=parts[2] if len(parts)>2 else 'Firmware fault'
            self.active_scan=None

    def sync_diagnostics(self):
        try:
            if self.diagnostic_results:
                self.api.post('commands/result',self.diagnostic_results[0]); self.diagnostic_results.popleft()
            if self.ready and self.active_scan is None and not self.capture:
                item=self.api.post('commands/poll',{},timeout=0.5).get('command')
                if item and item.get('action') in ['servo','lcd','indicators']:
                    identifier=str(uuid.UUID(item['id']))
                    self.send(f"DIAG|{identifier}|{item['action']}")
        except (ApiError,URLError,TimeoutError,OSError,ValueError,KeyError): pass

    def passage_result(self, completed):
        if not completed or not self.ready: return
        payload,result=completed
        row=self.store.db.execute('SELECT scan FROM grants WHERE session=? AND grant_id=?',(self.session,payload['grantId'])).fetchone()
        if row:
            message=result.get('message','GECIS TAMAMLANDI') if isinstance(result,dict) else 'GECIS TAMAMLANDI'
            if payload.get('validationMode')=='single_sensor_prototype': message='TEST '+message
            self.send(f'RESULT|{row[0]}|{lcd_text(message)}')


class PortLock:
    """A machine-wide port mutex prevents competing FitGate bridge processes."""
    def __init__(self, port):
        self.handle=None
        if os.name=='nt':
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateMutexW.restype=ctypes.c_void_p
            kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p]
            self.handle=kernel.CreateMutexW(None,False,'Local\\FitGate-Serial-'+port.upper())
            if not self.handle: raise OSError('Port kilidi olusturulamadi.')
            kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint]
            result=kernel.WaitForSingleObject(self.handle,0)
            if result not in [0,128]:
                kernel.CloseHandle.argtypes=[ctypes.c_void_p]; kernel.CloseHandle(self.handle)
                self.handle=None
                raise SystemExit('Bu COM portunda FitGate bridge zaten calisiyor. Ikinci bridge baslatilmadi.')
            self.kernel=kernel

    def close(self):
        if self.handle:
            self.kernel.ReleaseMutex.argtypes=[ctypes.c_void_p]
            self.kernel.CloseHandle.argtypes=[ctypes.c_void_p]
            self.kernel.ReleaseMutex(self.handle); self.kernel.CloseHandle(self.handle); self.handle=None


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--list-ports',action='store_true')
    parser.add_argument('--queue-status',action='store_true')
    args=parser.parse_args()
    if args.list_ports:
        for port in list_ports.comports(): print(port.device,port.description)
        return
    if args.queue_status:
        if not (HERE/'passage-queue.sqlite3').exists(): print('Queue not created yet.'); return
        with sqlite3.connect(HERE/'passage-queue.sqlite3') as db:
            for state,count in db.execute('SELECT status,count(*) FROM events GROUP BY status'): print(state,count)
        return
    load_dotenv(HERE/'.env')
    key=os.getenv('DEVICE_KEY',''); code=os.getenv('DEVICE_CODE',''); port=os.getenv('SERIAL_PORT','')
    if len(key)<32 or not code or not port: raise SystemExit('Configure hardware/.env with register_usb_device first.')
    api=Api(os.getenv('API_BASE_URL','http://127.0.0.1:8001'),code,key)
    baud=int(os.getenv('SERIAL_BAUD','115200'))
    lock=PortLock(port)
    store=Store(HERE/'passage-queue.sqlite3')
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        while True:
            try:
                with serial.Serial(port,baud,timeout=0.15,write_timeout=1) as link:
                    bridge=Bridge(api,store,link,allow_prototype=os.getenv('ALLOW_SINGLE_SENSOR_PROTOTYPE','false').lower()=='true')
                    bridge.telemetry.update(port=port,connection='connected')
                    LOG.info('USB connected at %s; waiting for FitGate firmware. Opening the port may reset UNO.',port)
                    heartbeat_at=flush_at=capture_at=log_at=measurement_at=diagnostic_at=0
                    buffer=b''
                    while True:
                        buffer+=link.read_until(b'\n',160)
                        while b'\n' in buffer:
                            raw,buffer=buffer.split(b'\n',1)
                            if len(raw)<=159: bridge.handle(raw.decode('ascii',errors='replace'))
                        if len(buffer)>159: buffer=b''
                        now=time.monotonic()
                        if now-bridge.last_frame_at>12: raise serial.SerialException('Firmware cevap vermiyor')
                        if not bridge.ready and now-heartbeat_at>3:
                            try: api.post('heartbeat',{'connected':False,'sensor':'unknown','telemetry':{**bridge.telemetry,'connection':'retrying'}})
                            except (ApiError,URLError,TimeoutError,OSError): pass
                            heartbeat_at=now
                        if bridge.ready and now-measurement_at>0.8:
                            bridge.push_measurements(); measurement_at=now
                        if bridge.ready and now-capture_at>1:
                            bridge.sync_capture(); capture_at=now
                        if bridge.ready and now-heartbeat_at>3 and now-bridge.health_at<10:
                            try: bridge.heartbeat()
                            except (ApiError,URLError,TimeoutError,OSError): LOG.warning('Heartbeat failed.')
                            heartbeat_at=now
                        if now-flush_at>2:
                            bridge.passage_result(store.flush_one(api)); flush_at=now
                        if bridge.ready and now-diagnostic_at>1:
                            bridge.sync_diagnostics(); diagnostic_at=now
                        if now-log_at>0.7:
                            bridge.flush_log(); log_at=now
            except (serial.SerialException,OSError) as error:
                LOG.warning('USB unavailable; reconnecting in 3 seconds. Check Serial Monitor is closed.')
                try: api.post('heartbeat',{'connected':False,'sensor':'unknown','telemetry':{'port':port,'connection':'retrying','lastError':str(error)[:120]}})
                except (ApiError,URLError,TimeoutError,OSError): pass
                store.flush_one(api)
                time.sleep(3)
    except KeyboardInterrupt: LOG.info('USB bridge stopped.')
    finally:
        try: api.post('heartbeat',{'connected':False,'sensor':'unknown','telemetry':{'port':port,'connection':'retrying'}})
        except (ApiError,URLError,TimeoutError,OSError): pass
        store.db.close(); lock.close()


if __name__=='__main__': main()
