# FitGate FastAPI + PostgreSQL

Aktif API `app.main:app`, SQLAlchemy ve PostgreSQL 17 kullanir.
Windows ilk kurulum, Docker, yedekleme ve baslatici rehberi:
[Kurulum](../../docs/KURULUM.md).

Backend dizininde yeni Python ortami icin:

```powershell
python -m venv .venv-fastapi
.\.venv-fastapi\Scripts\python.exe -m pip install -r requirements-fastapi.lock.txt
```

Standart ilk kurulum proje kokundeki `FitGate-Kurulum.bat` ile yapilir.
Tek akis yeni `fitgate_local` PostgreSQL veritabanini, Alembic semasini ve
20 uye / 5 personelli ornek kayitlari hazirlar. Mevcut ayar, container veya
volume varsa durur; verileri silerek kurulumu zorlamayin.

Proje kokunden `FitGate-Baslat.bat` ve `FitGate-Durdur.bat` kullanilir.
React Windows :5174, FastAPI Windows :8001, PostgreSQL Docker :5433'tedir.
Arduino olmadan yonetim ekranlari calisir. Bridge icin yerel cihaz kaydi gerekir.

Alti yerel ornek hesabin giris bilgileri [README](../../README.md) icindedir; `.env.fastapi.example` yalnizca alan ornegidir.
Gercek env, sifreler, UID eslesmeleri ve yedekler dagitima dahil degildir.
Demo reset normal baslangicta calismaz. Firmware 7 test prototipidir;
[guvenlik ve derleme bayragi](../../docs/tek-sensor-prototip-testi.md).

`tools/import_backup.py` eski export bicimini okuyabilen istege bagli bir
aktarma aracidir; Django runtime gerektirmez. Otomatik baslangicta cagrilmaz.
Eski kurulumdan aktarim gerekiyorsa once yedek, ayri deneme ortami ve acik onay gerekir.

`tools/test_fastapi.py --isolated-demo-container` yalnizca onceden hazirlanmis
`fitgate-demo-test` / `127.0.0.1:5434` sunucusundaki `fitgate_fastapi_test`
veritabanini sifirlar. Test ayarlari sadece alt surecin ortaminda verilir;
mevcut `.env.fastapi` degistirilmez. Gercek veya standart kurulum hedefi reddedilir.
Ayrintilar [gelistirici testleri](../../docs/KURULUM.md#gelistirici-testleri) bolumundedir.
