# FitGate

Windows üzerinde yerel çalışan, **React + FastAPI + PostgreSQL** tabanlı bir
spor salonu yönetim sistemi. Üyelikleri, ödemeleri ve günlük salon işlemlerini
tek arayüzden yönetmek için geliştiriliyor.

## Özellikler

- Üye kaydı, üyelik paketleri, yenileme ve dondurma.
- Borç, taksit, tahsilat ve iade takibi.
- Personel, vardiya, izin ve mesai yönetimi.
- Ders ve randevu rezervasyonları.
- Ürün, stok ve satış işlemleri.
- Raporlar, bildirimler ve rol bazlı admin/çalışan ekranları.
- Yetkili manuel giriş-çıkış ve isteğe bağlı Arduino/RFID prototipi.

## Teknolojiler

Arayüz React/Vite, API Python/FastAPI, veritabanı PostgreSQL 17'dir.
SQLAlchemy ve Alembic veri erişimi ve şema yönetimi için kullanılır.
**Yalnızca PostgreSQL Docker Desktop'ta çalışır;** React, FastAPI ve isteğe
bağlı Python USB Bridge Windows üzerinde çalışır.

## İlk Kurulum

Windows PowerShell 5.1, Git, Python 3.10+, Node.js ve Docker Desktop gerekir.
Node.js sürümü kilitli Vite paketine uygun olmalıdır; sürüm ayrıntıları ve
alternatif kurulum için [Windows kurulum rehberine](docs/KURULUM.md) bakın.

Docker Desktop'ın Linux konteyner motorunu açın. **Yeni ve verisiz bir kurulumda**
Windows PowerShell üzerinden:

```powershell
git clone https://github.com/Erdemgmssy/FitGate.git
cd FitGate\backend
python -m venv .venv-fastapi
.\.venv-fastapi\Scripts\python.exe -m pip install -r requirements-fastapi.lock.txt
.\.venv-fastapi\Scripts\python.exe tools/local_postgres.py
.\.venv-fastapi\Scripts\python.exe -m alembic upgrade head
.\.venv-fastapi\Scripts\python.exe tools/create_admin.py
cd ..\frontend
npm ci
cd ..
```

Kurulum aracı yerel bağlantı ayarlarını oluşturur. `.env.fastapi.example`
dosyasını bu adımdan **önce** gerçek env dosyasına kopyalamayın. Mevcut FitGate
ayarları, konteyneri veya volume'ü varsa kurulum durur; bunları silmeyin.
Admin bilgileri interaktif istenir; varsayılan parola ve otomatik demo seed yoktur.
İlk girişte oluşturduğunuz admin e-posta adresi ve parolayı kullanın.

## Çalıştırma

Proje kökündeki `FitGate-Baslat.bat` dosyasına çift tıklayın ve
[yerel arayüzü](http://127.0.0.1:5174/) açın. Docker Desktop açık olmalıdır.
`FitGate-Durdur.bat` uygulama süreçlerini durdurur; PostgreSQL açık kalır.
Arduino olmadan yönetim ekranları kullanılabilir.

## Ekran Görüntüleri

Henüz yayıma uygun, kişisel veri içermeyen ekran görüntüleri eklenmedi.

## Kapsam ve Sınırlar

Proje yerel geliştirme ve donanım prototipi içindir. Üretim güvenliği, ticari
kullanıma hazır olma veya fiziksel geçiş garantisi iddia edilmez. Firmware 7'nin
tek sensörlü test modu tam fiziksel geçiş kanıtı değildir. Servo ve sensörler
güvenlik sertifikalı bir turnike sistemi oluşturmaz.

Gerçek env, parolalar, kullanıcı verileri, RFID eşleştirmeleri ve veritabanı
yedekleri depoya eklenmemelidir. Kodu yerel olarak çalıştırmak, veri toplama ve
işletme kullanımına ilişkin gereklilikleri yerine getirdiğiniz anlamına gelmez.

## Belgeler

- [Kurulum, testler ve sorun giderme](docs/KURULUM.md)
- [Backend kullanım notları](backend/README.md)
- [Arduino tek sensör prototipi](docs/tek-sensor-prototip-testi.md)
- [Manuel giriş-çıkış ve mesai](docs/manuel-isletim-modu.md)
