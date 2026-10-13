"""Only backup metadata is exposed; dumps never enter a public directory."""
import json
from pathlib import Path
from sqlalchemy import text
from app.db.session import get_session

DIRECTORY=Path(__file__).resolve().parents[2]/'backups'/'system'

def status():
    get_session().execute(text('SELECT 1'))
    history=[]
    for path in sorted(DIRECTORY.glob('*.json'),reverse=True)[:50]:
        try:
            item=json.loads(path.read_text(encoding='utf-8'))
            history.append({key:item.get(key) for key in ['id','at','status','verified','restoreVerified','error']})
        except (OSError,ValueError):continue
    successful=next((row for row in history if row['status']=='success'),None)
    return {'database':'connected','lastSuccessfulAt':successful['at'] if successful else None,'latest':history[0] if history else None,'history':history}
