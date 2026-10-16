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

Docker Desktop Linux motorunu açıp proje kökünde `FitGate-Kurulum.bat` çalıştırın.
Kurulum tek akıştır: kilitli Python/React bağımlılıkları, yeni PostgreSQL 17,
Alembic şeması ve kurgusal örnek kayıtlar otomatik hazırlanır. Sonra
`FitGate-Baslat.bat` çalıştırın. [Altı hazır hesap README’dedir](../README.md#hazır-kayıtlar-ve-giriş).

20 üye, 5 personel, 5 paket, farklı üyelik durumları, fatura, taksit, ödeme, kasa,
tedarikçi, 6 ürün, stok, satış, planlı vardiya, izin, ders ve rezervasyon yüklenir.
Beş geçmiş mesai simülasyondur. Fiziksel cihaz oluşturulmaz; kart etiketleri
`DEMO-MEMBER-*` ve `DEMO-STAFF-*` biçiminde kurgusaldır.

| Kaynak | Değer |
|---|---|
| Container / imaj | `fitgate-postgres` / `postgres:17` |
| Veritabanı / kullanıcı | `fitgate_local` / `fitgate` |
| Bağlantı | yalnızca `127.0.0.1:5433:5432` |
| Volume | `fitgate-postgres-data` → `/var/lib/postgresql/data` |
| Yerel ayarlar | `backend/.env.fastapi` |
| Docker parola dosyası | `backend/backups/postgres-docker.env` |

Veritabanı parolası ve imza anahtarı rastgele oluşturulur; terminale yazdırılmaz.
Bu dosyaları paylaşmayın. Her bilgisayar kendi veritabanı ve volume’üne sahiptir.
Alembic + örnek veri üreticisi kullanılır; dağıtım için dump oluşturulmaz.

Mevcut ayar, parola dosyası, container veya volume varsa **kurulum durur**;
silme, reset veya üzerine yazma yapılmaz. Günlük kullanımda Başlat dosyasını kullanın.
Kurulum hedefini değiştirebilecek uygulama ortam değişkenleri varsa da işlem durur.

Örnek veri yükleyicisi yalnızca `ENVIRONMENT=development`, `LOCAL_SAMPLE_DATA=true`,
`127.0.0.1:5433/fitgate_local`, doğru yerel Docker container/volume eşleşmesini
kabul eder. TCP bağlantısının SQL sistem kimliği container içinden okunanla
karşılaştırılır. PostgreSQL 17 ve boş veritabanı doğrulanmadan Alembic çalışmaz.
Ardından veriler tek transaction’da oluşturulur; dolu tablolar değiştirilmez.
Mevcut `fitgate` ve test amaçlı `fitgate_demo` standart kurucuda reddedilir.
Üretim ortamında herkese açık hesaplarla kurulum ve örnek veri profiliyle
uygulama başlangıcı engellenir.

Yarım kalan kurulumda dosya veya volume silmeyin. Günlüklerden hatayı belirleyin;
kurulumun tamamını tekrar çalıştırmak mevcut kaynakları değiştirmez. Tamamlama
adımları hedefin kimliği, migration durumu ve kayıtları incelendikten sonra
ayrıca planlanmalıdır; mevcut veritabanına genel seed/reset uygulamayın.

`.env.fastapi.example` yalnızca alan referansıdır. Otomatik kurulumdan önce
`.env.fastapi` olarak kopyalamayın. Eski ayarlarınızı yeni örnekle değiştirmeyin.
`tools/create_admin.py` interaktif ayrı bir bakım aracıdır; standart ilk kurulumun
parçası değildir.

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

Günlük başlangıçta seed/reset çağrılmaz. Standart ilk kurulum `install_sample.py`
ile Alembic ve örnek verileri hazırlar. `demo_seed.py` eski, cihaza bağlı araçtır; yalnızca açıkça onaylanan
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

## Geliştirici Testleri

Proje kökünden, canlı üyelerle test işlemi yapmadan:

```powershell
.\backend\.venv-fastapi\Scripts\python.exe -m unittest discover -s tests/security -v
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/launcher/Test-Launcher.ps1
cd backend
.\.venv-fastapi\Scripts\python.exe tools/test_fastapi.py --isolated-demo-container
.\.venv-fastapi\Scripts\python.exe -m unittest discover -s hardware -p test_bridge.py
cd ..\frontend
npm test
npm run build
```

Backend regresyon komutundan önce yalnızca alt sürecin ortamında izole test
bağlantısını verin: `127.0.0.1:5434/fitgate_demo`, `fitgate` kullanıcısı,
`FITGATE_ISOLATED_DEMO_TEST=1`, `DEMO_MODE=true`, `LOCAL_SAMPLE_DATA=false`,
`ENVIRONMENT=development` ve ayrı bir test imza anahtarı. Mevcut `.env.fastapi`
dosyasını değiştirmeyin. Test container'ı önceden hazırlanmış olmalıdır.
`test_fastapi.py` artık açık bayrak ve yalnızca `fitgate-demo-test` container'ını
kabul eder; SQL sistem kimliğini doğrulamadan hiçbir reset çalıştırmaz. Yalnızca
bu sunucudaki ayrı `fitgate_fastapi_test` veritabanını oluşturur/sıfırlar;
`fitgate_demo` kayıtlarını korur. Gerçek `fitgate` ve standart `fitgate_local`
üzerinden çalıştırılması reddedilir. Test veritabanına gerçek kayıt koymayın.
Bridge birim testleri gerçek COM portu açmaz. Başlatıcı testi ayrı örnek süreçler
ve 18001/15174/18106 portlarını kullanır; Docker/PostgreSQL yanıtları geçici test
kopyasında taklit edilir, gerçek Docker kaynaklarına erişilmez. Donanım
bağlı/bağlı-değil fiziksel adımlar kullanıcıyla ayrıca doğrulanır.

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
