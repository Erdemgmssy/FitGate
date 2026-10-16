# Standart FitGate kurulum doğrulaması

Sonraki doğrulama tamamlandı: [GitHub öncesi son rapor](SON-DOGRULAMA-RAPORU.md).
Tam backend paketi artık izole PostgreSQL üzerinde 262 test ve 60 alt kontrolle geçti.

16 Ekim 2026 — `feature/demo-database-setup`. Push, merge veya commit yapılmadı.

## Hazırlanan dağıtım

`FitGate-Kurulum.bat` aynı PowerShell girişini kullanır; artık boş/demo seçimi yoktur.
Tek akış bağımlılıkları yükler, yeni PostgreSQL 17 container/volume oluşturur,
`tools/install_sample.py` ile hedefi ve boşluğu doğrular, Alembic head uygular ve
20 üye, 5 personel, 6 hesap içeren ortak kurgusal veri üreticisini çağırır.
Sonrasında `FitGate-Baslat.bat` günlük başlatma yoludur.

Yeni standart veritabanının adı `fitgate_local` olarak ayrıldı. Gerçek `fitgate`
ve geliştirme testindeki `fitgate_demo` standart yükleyicide kabul edilmez.
Container `fitgate-postgres`, volume `fitgate-postgres-data`, bağlantı yalnızca
`127.0.0.1:5433` olur. Mevcut container, volume, `.env.fastapi` veya Docker parola
dosyası varsa yeni kurulum durur. Oluşturulan dosyalar exclusive modda açılır;
silme, reset, overwrite, dump veya gerçek veriden kopyalama yoktur.

`LOCAL_SAMPLE_DATA=true`, development ortamı, doğru veritabanı/kullanıcı/host/port,
yerel Windows Docker bağlamı, container/volume ve PostgreSQL SQL sistem kimliği
doğrulanır. Migration öncesinde kullanıcı tabloları, view ve sequence bulunmamalıdır.
Seed tabloları kilitleyip boşluğu tekrar kontrol eder ve tek transaction kullanır.
Örnek profil üretim ortamında veya farklı bağlantıyla uygulamayı başlatamaz.
Herkese açık hesap bilgileri README’dedir; Argon2 ile saklanır.

İzole test profili, eski reset araçları ve smoke testleri kullanıcı kurulumuna
eklenmedi. Kullanıcı belgelerinde tek standart kurulum anlatılır. Eski demo
raporu tarihsel olarak işaretlendi.

## Çalıştırılan kontroller

| Kontrol | Sonuç |
|---|---|
| Güvenlik / kurulum testleri | 21 test geçti |
| Yeni ayar dosyaları ve Docker oluşturma komutu | Geçici dizinde, Docker çağrıları taklit edilerek geçti |
| Üretim / yanlış hedef / gerçek `fitgate` reddi | Geçti |
| Dolu veritabanında migration/seed çağrılmaması | Geçti |
| Ortak örnek veri üreticisi | Bellek içi SQLite testinde 20 üye, 5 personel, 6 hesap; parola/rol, taksit ve stok kontrolleri geçti |
| Mevcut PostgreSQL 17.11 izole veri seti | Head `b821d74ea39c`, 20 üye, 5 personel, 6 hesap; tüm ilişkiler ve finans/stok kontrolleri geçti |
| PostgreSQL veri detayları | 5 paket, 18 üyelik, 18 fatura, 13 ödeme, 6 ürün, 9 stok hareketi, 3 satış, 4 ders, 7 rezervasyon |
| Tekrar seed | İzole PostgreSQL tablolarındaki satırlar ve parola hash’leri değişmedi |
| Altı hesabın API ve form girişi | İzole backend/frontend üzerinde geçti |
| Admin ekranları ve personel yetkileri | 13 admin ekranı, çalışan finans dışa aktarımı 403, kendi personel kaydı kapsamı geçti |
| Yenileme, masaüstü/mobil, JS çalışma hataları | Altı hesap geçti; sıfır JS çalışma hatası |
| Frontend birim testleri | 72 test geçti |
| Frontend production build | Geçti; lucide-react kaynaklı iki engelleyici olmayan `use client` uyarısı |
| Windows PowerShell 5.1 başlatıcı fixture testi | Docker tamamen taklit edilerek tekrar çalıştırıldı ve geçti |
| Taklit Docker soğuk başlangıcı | Gerçek Docker çalıştırılmadan stopped → start → ready akışı geçti |
| Kurulumun mevcut ayarlarla çağrılması | `.env.fastapi` görüldüğünde beklenen şekilde durdu |
| PowerShell parser ve `git diff --check` | Geçti |

Bellek içi SQLite yalnızca test içindir; uygulamanın dağıtım veritabanı PostgreSQL
olarak kalmıştır. Yeni kurucu doğrulanmış portable veri üreticisini aynen kullanır;
test için farklı bir örnek veri seti geliştirilmedi.

## Sınırlar ve güvenlik olayı

**Temiz Windows bilgisayarda yeni Docker kaynaklarıyla uçtan uca standart kurulum
henüz doğrulanmadı.** Bu bilgisayardaki mevcut kaynakları korumak için standart
container oluşturma akışı gerçek Docker üzerinde çalıştırılmadı. Yeni standart
`fitgate_local` üzerinde yeni migration+seed uçtan uca testi yapılmadı; Docker ve
ilk kurulum sıralaması fixture testleriyle, ortak veri üreticisi bellek içi testle,
veri işlevleri mevcut izole PostgreSQL 17.11 kurulumu üzerinden doğrulandı.

İlk doğrulamada `tools/test_fastapi.py` ayrı bir veritabanı oluşturup tabloları sıfırladığı
için tüm backend regresyon paketi çalıştırılmamıştı. Son doğrulamada hedef korumaları
eklenerek tam paket güvenle çalıştırıldı; ayrıntılar yukarıdaki son rapordadır. Mevcut izole
veritabanı ve örnek kayıtlar korundu. Fiziksel donanım testi yapılmadı.

İlk başlatıcı testinin Docker erişimini taklit etmediği çalışma sırasında fark
edildi. Bu eski test durmuş gerçek `fitgate-postgres` container’ını başlattı.
Gerçek veritabanına migration, seed, reset veya iş verisi yazan SQL gönderilmedi;
ancak PostgreSQL açılışının volume’e dahili yazı yapmış olması mümkündür.
Bu nedenle gerçek volume’ün hiç değişmediği iddia edilemez. Container tekrar
durdurulmadı. Olay kullanıcıya bildirildi. Test, geçici launcher kopyasında Docker
fonksiyonunu başlangıçtan önce değiştirecek şekilde düzeltildi ve yeniden geçti.
Bu korumanın süreç başlangıcından önce uygulandığına regresyon testi eklendi.

Mevcut `.env.fastapi` değiştirilmedi; başlangıç ve bitiş SHA-256:
`A9E6B7268395553D656ACF3548BFFA30D701049FE9919E9191D65EA65C948FB2`.
Gerçek veritabanı için önce/sonra veri parmak izi bulunmadığından içeriklerin
değişmediği bağımsız karşılaştırmayla doğrulanmış değildir. Gerçek kişi kayıtları,
parolalar, RFID, ödeme verileri, env veya dump dosyaları değişikliklere eklenmedi.

## İnceleme ortamı

Önceden kurulan izole uygulama açık bırakıldı: frontend `http://127.0.0.1:5184/`,
backend `http://127.0.0.1:8014/docs`. Bu adresler geliştirme testinindir; standart
kurulum adresleri `5174` ve `8001` olarak kalır. Container, volume ve örnek kayıtlar
silinmedi. Ayrıntılı yerel kanıtlar Git dışındaki `work/isolated-demo/` altındadır.
