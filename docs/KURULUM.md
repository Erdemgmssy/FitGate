# FitGate Windows Kurulumu

## Mimari ve Gereksinimler

React/Vite, FastAPI ve Python USB Bridge Windows üzerinde çalışır.
Docker Desktop yalnızca PostgreSQL 17'yi çalıştırır; Docker Compose dosyası yoktur.

Doğrulanan yerel ortam: Python 3.10.11, Node 20.19.6, Windows PowerShell 5.1.
FastAPI minimum Python 3.10 ister; kilitli Vite'ın Node gereksinimi
`^20.19.0 || >=22.12.0` şeklindedir. Diğer sürümler ayrıca doğrulanmalıdır.
Docker Desktop Linux konteyner motorunu, Git'i ve npm'i hazır edin.

| Bileşen | Yerel adres / ayar | Kaynak |
|---|---|---|
| React | `127.0.0.1:5174` | `start-frontend.ps1` |
| FastAPI | `127.0.0.1:8001` | `start-backend.ps1` |
| API proxy | `http://127.0.0.1:8001` | `frontend/vite.config.mjs` |
| PostgreSQL | `127.0.0.1:5433` → konteyner 5432 | `.env.fastapi` / ilk kurulum aracı |
| Arduino | Örnek port COM6, 115200 baud; kendi portunuzu doğrulayın | yerel `backend/hardware/.env` |

`FitGate-Launcher.ps1` port parametreleri testler içindir; manuel servis betikleri
ve Vite proxy günlük kullanımda yukarıdaki portları kullanır. Bir portu değiştirmek
gerekirse ilgili tüm ayarları birlikte değerlendirin.

## İlk Kurulum

### Otomatik boş veya demo kurulum

Docker Desktop Linux motorunu açıp proje kökünde `FitGate-Kurulum.bat` çalıştırın.
Betik Python >=3.10, Node 20.19+ / 22.12+ veya daha yeni ana sürüm, npm, Git ve
yerel Docker Desktop gereksinimlerini kontrol eder; kilitli Python ve React
bağımlılıklarını yükler. Aşağıdaki manuel adımlar alternatif kurulum yoludur.

- **1 – Boş:** yeni `fitgate` veritabanı, Alembic şeması ve interaktif admin hesabı.
- **2 – Demo:** yeni `fitgate_demo` veritabanı, Alembic şeması ve sahte kayıtlar.

Her iki seçenek aşağıda açıklanan container, volume ve port adlarını kullanır.
Mevcut `.env.fastapi`, Docker parola dosyası, container veya volume bulunursa
kurulum durur; silme, sıfırlama veya üzerine yazma yapmaz. Tekrar çalıştırmak
mevcut veritabanını migrate etmez. Günlük kullanımda `FitGate-Baslat.bat` kullanın.
DATABASE_URL, SECRET_KEY veya ENVIRONMENT ortam değişkenleri kurulum hedefini
değiştirebildiği için betik bunlar tanımlıyken de durur.

Demo; 20 üye, 5 personel, 5 paket, farklı durumlarda üyelikler, fatura, taksit,
ödeme, kasa, tedarikçi, 6 ürün, stok, satış, vardiya, izin, ders ve rezervasyon içerir.
Geçmiş 5 mesai ve olayları `simulation` olarak işaretlenir; fiziksel geçiş kanıtı
değildir. Cihaz oluşturulmaz. Kartlar `DEMO-MEMBER-*` ve `DEMO-STAFF-*` biçiminde
kurgusal etiketlerdir; gerçek RFID kullanılmaz.

Parametresiz demo kurucusunun hesapları `admin.demo@example.com`, `reception.demo@example.com`,
`trainer.demo@example.com`, `floor.demo@example.com`, `sales.demo@example.com`,
`support.demo@example.com` adresleridir. Her hesabın parolası kurulum sırasında
gizli giriş ve onayla alınır (en az 12 karakter); dosyaya yazılmaz. Mevcut Argon2
hash işlevi ve rol politikaları kullanılır. Varsayılan yönetici parolası yoktur.

Otomatik kurulumda **2 – Demo** seçimi `DEMO_MODE=true` yazar ve
`install_demo.py --local-demo-accounts` çağırır. Bu açık seçimde kullanılan altı
hesap ve yalnızca yerel test şifreleri [README](../README.md#demo-giriş-bilgileri)
bölümündedir. Demo modu varsayılan olarak kapalıdır; üretim ve `fitgate` hedefi
reddedilir. Boş kurulum admin parolasını istemeye devam eder.

Dağıtım yöntemi **Alembic + seed**'dir; dump gerekmez. Gerçek veritabanından
otomatik yedek veya veri kopyası alınmaz. `tools/install_demo.py` yalnızca
development ortamında yerel PostgreSQL `fitgate_demo` hedefini kabul eder.
Migration sonrası uygulama tablolarının boşluğu kilit altında doğrulanır.
Veriler tek transaction içinde üretilir; hata geri alınır. Demo işareti varsa
tekrar çalıştırma kayıt çoğaltmaz veya parolaları değiştirmez. Başka veri varsa durur.

Yarım kalan kurulumda dosya veya volume silmeyin. Hatanın nedenini çözün.
Yerel bağlantının **kendi yeni kurduğunuz** veritabanına ait olduğunu doğruladıktan
sonra backend dizininde `python -m alembic upgrade head` ve demo için
`python tools/install_demo.py`, boş kurulum için `python tools/create_admin.py`
komutlarını `.venv-fastapi\Scripts\python.exe` ile çalıştırarak tamamlayın.
Mevcut işletme veritabanında bu tamamlama adımlarını uygulamayın.

FitGate deposu PUBLIC'tir; indirmek için GitHub hesabı gerekmez.
Windows PowerShell'de aşağıdaki komutları çalıştırın:

```powershell
git clone https://github.com/Erdemgmssy/FitGate.git
cd FitGate
cd backend
python -m venv .venv-fastapi
.\.venv-fastapi\Scripts\python.exe -m pip install -r requirements-fastapi.lock.txt
cd ..\frontend
npm ci
cd ..
```

FastAPI kilit dosyası aktif bağımlılıkları ve Excel için `openpyxl`/`et_xmlfile`
sürümlerini içerir. Django, SQL Server ve ODBC yeni kurulum için gerekmez;
eski uygulama ve bağımlılık kilidi bu temiz dağıtıma dahil değildir.

Docker Desktop'ı açın; motor hazır olduktan sonra **yalnızca ilk, verisiz kurulumda**:

```powershell
cd backend
.\.venv-fastapi\Scripts\python.exe tools/local_postgres.py
.\.venv-fastapi\Scripts\python.exe -m alembic upgrade head
.\.venv-fastapi\Scripts\python.exe tools/create_admin.py
cd ..
```

`local_postgres.py` yalnızca yerel Windows Docker Desktop bağlamını kabul eder.
Mevcut `.env.fastapi`, Docker parola dosyası, `fitgate-postgres` konteyneri veya
`fitgate-postgres-data` volume'ü bulunursa **hiçbir yapılandırmayı yazmadan durur**.
Bu durumda eski `.env.fastapi` ve veritabanı parolasını güvenli yedekten koruyun;
mevcut veriyi silerek kurulumu zorlamayın. `.env.fastapi` dosyasını silmek parola sıfırlama yöntemi değildir.

Yeni kurulumda araç rastgele güçlü parola ve imza anahtarı oluşturur:

- `backend/.env.fastapi`: FastAPI bağlantısı ve imza ayarı.
- `backend/backups/postgres-docker.env`: ilk konteyner oluşturma ayarı.
- Konteyner: `fitgate-postgres`, imaj: `postgres:17`.
- Port: yalnızca `127.0.0.1:5433:5432`.
- Volume: `fitgate-postgres-data`, hedef: `/var/lib/postgresql/data`.

Değerler terminale yazdırılmaz. Bu dosyaları paylaşmayın. Docker parolasını sonradan
yalnızca env dosyasında değiştirmek mevcut PostgreSQL rolünün parolasını değiştirmez.

### Örnek Env Dosyaları

`.env.fastapi.example` gerçek değer içermez; alanları anlamak için referanstır.
Otomatik yerel kurulumdan **önce** bunu `.env.fastapi` olarak kopyalamayın;
kurulum aracı mevcut dosyayı korumak için durur.

Alternatif/önceden hazırlanmış veritabanında örneği `.env.fastapi` olarak kopyalayın,
bağlantı ve en az 48 karakterlik rastgele `SECRET_KEY` değerini yerel editörde doldurun.
Parola/secret üretimini veya değerlerini sohbete ve Git'e taşımayın.
Tek tıkla başlatıcı yalnızca adı belirli yerel Docker PostgreSQL kurulumunu destekler;
harici veritabanı için FastAPI'yi doğrudan çalıştırıp kendi işletim planınızı kullanın.

Yeni admin hesabı `create_admin.py` ile interaktif oluşturulur; varsayılan parola yoktur.
Araç admin e-posta adresi, ad, en az 12 karakterlik parola ve parola onayını ister.
Boş veritabanında salon/şube adını da sorar. İlk girişte bu e-posta ve parolayı kullanın.
Mevcut hesaplar varsa script aynı e-postayla hesabı değiştirmez. Aktif hesap veya
oturum sıfırlaması kurulum adımı değildir.

## Günlük Başlatma ve Durdurma

1. Docker Desktop'ı açın.
2. `FitGate-Baslat.bat` dosyasına çift tıklayın.
3. Tarayıcı: http://127.0.0.1:5174/.

BAT dosyası Windows PowerShell 5.1 başlatıcısını çağırır; global execution policy
değişmez. Yönetici yetkisi istenmez. Docker motoru kapalıysa kurulu Docker Desktop
gizli pencereyle başlatılabilir; hazır olması sınırlı süre beklenir. Konteyner yoksa
hata verilir, yeni/verisiz konteyner oluşturulmaz. Duran mevcut konteyner başlatılır.
FastAPI'nin gerçek SQL sağlık yanıtı ve React sayfası doğrulanmadan tarayıcı açılmaz.

Başlatıcının varsayılan hazır olma süresi 120 saniyedir; beklemeler sınırlıdır.
Tekrar başlatma yeni süreç çoğaltmaz. USB ayarı varsa tek Bridge yönetilir; USB yokken
Bridge yeniden bağlantıyı dener ve web uygulamasının çalışması buna bağlı değildir.

`FitGate-Durdur.bat` sadece başlatıcının sahipliğini doğrulayabildiği Windows job
süreçlerini ve alt süreçlerini kapatır. PID yeniden kullanımı/eski kayıt durumunda
başka uygulamaları kapatmaz. Docker ve PostgreSQL varsayılan olarak açık kalır.

PostgreSQL'i ayrıca durdurmak gerekiyorsa önce tüm uygulama/test istemcilerini kapatın,
ardından **açıkça ve ayrı bir işlem olarak** `docker stop fitgate-postgres` kullanın.
Bu normal Durdur dosyasının bir parçası değildir. Volume silinmez.

### Manuel Servisler

Proje kökünde üç ayrı Windows PowerShell terminali:

```powershell
.\start-backend.ps1
.\start-frontend.ps1
.\start-bridge.ps1
```

Backend betiği ortak başlatıcıdaki Docker/PostgreSQL kontrolünü kullanır, Alembic'i
uygular ve Uvicorn'u başlatır. Frontend `--strictPort` kullanır. Bridge için yerel
cihaz ayarı gerekir. Bunları tek tıkla servisler açıkken ikinci kez çalıştırmayın.
Elle açılan süreçleri kendi terminalinde `Ctrl+C` ile kapatın; başlatıcı başka sahibin
süreçlerini devralıp kapatmaz.

## Arduino ve USB Bridge

Arduino zorunlu değildir. Manuel işletim yetkileri rol politikasından açılır;
manuel kayıt servo komutu veya sensör kanıtı üretmez.

İlk cihaz kaydı için backend dizininde:

```powershell
.\.venv-fastapi\Scripts\python.exe tools/register_usb_device.py --help
```

Mevcut cihazı yeniden kaydetmeyin. `backend/hardware/.env.example` boş anahtarlı güvenli
örnektir. Kayıt aracı yerel `.env` ve mevcut cihazın hash eşleşmesini yönetir.
COM portunu Aygıt Yöneticisi'nden bulun; COM6 her bilgisayarda sabit değildir.
Seri Monitor ve aynı porta bağlı ikinci Bridge kapalı olmalıdır.

Firmware 7 yalnızca development ortamında, belirli cihaz ve iki tarafta açık izinle
çalışan tek-sensör prototipidir. Varsayılan örnekler prototipi kapalı tutar.
Derleme bayrağı ve güvenlik adımları [prototip belgesinde](tek-sensor-prototip-testi.md).
Bağlama/reset/yükleme servo hareketine neden olabilir; uygun besleme, RC522 seviye
dönüşümü ve güvenli hareket alanı zorunludur. Bu doküman firmware yüklemez.

## Veritabanı ve Yedekleme

Günlük başlangıçta seed/reset çağrılmaz. Yeni demo kurulumu `install_demo.py`
kullanır. `demo_seed.py` eski, cihaza bağlı araçtır; yalnızca açıkça onaylanan
yerel test için ayrı bir araçtır; normal kurulumda kullanmayın. PostgreSQL kayıtları
Alembic ve transaction'larla yönetilir; bu dağıtımdaki Alembic migration'ları
aktif PostgreSQL şemasının kaynağıdır.

Yedek aracı, backend dizininden:

```powershell
.\.venv-fastapi\Scripts\python.exe tools/backup_postgres.py --verify-restore
```

Yedek mevcut korumalı `backend/backups/system/` klasörüne alınır; geri yükleme
doğrulaması ayrı geçici veritabanındadır, canlı veriye uygulanmaz. Bu `.dump`
dosyası **şifreli değildir**; paylaşmadan/başka diske taşımadan onaylı şifreleme ve
erişim kısıtları kullanın. Önceki kurulumun yerel yedekleri bu dağıtıma dahil
değildir. Mevcut kurulumdaki yedekleri silmeyin.

Migration öncesi yedek/geri yükleme planı gerekir; downgrade veri kaybettirebilir.
Normal kurulum mevcut veriyi sıfırlamamalıdır. `docker volume rm`, `docker rm -v`
ve silme/reset araçları günlük bakım komutları değildir.

## Testler

Proje kökünden, canlı üyelerle test işlemi yapmadan:

```powershell
.\backend\.venv-fastapi\Scripts\python.exe -m unittest discover -s tests/security -v
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/launcher/Test-Launcher.ps1
cd backend
.\.venv-fastapi\Scripts\python.exe tools/test_fastapi.py
.\.venv-fastapi\Scripts\python.exe -m unittest discover -s hardware -p test_bridge.py
cd ..\frontend
npm test
npm run build
```

`test_fastapi.py` yalnızca ayrı `fitgate_fastapi_test` veritabanını sıfırlar.
Bridge birim testleri gerçek COM portu açmaz. Başlatıcı testi ayrı örnek süreçler
ve 18001/15174/18106 portlarını kullanır; PostgreSQL hazır olmasını kontrol eder,
canlı iş kaydı yazmaz. Donanım bağlı/bağlı-değil fiziksel adımlar kullanıcıyla ayrıca doğrulanır.

## Sorun Giderme

| Sorun | Kontrol |
|---|---|
| Docker yok/kapalı | Docker Desktop kurulu mu, Linux motoru hazır mı? Başlatıcı hata verirse önce motor ekranını kontrol edin. |
| PostgreSQL hatası | `docker ps -a --filter name=fitgate-postgres`; yerel `.env.fastapi` ile eski konteyner ayarı eşleşiyor mu? Secret yazdırmayın. |
| 5433 dolu | `Get-NetTCPConnection -LocalPort 5433`; diğer veritabanını öldürmeyin, port sahibini belirleyin. |
| FastAPI açılmıyor | `.venv-fastapi`, kilitli paketler, env ve `work/fitgate-launcher/backend.log`; migration hatası varsa veri silmeyin. |
| React açılmıyor | Node sürümü, `npm ci`, 5174 port sahibi ve `frontend.log`; strict port başka porta sessiz geçmez. |
| COM portu yok | USB sürücüsü/kablo, Aygıt Yöneticisi, doğru port; Arduino yokken web ekranları kullanılabilir. |
| Bridge açılamıyor | Yerel cihaz ayarı, Seri Monitor/ikinci Bridge, `bridge.log`; API ve React açık kalır. |
| Süreç çakışması | Bir başlatma işleminin bitmesini bekleyin; eski PID kaydı nedeniyle diğer programlara dokunmayın. |

Günlükler kişisel veri/UID içerebilir; ham günlükleri GitHub'a veya sohbete koymayın.
Yerel geliştirme sunucusunu internete açmayın; üretim HTTPS, secret/cookie,
veritabanı izinleri ve fiziksel emniyet için ayrı kurulum incelemesi gerektirir.
