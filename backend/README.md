# FitGate Backend

Aktif backend `app.main:app` ile calisan bagimsiz FastAPI uygulamasidir.
SQLAlchemy 2 / psycopg ile PostgreSQL kullanir; yeni runtime Django veya SQL Server gerektirmez.

Windows kurulumu ve sorun giderme: [Kurulum](../docs/KURULUM.md).
API, admin/cihaz kaydi ve test notlari: [Backend rehberi](docs/fastapi-running.md).

Backend klasorunde:

```powershell
.\.venv-fastapi\Scripts\python.exe -m alembic upgrade head
.\.venv-fastapi\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

API dokumantasyonu: http://127.0.0.1:8001/docs

Ilk kurulum proje kokundeki `FitGate-Kurulum.bat` ile tek akistir: PostgreSQL 17,
Alembic ve 20 uye / 5 personelli kurgusal kayitlar otomatik hazirlanir.
Alti yerel ornek hesap [README](../README.md) icindedir. Mevcut ayar, container
ve volume korunur; uretimde herkese acik hesap kurulumu reddedilir.

`requirements.txt` ve `requirements-fastapi.txt` yeni stack'i belirtir.
Test edilen tam surumler `requirements-fastapi.lock.txt` dosyasindadir.
PostgreSQL semasi icin Alembic kullanin; gercek env ve veri arsivleri depoya eklenmez.
