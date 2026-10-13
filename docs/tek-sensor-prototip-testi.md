# Tek Sensor Prototip Testi

Bu mod gercek turnike guvenligi icin uygun degildir. HC-SR04 ve SG90 bir emniyet
sistemi degildir; algilama kisinin tamamen gectigini veya sensor sirasiyla yonunu kanitlamaz.
Hareket alanini bos tutun, uygun besleme ve RC522 3.3 V seviye donusumu kullanin.
Sensor okunamazken veya alan doluyken servo kapatma komutu verilmez; prototip acik
kalabilir. Sikisma riski olan duzenekte test etmeyin; enerjiyi kesme imkani hazir olsun.
USB baglama/flash okuma/yukleme UNO'yu resetleyebilir ve setup'ta servo hareket edebilir.

## Surum ve Yedek

- Yerel flash yedekleri bu kaynak dagitimina dahil degildir; onceki kurulumda korunur.
- Tek sensor derlemesi Firmware 7 prototipi olarak ayrilir. Normal derleme Firmware 6
  ve iki-sensor-sirali mantigi korur; varsayilan prototype derleme bayragi kapali.
- Firmware yalnizca kullanici onayiyla yuklenmelidir.

Arduino CLI ve arduino:avr cekirdegi ayrica kurulmalidir. COM portu ve cihaz
izinleri yeni kurulumda yerel olarak tanimlanir; bu dagitim bunlari etkinlestirmez.

```powershell
arduino-cli compile --fqbn arduino:avr:uno --build-property "compiler.cpp.extra_flags=-DFITGATE_SINGLE_SENSOR_PROTOTYPE=1" --output-dir outputs/arduino-single-sensor-prototype hardware/arduino/FitGateUno
```

## Onay Sonrasi Etkinlestirme

Yukleme/reset icin uygun besleme, seviye donusturucu ve guvenli servo alani tekrar
dogrulanmalidir. Seri Monitor kapali, Bridge durmus olmalidir.

Yalnizca yerel, Git disindaki ayarlarda:

- backend/.env.fastapi: ALLOW_SINGLE_SENSOR_PROTOTYPE=true
- backend/.env.fastapi: SINGLE_SENSOR_PROTOTYPE_DEVICE_CODE, hardware/.env icindeki mevcut DEVICE_CODE ile ayni.
- backend/hardware/.env: ALLOW_SINGLE_SENSOR_PROTOTYPE=true
- ENVIRONMENT=development olmali; production modunda ve baska cihaz kodunda API reddeder.

Backend yeni ayarlarla yeniden baslatilir. Onayli prototip HEX'i COM6'ya yuklendikten
sonra mevcut USB Bridge baslatilir. Yeni cihaz anahtari, yeni uyeler veya yeni DB reset'i
gerekmez. Uygulama http://127.0.0.1:5174/ adresinde acilir.

## Kesin Algilama Kurali

- Dis: TRIG D2 / ECHO D3. Ic: TRIG D4 / ECHO D5.
- <=20 cm algilama, >20 cm bos. 30 cm veya yon sirasi sarti yok.
- Sensorler akustik etkilesimi azaltmak icin donusumlu 60 ms aralikla okunur.
- Ayni sensorden ardarda iki gecerli yakin ornek gerekir; izin sonrasi filtre sifirlanir.
- RFID/FastAPI izni olmadan sensor olayi uye/personel kaydi olusturmaz.
- Giris/cikis yonu FastAPI acik ziyaretten belirlenir; belirsiz eski ziyaret reddedilir.
- Herhangi bir sensorden kararli yakin ornek gelince tek prototip olayi PC'ye gonderilir.
  Her iki sensor ayni anda yakin olsa da tek olay olur; ikinci sensor beklenmez.
- Diger sensorun uzak (>20 cm) degeri tetiklemeyi engellemez. Ancak iki sensorun da
  gecerli/guncel olmasi mevcut emniyet kontroludur; eksik/bozuk olcumde izin/olay reddedilir.
- Servo, kayit ile birlikte derhal kapanmaz: iki sensor de iki ornekle bos ve 250 ms
  kesintisiz bos olmali. Iki sensorun bosalmasi kayit icin degil sadece guvenli kapanma icindir.
- Yeni islem icin tetikleyen sensor(ler) yeniden bosalmali, servo kapanmali ve kart kaldirilmalidir.
- Algilama gelmezse 8 saniyede zaman asimi; yeni ziyaret ve seans dusumu yok.
  Sunucu izni 30 saniyede sona erer; zaman asimindan sonra yeni deneme icin onceki
  iznin bitmesini de bekleyin. Bekleyen izin korumasi devre disi birakilmaz.
- PC yeniden gonderimleri ayni olay/istek anahtarini kullanir; ikinci seans dusmez.
- USB/server hatasinda kayit kuyrukta kalir veya inceleme gerektirir; basari uydurulmaz.

## Gercek Donanim Test Adimlari

1. Admin ile girin; Cihaz durumu ekraninda Firmware 7, Tek sensor prototipi, COM6 ve
   guncel/gecerli iki mesafeyi gorun. Ekranda guvenlik uyarisi gorunmeli.
2. Kart okutmayin; sadece bir sensore elinizi <=20 cm yaklastirin. Servo acilmamali,
   ziyaret/mesai veya seans kaydi olusmamali. Sonra elinizi cekin.
3. Girise uygun Demo Uye 01 veya 02 kartini okutun. Onaydan sonra servo acilmali.
   Bir sensoru >20 cm bos birakin; yalnizca digerini <=20 cm yapin.
4. Yaklasik 120-240 ms filtrelemeden sonra LCD'de TEST GIRIS OLAYI ve tek prototip
   kaydi gorulmeli. PC kuyruk aktarimi ve ekran yenilemesi birkac saniye surebilir.
   Ikinci sensor yakinlastirilmadan PostgreSQL'de acik ziyaret olusmali.
5. Demo Uye 02'nin seansi tam 1 azalmali. Elinizi yakin tutun: ikinci kayit/seans olmamali.
   Servo alan doluyken acik kalmali. Elinizi cekince alan kararli bos oldugunda kapanmali.
6. Karti kaldirin ve tekrar okutma korumasi icin en az 10 saniye bekleyin. Ayni karti
   yeniden okutun; acik ziyaret nedeniyle CIKIS izni gelmeli. Bu kez sadece diger sensoru
   <=20 cm yapin. Ziyaret kapanmali, seans ikinci kez azalmamali.
7. Kart onayi alip hicbir sensoru yakinlastirmayin: 8 saniyede zaman asimi ve yeni kayit yok.
8. Suresi dolmus Demo Uye 03 veya dondurulmus Demo Uye 04 ile giris reddini kontrol edin.
9. Personel kartini vardiya icinde okutun. Izinden once mesai olusmamali; tek sensor
   olayindan sonra mevcut vardiya kuralina gore baslamali. Vardiya disinda sadece ziyaret
   kaydi olusmasi normaldir. Demo vardiyalari 08:00-18:00'dedir.
10. Personel hesabindan mola/mesai bitisi secimini yapin; RFID + herhangi bir tek sensor
    olayi ile cikisi tamamlayin. Mola donusu ve bitis mevcut kurallari kullanir.

## Kayitlarin Anlami

Grant.context icinde validationMode=single_sensor_prototype, tetikleyen sensor ve
physicalVerified=false saklanir. Uye ziyaretinin yontemi Tek sensor prototipi olur.
Personel olay mesajinda prototip etiketi bulunur. Son 10 gecis tablosu olayi gosterir;
tam fiziksel gecis raporlari/yon-yogunluk grafigi bunu fiziksel kanit olarak saymaz.
Acik ziyaret sayaci yazilimin prototip durumunu izler; gercek kisi sayisini kanitlamaz.
Normal RFID yetkileri, uyelik/kart/borc/saat/seans kontrolleri ve personel is kurallari korunur.
Mevcut uye, kart, finans veya uyelik kayitlari silinmez; migration gerekmez.
