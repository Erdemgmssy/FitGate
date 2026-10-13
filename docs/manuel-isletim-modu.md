# FitGate Manuel Isletim Modu

## Kullanma

1. Admin: Giris-Cikis > Manuel islemler. Resepsiyon: Giris Terminali > Manuel Islem Modu.
2. Uye adini, numarasini veya telefonunu arayin; uyeyi secin.
3. Paket, tarihler, kalan seans ve ziyaret durumunu kontrol edin.
4. Manuel Giris veya icerideki uye icin Manuel Cikis secin.
5. Gerekceyi ve varsa cihaz ariza aciklamasini yazin. Kisinin gercek giris/cikisini bizzat dogruladiginizi onaylayin.
6. Kaydedilen ziyaret mevcut iceridekiler listesine ve manuel gecmisine yansir.

Standart giris; aktif uye, engel/dondurma, gecerli paket, gun/saat, seans,
gunluk/haftalik limit, salon takvimi, borc engeli ve kapasite kurallarini kullanir.
Kart veya cihaz gerekmez. Birden fazla paket mevcutsa otomatik RFID akisindaki
ayni uygun paket secim kurali uygulanir. Basarili standart giriste sinirli paketten
bir seans duser. Cikista seans dusmez; bitmis uyelik cikisi engellemez.

Admin istisnasi ayri islem ve ayri onay gerektirir. Uyeligi aktiflestirmez, paket
secmez, seans dusmez; kapasite/bekleyen gecis/tutarsiz ziyaret korumasini asmaz.
Istisna gerekcesi denetim gunlugunde saklanir.

## Yetkiler ve personel

- Admin yetkilidir. Calisan icin Ayarlar > Rol Yetkileri bolumunde
  `manualVisits` ve `memberManagement` acik olmali. Yeni `manualVisits` izni
  varsayilan olarak kapalidir; mevcut rol politikalari otomatik genisletilmedi.
- Manuel mesai icin `manualAttendance`, mola icin ayrica `attendanceBreak`
  izni gerekir. Personel ve Mesai ekraninda Mesai Baslat, Molaya Cik,
  Moladan Don ve Mesai Bitir islemleri gerekce/onayla yapilir.
- Calisan yalnizca kendi kaydini isler; admin personel secebilir. Baslangicta
  etkin calisma vardiyasi, izin/tatil ve acik mesai kontrolleri uygulanir.
- Mesai/mola hareketleri `MANUAL_PERSONNEL` olarak mevcut AttendanceEvent,
  Shift ve ShiftBreak kayitlarina yazilir. PersonelVisit veya Passage uretilmez.
  Ucretli/ucretsiz mola ve gece vardiyasi mevcut hesaplamalari kullanir.
- Cihazla baslamis mesai manuel olarak bitirilebilir. Ilk kaynak degistirilmez;
  manuel bitis AttendanceEvent ve denetim kaydinda ayrilir. Fiziksel personel
  ziyareti kendiliginden kapanmaz: salon varligi ve ucretli calisma ayridir.
- Eski mesai kayitlari ve mevcut duzeltme API'leri geriye uyum icin korunur.

## Kayit ve emniyet

- Mod secimi yalnizca terminalin gorunumunu degistirir; cihaz modunu, kartlari,
  acik ziyaretleri veya mevcut kayitlari degistirmez. Bagli cihazin otomatik
  servisi calismaya devam edebilir; mode gecisi turnikeyi kapatmaz.
- Manuel islem DeviceCommand/Grant/Passage yaratmaz; servo acma veya zorla
  kapatma komutu yoktur. Mekanik emniyet ve acil tahliye bagimsizdir.
- Giris yontemi `Visit.method`, cikis yontemi `Visit.exit_method` alaninda
  saklanir. Personel, gerekce ve paket baglantisi da mevcut Visit modelindedir.
- `MANUAL`, `RFID`, `ADMIN_CORRECTION` ve mevcut tek-sensor prototip etiketi
  ayri tutulur. Manuel kayit tam fiziksel gecis kaniti olarak sunulmaz.
- Acik RFID izni bitmeden ayni kisiye manuel islem yapilmaz. Ayni subenin
  transaction kilidi ve mevcut OperationReceipt idempotency altyapisi cift
  ziyaret/seans tuketimini onler. Manuel kayittan hemen sonraki RFID okumasi
  10 saniyelik tekrar korumasina tabidir.
- Admin manuel ziyaret zamanlarini cakisma/gelecek tarih kontrolleriyle
  duzeltebilir. Eski degerler Audit.before/after icinde kalir. Duzeltme seansi,
  borcu veya tahsilati otomatik degistirmez. Cihaz olayi bulunan ziyaretler bu
  zaman duzeltme islemine alinmaz; mevcut gerekceli cikis duzeltmesi korunur.
- Dashboard dolulugu manuel acik ziyaretleri icerir. Gunluk toplamda fiziksel
  ve manuel sayilar ayri yazilir; yogunluk grafigi fiziksel kayitlarla kalir.
  Raporlar > Gecisler > Manuel islemler/admin duzeltmeleri; personel, gerekce,
  giris, cikis ve donem sonu manuel iceride sayisini ayri gosterir.

## Migration ve veri koruma

`b821d74ea39c_manual_operations` migration'i mevcut `gym_visit` tablosuna
paket, giris/cikis personeli, gerekce ve cikis yontemi ekler; cihaz baglantisini
manuel ziyaret icin nullable yapar. Yeni bir ziyaret/mesai tablosu yoktur.
Yeni provenance kaydi varken veri kaybettirecek downgrade reddedilir.

Migration oncesinde sifreli, yerel Windows kullanicisina bagli DPAPI yedek
alinip ayri PostgreSQL veritabaninda geri yukleme dogrulandi. Yedek yerel
`work/demo-reset` klasorunde, Git disinda tutulur. Gizli anahtar/UID yazdirilmadi.

Backend ve Bridge kisa sureli durdurularak 43 tablonun eski sutunlari icin satir
sayilari ve SHA-256 veri parmak izleri karsilastirildi: fark yok. 24 uye,
3 personel, 4 hesap, 4 uye karti + 3 personel karti, 21 uyelik, 21 satis/borc
ve 17 tahsilat korunuyor. Stok/ders ve diger tablolar da ayni kontrolu gecti.
Servisler geri acildi; Firmware 7 yuklenmedi veya degistirilmedi.

## Test raporu - 13 Ekim 2026

- 160 farkli backend testi basarili; tekrar calistirilanlar bu sayida bir kez
  sayildi. 21'i yeni ManuelOperationsTests testidir.
- Kapsam: manuel islemler, uyelik/paket, personel, raporlar, tek-sensor
  prototipi, unified hardware API, servis/regresyon, panel yetkileri ve ayarlar.
- Tamamen ayri `fitgate_fastapi_test` PostgreSQL veritabani kullanildi.
  Canli veritabanina test uyesi, ziyaret, mesai veya tahsilat eklenmedi.
- HTTP uzerinden giris, state yenileme ve cikis; idempotency; iki ayri
  transaction'da eszamanli RFID/manuellik; seans/limit; gece vardiyasi;
  ucretli/ucretsiz mola ve personel rapor tutarliligi test edildi.
- Son odakli backend grubu: ManuelOperationsTests + ReportTests, 40/40.
- 27 frontend birim testi basarili: personel, uyelik, rapor, panel yetkileri,
  guvenli islem/idempotency ve API yenileme/zaman asimi.
- 14 Playwright kontrolu basarili: admin, resepsiyon, yetkisiz rol, cevrimdisi
  cihaz, onay formlari, mod degisiminde ziyaretin korunmasi, giris/cikis ve
  dort mesai adimi. Masaustu 1440px ve mobil 390px goruntuleri incelendi.
- Playwright testleri sentetik UI fixture'lariyla calisir; canli kayitlari
  degistirmez. Backend/PostgreSQL dogrulamasi yukaridaki ayri testlerdedir.
- React uretim derlemesi basarili. Mevcut lucide/Vite `use client` ve
  Starlette/httpx deprecation uyarilari var; test/derleme hatasi yok.
- Firmware, USB Bridge kaynaklari degistirilmedi. Yeni fiziksel RFID/servo/
  sensor testi yapilmadi. Firmware baglantisi/telemetrisi goruldu; bu, mekanik
  gecisin basarili oldugu iddiasi degildir.
- Tam proje paketi, finans/stok/derslerin tum testleri ve Bridge yazilim
  testleri bu degisiklik icin yeniden calistirilmadi. Ilgili entegrasyonlar
  odakli paketlerde dogrulandi; ilgisiz moduller degistirilmedi.
- Frontend 5174, FastAPI 8001, PostgreSQL 5433 ve Bridge hazir. Bridge kullanici
  guvenlik onayi sonrasinda yeniden acildi. Commit, staging veya push yok.
