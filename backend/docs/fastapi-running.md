# FitGate FastAPI + PostgreSQL

Aktif API `app.main:app`, SQLAlchemy ve PostgreSQL 17 kullanir.
Windows ilk kurulum, Docker, yedekleme ve baslatici rehberi:
[Kurulum](../../docs/KURULUM.md).

Backend dizininde yeni Python ortami icin:

```powershell
python -m venv .venv-fastapi
.\.venv-fastapi\Scripts\python.exe -m pip install -r requirements-fastapi.lock.txt
```

Yalnizca ilk ve verisiz kurulumda Docker Desktop hazirken
`tools/local_postgres.py`, ardindan `alembic upgrade head` ve
`tools/create_admin.py` calistirilir. Mevcut konteyner, volume veya ayar varsa
kurulum araci durur. Eski veriyi silerek kurulumu zorlamayin.

Proje kokunden `FitGate-Baslat.bat` ve `FitGate-Durdur.bat` kullanilir.
React Windows :5174, FastAPI Windows :8001, PostgreSQL Docker :5433'tedir.
Arduino olmadan yonetim ekranlari calisir. Bridge icin yerel cihaz kaydi gerekir.

Varsayilan parola yoktur; `.env.fastapi.example` yalnizca alan ornegidir.
Gercek env, sifreler, UID eslesmeleri ve yedekler dagitima dahil degildir.
Demo reset normal baslangicta calismaz. Firmware 7 test prototipidir;
[guvenlik ve derleme bayragi](../../docs/tek-sensor-prototip-testi.md).

`tools/import_backup.py` eski export bicimini okuyabilen istege bagli bir
aktarma aracidir; Django runtime gerektirmez. Otomatik baslangicta cagrilmaz.
Eski kurulumdan aktarim gerekiyorsa once yedek, ayri deneme ortami ve acik onay gerekir.

Testler ayri `fitgate_fastapi_test` veritabanini yeniden olusturur. Bu veritabanina
gercek kayit koymayin; canli veritabaninda fixture veya reset calistirmayin.
