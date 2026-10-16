# FitGate

Windows üzerinde çalışan **React + FastAPI + PostgreSQL** tabanlı spor salonu yönetimi.
Üyelik, paket, ödeme, taksit, personel, mesai, ders, stok ve satış ekranlarını içerir.

## Kurulum

Windows PowerShell 5.1, Python 3.10+, Node.js 20.19+ veya 22.12+ (ya da daha yeni
uyumlu sürüm), npm, Git ve Docker Desktop gerekir. Docker Desktop’ın **Linux
container motorunu** açın.

```powershell
git clone https://github.com/Erdemgmssy/FitGate.git
cd FitGate
.\FitGate-Kurulum.bat
.\FitGate-Baslat.bat
```

ZIP indiriyorsanız arşivi çıkarıp aynı iki BAT dosyasını sırasıyla çalıştırın.
Kurulum tek akıştır; seçim veya hesap oluşturma sorusu yoktur. Kilitli bağımlılıklar
yüklenir, Docker üzerinde bağımsız **PostgreSQL 17** oluşturulur, Alembic tabloları
ve ilişkileri kurar, kurgusal örnek kayıtlar otomatik yüklenir. Dump dosyası gerekmez.
Her bilgisayarın verileri kendi yerel Docker volume’ünde tutulur.

Uygulamayı **http://127.0.0.1:5174/** adresinde açın. API belgeleri:
http://127.0.0.1:8001/docs. Sonraki kullanımlarda yalnızca `FitGate-Baslat.bat`
çalıştırılır. `FitGate-Durdur.bat` uygulama süreçlerini durdurur; veriler korunur.

**Mevcut `.env.fastapi`, container veya volume varsa kurulum durur.** Otomatik silme,
sıfırlama veya üzerine yazma yapılmaz. Bunları silerek kurulumu zorlamayın.
Kurulumdan önce `.env.fastapi.example` dosyasını kopyalamayın; yerel ayarlar ve
rastgele veritabanı parolası kurulumda oluşturulur.

## Hazır kayıtlar ve giriş

İlk açılışta **20 üye, 5 personel ve 6 hesap** hazırdır. Ayrıca 5 paket, farklı
üyelik durumları, faturalar, taksitler, ödemeler, kasa, 6 ürün, stok hareketleri,
satışlar, planlı vardiyalar, izinler, dersler ve rezervasyonlar bulunur.
Beş geçmiş mesai simülasyon olarak işaretlidir; gerçek fiziksel geçiş değildir.
Gerçek kişi, ödeme veya RFID verisi kullanılmaz. Arduino gerekli değildir.

| Rol | E-posta | Parola |
|---|---|---|
| Admin | admin@fitgate.demo | FitGateDemo2026! |
| Çalışan 1 | personel1@fitgate.demo | FitGateDemo2026! |
| Antrenör | personel2@fitgate.demo | FitGateDemo2026! |
| Çalışan 3 | personel3@fitgate.demo | FitGateDemo2026! |
| Çalışan 4 | personel4@fitgate.demo | FitGateDemo2026! |
| Çalışan 5 | personel5@fitgate.demo | FitGateDemo2026! |

Bu herkese açık hesaplar **yalnızca yerel örnek kurulum içindir**. Kurucu,
`ENVIRONMENT=development`, `LOCAL_SAMPLE_DATA=true`, yalnızca loopback’e bağlı
PostgreSQL ve yeni `fitgate_local` veritabanını zorunlu tutar. Gerçek `fitgate`
veritabanına örnek veri yüklemez. Üretimde bu hesaplarla kurulum reddedilir;
`LOCAL_SAMPLE_DATA=true` üretim ayarlarıyla uygulama da başlatılamaz.
Parolalar Argon2 ile hash’lenir. Bu dağıtım yerel kullanım içindir; internete açık
üretim kurulumu ayrıca yapılandırılmalıdır.

## Belgeler ve doğrulama

- [Windows kurulumu ve sorun giderme](docs/KURULUM.md)
- [Standart kurulum test raporu](docs/STANDART-KURULUM-RAPORU.md)
- [Backend](backend/README.md)
- [Manuel giriş-çıkış ve mesai](docs/manuel-isletim-modu.md)
- [Arduino prototipi](docs/tek-sensor-prototip-testi.md)

İzole test araçları normal kurulum akışına dahil değildir; geliştirici notları
[ayrı belgede](docs/demo-veri-yonetimi.md) tutulur. Temiz bir Windows bilgisayarda
uçtan uca kurulum henüz doğrulanmadı; test kapsamı ve sınırları raporda açıklanır.
Gerçek env dosyaları, kişisel kayıtlar, cihaz anahtarları ve yedekler GitHub’a eklenmez.
