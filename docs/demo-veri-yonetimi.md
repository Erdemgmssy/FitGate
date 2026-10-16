# Yerel Demo Verisi

Bu belge gelistirici ve tarihsel test araclari icindir. Normal kullanici kurulumu
`FitGate-Kurulum.bat` ile tek akistir; [guncel rehbere](KURULUM.md) bakin.

Bu arac uygulama baslangicinda otomatik calismaz. Uretimde yasaktir.
Asagidaki eski reset araci yalnizca development ortamindaki
`127.0.0.1:5433/fitgate` ve `fitgate-postgres` Docker konteynerini destekler.
Ayri ve veri silmeyen test yolu icin "Izole PostgreSQL 17.11 demo testi" bolumune bakin.

## Korunan Alanlar

- React tasarimi, FastAPI is kurallari, Arduino ve USB Bridge kaynaklari degismez.
- Tablo yapilari, foreign key/unique/check kisitlari, indeksler ve Alembic surumu korunur.
- Tum isletme, hesap, oturum ve gecis kayitlari birlikte transaction icinde temizlenir.
- Gercek fiziksel gecis, sensor olcumu, ziyaret veya otomatik mesai uretilmez.
- Paket satisi, dondurma, tahsilat, stok, ders ve vardiya icin mevcut servisler kullanilir.

## Yerel Dosyalar

`work/demo-reset/` Git disindadir. Windows izinleri mevcut kullanici ve SYSTEM ile sinirlanir.

- `config.json`: gercek RFID listesi, hedef, COM6 ve tek kullanimlik yerel silme izni.
- `Giris-Bilgileri.json`: dort hesabin benzersiz, rastgele uretilen gecici parolalari.
- `before-demo-*.dump.dpapi`: eski kisisel verileri de iceren sifreli geri donus yedegi.
- `reset-report.json`: temizlenen kayit sayisi ve yeni verilerin finansal dogrulamalari.
- `Eski-Veri-Dosyalari.json`: eski veri icerebilecek yerel dosyalar ve inceleme adaylari.
- `Eski-USB-Kuyrugu/`: eski olaylar tekrar gonderilmesin diye tasinan kuyruk ve WAL/SHM dosyalari.

DPAPI yedegi bu Windows hesabi ile cozulebilir; tasinabilir/parolali arsiv olarak kabul edilmemelidir.
Yedekleme bellek uzerinden yapilir; acik metin yeni PostgreSQL dump dosyasi diske yazilmaz.
Yedek ayri, gecici veritabanina geri yuklenir. Kayit sayilari ve schema dogrulanir;
gecici geri yukleme veritabani sonrasinda kaldirilir. Eski yedekler onay olmadan silinmez.

Gecici parolalar sohbet, kaynak kod veya test fixture'larina yazilmaz. Ilk giris sonrasi
Ayarlar uzerinden degistirilmelidir. Mevcut kimlik dogrulama altyapisinda zorunlu ilk-giris
parola degisimi bulunmadigindan bu arac bunu uygulanmis gibi gostermez.

## Calistirma

Once FitGate uygulamasini ve Bridge'i mevcut durdurma betigiyle kapatin.
Docker/PostgreSQL acik kalmalidir. Hedef veritabaninda baska baglanti varsa reset engellenir.
Komutlar `backend` dizininde calistirilir:

```powershell
# Yalnizca ayri fitgate_demo_seed_test veritabanini kullanir.
.venv-fastapi/Scripts/python.exe tools/demo_seed.py --test

# SADECE acikca onaylanan ilk yerel sifirlama icin.
.venv-fastapi/Scripts/python.exe tools/demo_seed.py --reset-local --confirm "RESET LOCAL FITGATE"
```

Gercek UID'ler kaynak kodda degil yerel `config.json` icinde bulunmalidir.
Silme icin bu dosyadaki `allowLocalReset` acikca `true` olmalidir; basaridan sonra `false` olur.
Demo isareti bulunan veritabaninda komut tekrar calistirilirsa kayitlar cogalmaz ve silinmez.
Eszamanli tekrar icin transaction kilidi ve ikinci isaret kontrolu bulunur.
`fitgate_demo_seed_test` de demo isaretinden sonra yeniden uretilmez.

Uygulamayi yeniden acarken Arduino testine hazir olana kadar yalnizca backend/frontend
servislerini baslatin. Bridge kaynaklari ve mevcut yerel cihaz anahtari degistirilmez;
cihaz kaydindaki anahtar hash'i mevcut yerel anahtarla eslestirilir.
Beklenen firmware bilgisi telemetri yerine gecmez: gercek surum/bilesen durumu baglaninca okunur.

## Dogrulama

```powershell
# backend
.venv-fastapi/Scripts/python.exe tools/test_fastapi.py -k DemoSeedTests

# frontend; mevcut yerel demo uzerinde sadece giris/okuma ve ekran kontrolu
node tests/demo-seed-smoke.cjs
```

Demo kontrolu hesaplari dosyadan okur; parolalari yazdirmaz. Test kaynaklarindaki UID'ler
tamamen sentetiktir. Screenshot dosyalari `outputs/` icindedir ve Git disindadir.

## Kart Test Senaryolari

- Demo Uye 01: aktif aylik sinirsiz; gercek giris yetkisi icin uygun.
- Demo Uye 02: aktif 10 seans; seans ancak gercek fiziksel girisle azalir.
- Demo Uye 03: suresi bitmis; giris reddi beklenir.
- Demo Uye 04: dondurulmus; giris reddi beklenir.
- Demo Resepsiyon, Demo Antrenor, Demo Salon Personeli: kendi personel profiline bagli kart.

Bu veriler donanim testi yapildigi anlamina gelmez. Personel otomatik mesaisi icin onayli
fiziksel gecis yaninda aktif vardiya da gerekir. Demo vardiyalari bugun ve sonraki iki gun
08:00-18:00 araligindadir. Uygun saat/plan yoksa mesai baslamamasi dogru davranistir.

Kurgusal telefonlar, NANPA'nin calismayan 555-0100..0199 araligindan secilir;
mevcut telefon dogrulamasi gevsetilmez: https://www.nanpa.com/numbering/555-line-numbers
E-postalar `example.com` alanindadir; bu kisiler icin SMS/e-posta gonderilmemelidir.
## Izole PostgreSQL 17.11 demo testi

Bu yol mevcut yerel kurulumdan ayridir. `tools/local_postgres.py`,
`tools/demo_seed.py --reset-local` ve `tools/test_fastapi.py` bu testte kullanilmaz.
Mevcut `.env.fastapi` degistirilmez; ayarlar yalnizca alt surecin ortaminda verilir.

`FITGATE_ISOLATED_DEMO_TEST=1` secildiginde demo kurucusu yalnizca su hedefi kabul eder:

- Yerel Windows Docker named-pipe baglami; uzak Docker reddedilir.
- Calisan `/fitgate-demo-test`, yalniz `127.0.0.1:5434:5432` baglantisi.
- Yalniz `fitgate-demo-test-data` adli Docker volume mount'lari.
- PostgreSQL, `fitgate` kullanicisi ve `127.0.0.1:5434/fitgate_demo`;
  URL sorgu parametreleri kabul edilmez.
- `ENVIRONMENT=development`, `DEMO_MODE=true`.

Backend dizininde, yukaridaki ayarlar ile `DATABASE_URL` ve ayri bir `SECRET_KEY`
surec ortamina guvenli olarak verildikten sonra:

```powershell
.venv-fastapi/Scripts/python.exe tools/demo_test.py
.venv-fastapi/Scripts/python.exe tools/demo_test.py --verify
```

Ilk komut migration oncesinde SQL sunucusunun sistem kimligini container icindeki
sunucuyla karsilastirir; surumun 17.11 oldugunu ve kullanici tablolarinin,
view'larin ve sequence'lerin bulunmadigini denetler. Beklenmeyen veri varsa durur.
Ardindan Alembic head ve portable demo seed uygulanir. Hicbir reset, truncate,
drop, container/volume olusturma veya silme komutu yoktur. Dolu veritabaninda ilk
komut tekrar calistirilmaz; `--verify` mevcut demo verisini denetler ve seed'in
tekrar cagrildiginda hicbir tabloyu degistirmedigini karsilastirir.

Test sunuculari icin backend `127.0.0.1:8014`, frontend `127.0.0.1:5184`
kullanilir. Backend `ALLOWED_ORIGINS` bu adresleri icermeli; frontend surecinde
`FITGATE_API_PROXY=http://127.0.0.1:8014` verilmelidir. Vite `--strictPort`
ile baslatilir. Donanim simulasyon bayraklari kapali tutulur.

Frontend dizininde `node tests/isolated-demo-smoke.cjs` altisi da olmak uzere
demo hesaplarinin API/form girislerini, rol kapsamini, admin ekranlarini,
oturumun yenilemeden sonra korunmasini ve mobil gorunumu denetler.
Raporlar ve ekran goruntuleri Git disindaki `work/isolated-demo/` altindadir.
Tum demo hesaplarinin parolasi `FitGateDemo2026!`; admin `admin@fitgate.demo`,
calisanlar `personel1@fitgate.demo` ... `personel5@fitgate.demo` adresleridir.
`personel2` antrenordur. Test bitince container, volume ve demo verisi korunur.
