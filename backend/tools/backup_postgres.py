"""Local Docker PostgreSQL backup; optional isolated restore drill, never live restore."""
import argparse,getpass,json,os,re,subprocess,sys,uuid
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.config import settings
from sqlalchemy.engine import make_url
from app.services.backups import DIRECTORY

def command(*args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=180)
    if result.returncode:raise RuntimeError('Yedekleme komutu tamamlanamadı; Docker/PostgreSQL ve disk izinlerini kontrol edin.')
    return result

def run(restore=False):
    url=make_url(settings.database_url)
    if url.host not in ['localhost','127.0.0.1'] or url.port!=5433 or url.database!='fitgate' or url.username!='fitgate':
        raise RuntimeError('Bu araç yalnızca mevcut yerel fitgate-postgres Docker kurulumunu destekler.')
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    if os.name=='nt':
        identity=os.environ.get('USERDOMAIN','')+'\\'+getpass.getuser()
        command('icacls',str(DIRECTORY),'/inheritance:r','/grant:r',identity+':(OI)(CI)F','*S-1-5-18:(OI)(CI)F')
    else:DIRECTORY.chmod(0o700)
    key=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    filename=key+'.dump';remote='/tmp/fitgate-'+filename;verify_db='fitgate_restore_verify_'+uuid.uuid4().hex
    item={'id':key,'at':datetime.now(timezone.utc).isoformat(),'status':'failed','verified':False,'restoreVerified':False,'error':None}
    try:
        command('docker','exec','fitgate-postgres','pg_dump','-U','fitgate','-d','fitgate','-Fc','-f',remote)
        command('docker','exec','fitgate-postgres','pg_restore','--list',remote)
        command('docker','cp','fitgate-postgres:'+remote,str(DIRECTORY/filename))
        if os.name!='nt':(DIRECTORY/filename).chmod(0o600)
        item['verified']=True
        if restore:
            assert re.fullmatch(r'fitgate_restore_verify_[0-9a-f]{32}',verify_db)
            command('docker','exec','fitgate-postgres','createdb','-U','fitgate',verify_db)
            command('docker','exec','fitgate-postgres','pg_restore','-U','fitgate','-d',verify_db,'--exit-on-error','--no-owner',remote)
            command('docker','exec','fitgate-postgres','psql','-U','fitgate','-d',verify_db,'-v','ON_ERROR_STOP=1','-c','SELECT version_num FROM alembic_version; SELECT count(*) FROM gym_branch;')
            item['restoreVerified']=True
        item['status']='success'
    except (RuntimeError,subprocess.TimeoutExpired):item['error']='Yedek veya ayrı ortam geri yükleme doğrulaması başarısız. Docker/PostgreSQL ve disk izinlerini kontrol edin.'
    finally:
        if restore:
            subprocess.run(['docker','exec','fitgate-postgres','dropdb','-U','fitgate','--if-exists',verify_db],capture_output=True,timeout=30)
        subprocess.run(['docker','exec','fitgate-postgres','rm','-f',remote],capture_output=True,timeout=30)
        (DIRECTORY/(key+'.json')).write_text(json.dumps(item,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(item,ensure_ascii=False))
    return item['status']=='success'

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify-restore',action='store_true');args=parser.parse_args()
    raise SystemExit(0 if run(args.verify_restore) else 1)
