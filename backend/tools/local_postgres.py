"""First local installation only; refuse existing data/configuration before writing."""
import os
import secrets
import shutil
import subprocess
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def preflight(root):
    if (root/'.env.fastapi').exists() or (root/'backups/postgres-docker.env').exists():
        raise SystemExit('Existing local configuration found; keep credentials and database. Use the launcher.')
    if not shutil.which('docker'):
        raise SystemExit('Docker Desktop is not installed or docker is not on PATH.')
    if os.environ.get('DOCKER_HOST') and not os.environ['DOCKER_HOST'].startswith('npipe://'):
        raise SystemExit('Only local Windows Docker Desktop is supported; remote Docker was not changed.')
    def docker(*args):
        return subprocess.run(['docker',*args],capture_output=True,text=True,timeout=15)
    context=docker('context','inspect','--format','{{.Endpoints.docker.Host}}')
    if context.returncode or not context.stdout.strip().startswith('npipe://'):
        raise SystemExit('Select the local Docker Desktop context before installation.')
    if docker('version','--format','{{.Server.Version}}').returncode:
        raise SystemExit('Docker Desktop is not ready. Start it and retry; no configuration was written.')
    for args,missing in [(('inspect','fitgate-postgres'),'no such object'),(('volume','inspect','fitgate-postgres-data'),'no such volume')]:
        result=docker(*args)
        if result.returncode==0:
            raise SystemExit('Existing FitGate container or volume found. Recover its original configuration; no files or data changed.')
        if missing not in result.stderr.lower():
            raise SystemExit('Could not verify Docker resources; no configuration was written.')

def main():
    preflight(ROOT)
    env=ROOT/'.env.fastapi';docker_env=ROOT/'backups/postgres-docker.env'
    password=secrets.token_urlsafe(32)
    docker_env.parent.mkdir(exist_ok=True)
    with docker_env.open('x',encoding='utf-8') as handle:
        handle.write(f'POSTGRES_USER=fitgate\nPOSTGRES_PASSWORD={password}\nPOSTGRES_DB=fitgate\n')
    with env.open('x',encoding='utf-8') as handle:
        handle.write(f'DATABASE_URL=postgresql+psycopg://fitgate:{password}@127.0.0.1:5433/fitgate\nSECRET_KEY={secrets.token_urlsafe(64)}\nENVIRONMENT=development\nALLOW_DEVICE_SIMULATION=false\nALLOW_SINGLE_SENSOR_PROTOTYPE=false\nSINGLE_SENSOR_PROTOTYPE_DEVICE_CODE=\n')
    subprocess.run(['docker','run','--detach','--name','fitgate-postgres','--env-file',str(docker_env),'-p','127.0.0.1:5433:5432','--mount','type=volume,source=fitgate-postgres-data,target=/var/lib/postgresql/data','postgres:17'],check=True)
    for _ in range(60):
        ready=subprocess.run(['docker','exec','fitgate-postgres','pg_isready','-q'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
        if ready.returncode==0:break
        time.sleep(1)
    else:raise SystemExit('PostgreSQL is not ready; keep local configuration and check Docker logs.')
    print('Local PostgreSQL configured; credentials remain in ignored local files.')

if __name__=='__main__':
    try:main()
    except (subprocess.SubprocessError,OSError):
        raise SystemExit('Local installation could not complete. Keep existing files; check Docker and filesystem permissions. Secret values were not displayed.') from None
