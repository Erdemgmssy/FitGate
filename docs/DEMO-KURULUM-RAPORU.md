> Tarihsel rapor: eski demo/boş kurulum akışını anlatır. Güncel dağıtım ve test sonuçları için [Standart Kurulum Raporu](STANDART-KURULUM-RAPORU.md) geçerlidir.

# Demo kurulum değişiklik raporu

## GitHub gönderimi öncesi son kontrol — 16 Ekim 2026

- Branch: `feature/demo-database-setup`; başlangıç commit'i güncel `origin/main` ile aynı.
- Son dosya haliyle `tools/test_fastapi.py`: **262 test ve 60 alt kontrol geçti**.
  Yalnızca mevcut httpx/Starlette deprecation uyarısı var.
- PowerShell parser, Python derleme ve staged `git diff --check` geçti.
- Commit kapsamı yalnızca demo kurulumuna ait 11 kaynak, test ve belge dosyasıdır.
  Gerçek env, dump, yerel parola/anahtar ve kişisel veri eklenmedi. `.env.fastapi.example`
  yalnızca yer tutucular içerir. Yerel env dosyalarının Git tarafından yok sayıldığı doğrulandı.
- Staged dosyalar bilinen yerel gizli değerler, anahtar kalıpları ve mevcut kullanıcı,
  personel, üye alanlarıyla karşılaştırıldı. Eşleşmeler yalnızca kaynakta tanımlı
  kurgusal demo adları ve örnek e-postalardı. Herkese açık demo şifresi ve test
  sabitleri bilinçli olarak kaynakta bulunur.
- Demo izolasyonu tekrar incelendi: varsayılan kapalı mod, development zorunluluğu,
  `fitgate_demo` hedefi ve yalnızca loopback port eşlemesi; gerçek `fitgate` reddedilir.
- **Temiz Windows makinesinde uçtan uca BAT kurulumu henüz test edilmedi.**
- Aşağıdaki bölümler önceki geliştirme ve doğrulama aşamalarının kayıtlarıdır.

## Hazır demo hesapları — 16 Ekim 2026 son iyileştirme

Bu bölüm son değişikliğin sonuçlarıdır; aşağıdaki önceki doğrulama notları
önceki çalışma aşamasına aittir.

- `feature/demo-database-setup` branch'inde çalışıldı; GitHub'a push yapılmadı.
- Otomatik kurulumun 2 seçimi bir admin ve beş çalışan için README'deki
  `@fitgate.demo` hesaplarını oluşturur. Personel 2 antrenör rolündedir.
- `DEMO_MODE` varsayılanı false; normal kurulum ve parametresiz demo kurucusu
  parola istemeye devam eder. Hazır hesaplar açık `--local-demo-accounts` seçimine bağlıdır.
- Tüm taşınabilir seed çağrıları development, açık demo modu, yalnızca yerel
  PostgreSQL `fitgate_demo` ve yalnızca 127.0.0.1:5433 Docker port eşlemesi ister.
  Eski seed yolu herkese açık demo parolasını reddeder.
- PostgreSQL üzerinde tüm backend paketi: **260 test, 60 alt kontrol geçti**.
  Son eklenen iki CLI seçimi testi ve genişletilen korumalar dahil demo paketi
  yeniden çalıştırıldı: **7 geçti, 255 kapsam dışı**.
- Altı hazır hesabın gerçek FastAPI TestClient girişleri HTTP 200 döndü;
  roller, Argon2 hash'leri, personel yetkileri ve admin işleminin çalışanlarda
  HTTP 403 ile engellenmesi doğrulandı.
- İkinci seed sonrası kullanıcı sayısı altı kaldı; kullanıcı kimlikleri ve
  parola hash'leri değişmedi. Dolu veritabanını reddetme testi geçti.
- Üretim, kapalı demo modu, gerçek fitgate hedefi, uzak sunucu, yanlış port,
  SQLite ve dış ağa açık Docker port eşlemesi reddetme testleri geçti.
- API/seed testleri yalnızca `fitgate_fastapi_test` veritabanında çalıştı.
  Bu testlerde hedef koruması mock edildi; korumanın kabul/ret koşulları
  ayrı testte Docker çıktısı mock edilerek sınandı. Gerçek fitgate hedefine
  seed çalıştırılmadı.
- Tüm backend paketi öncesi/sonrası gerçek veritabanındaki `gym_user` ve
  `gym_employee` tablolarının tüm alanları sıralanıp SHA-256 ile karşılaştırıldı:
  `LIVE_ACCOUNT_EMPLOYEE_FINGERPRINT_UNCHANGED=True`. Kişisel veriler yazdırılmadı.
- PowerShell parser, Python derleme ve `git diff --check` geçti.
- Temiz Windows makinesinde BAT ile uçtan uca kurulum bu aşamada denenmedi.
  Testlerde mevcut httpx/Starlette kullanımına ilişkin bir deprecation uyarısı var.

## Mevcut yapı

`local_postgres.py` ilk kurulumda yerel Docker Desktop üzerinde PostgreSQL 17
oluşturuyor ve mevcut yapılandırma/container/volume bulunduğunda duruyor.
`backup_postgres.py` mevcut işletme veritabanını yedekleyen ayrı bir bakım aracı;
yeni kurulum bunu çağırmıyor. Alembic migration zinciri aktif SQLAlchemy
modellerinin şema kaynağı. Yeni migration gerekmiyor.

Eski `demo_seed.py` cihaza, özel yerel yapılandırmaya ve onaylı reset akışına
bağlı. Yeni kurulum bu reset akışını çağırmıyor; yalnızca mevcut iş servisleriyle
veri üreten `seed` fonksiyonunun taşınabilir seçeneğini kullanıyor.
Eski varsayılan seed davranışı ve ona ait test beklentileri korunuyor.

`FitGate-Launcher.ps1` ve `FitGate-Baslat.bat` mevcut PostgreSQL container'ını
başlatıp servisleri yönetiyor. Bağlantı `.env.fastapi` üzerinden okunduğu için
`fitgate_demo` için launcher değişikliği gerekmiyor. Kullanıcı parolaları
uygulamanın Argon2 işleviyle hash'leniyor; API girişleri mevcut rol sistemini kullanıyor.

## Eklenen yol

`FitGate-Kurulum.bat` → `FitGate-Kurulum.ps1` → bağımlılıklar →
`local_postgres.py [--demo]` → Alembic → `install_demo.py` veya `create_admin.py`.

Demo yükleyici yalnızca yerel development `fitgate_demo` hedefini kabul ediyor.
Tablo kilitleri ve transaction, boşluk kontrolüyle veri üretimi arasındaki eşzamanlı
yazmaları engelliyor. Dolu veritabanı reddediliyor; demo işareti tekrar yüklemeyi
engelliyor. Hiçbir yeni akış TRUNCATE, DROP, restore veya gerçek veri yedeklemesi yapmıyor.
Mevcut kaynak varsa otomatik devam yerine koruyarak durmak bilinçli tercih.

## 16 Ekim 2026 doğrulaması

| Kontrol | Sonuç |
|---|---|
| Kurulum güvenlik testleri | 7 geçti |
| Bridge birim testleri | 36 geçti; gerçek COM kullanılmadı |
| Frontend testleri | 72 geçti |
| Frontend production build | Geçti; lucide-react `use client` uyarıları var |
| Python derleme ve PowerShell parser | Geçti |
| `git diff --check` | Geçti |
| Geçici SQLite üzerinde demo üretimi | 20 üye, 5 personel; taksit ve stok toplamları doğrulandı |
| Geçici SQLite üzerinde gerçek FastAPI girişleri | Admin ve beş personel için 6 giriş geçti |
| PostgreSQL 17 migration ve tüm backend testleri | İlk aşamada Docker erişilemiyordu; sonraki PostgreSQL doğrulaması aşağıda |
| Temiz Windows makinesinde uçtan uca kurulum | Çalıştırılmadı |
| Launcher entegrasyon testi | Çalıştırılmadı; PostgreSQL motoru hazır değil |

SQLite denemesi PostgreSQL ilişkileri, kilitleri veya migration doğrulamasının
yerine geçmez. Yeni `tests_fastapi/test_portable_demo.py`; gerçek giriş, dolu
veritabanını koruma, tekrar yükleme, stok ve taksit kontrollerini içerir.
Docker hazır olduğunda backend dizininde `tools/test_fastapi.py` ile mevcut
backend testleriyle birlikte çalıştırılmalıdır. Bu mevcut test runner'ı ayrı
`fitgate_fastapi_test` veritabanını sıfırlar; o isimde korunması gereken test
verisi varsa kullanmayın. İşletme veritabanına test uygulanmadı.

Bu çalışma sırasında mevcut PostgreSQL veritabanına, volume'e veya yerel env
dosyalarına yazılmadı; dump alınmadı. GitHub'a push yapılmadı.

## Gerçek PostgreSQL doğrulaması — 16 Ekim 2026

Bu bölüm yukarıdaki ilk aşamanın ardından yapılan gerçek PostgreSQL testidir.
Docker Desktop bağlantısı `desktop-linux` yerel npipe üzerinden sağlandı.
Docker motoru 29.0.1, mevcut `postgres:17` container'ındaki sunucu **17.11**.
Duran `fitgate-postgres` başlatıldı ve test sonunda çalışır durumda bırakıldı.
Yeni container veya volume oluşturulmadı; hiçbir container veya volume silinmedi.

Başlangıçta `fitgate_demo` yoktu. Mevcut sunucuda bu isimle ayrı veritabanı
oluşturuldu. Alembic gerçek PostgreSQL üzerinde boş şemaya uygulandı ve
`b821d74ea39c` revision'ına ulaştı; bunun depodaki tek head olduğu doğrulandı.
Sonraki iki çalıştırmada `upgrade head` de başarıyla tekrarlandı.

### Sonuçlar

| Kontrol | Sonuç |
|---|---|
| Demo üretimi | 20 üye, 5 personel, 6 kullanıcı, 5 paket |
| Üyelikler | 18: 7 aktif, 3 süresi dolmuş, 2 gelecek, 3 donmuş, 3 iptal |
| Finans | 18 fatura, 28 taksit, 13 ödeme; taksit toplamları faturalarla eşit, fazla ödeme yok |
| Stok/satış | 6 ürün, 9 stok hareketi, 3 satış; stok toplamları tutarlı |
| Personel | 15 vardiya planı, 5 simülasyon mesaisi, 10 mesai olayı, 5 izin talebi |
| Dersler | 4 ders, 7 rezervasyon |
| Parolalar | Altı hesapta Argon2 hash doğrulandı |
| Gerçek API girişleri | Admin, resepsiyon, antrenör, salon, satış ve destek: 6/6 HTTP 200 |
| Oturum ve veri API'leri | Her hesapta auth/me, state ve personnel HTTP 200; adminde dashboard HTTP 200 |
| İkinci seed çağrısı | No-op; tüm uygulama tablolarının sayıları ve parola hash'leri aynı |
| Yanlış hedefler | fitgate, uzak sunucu ve SQLite hedefleri reddedildi |
| Dolu demo koruması | Kurgusal mevcut şube korunarak yükleme reddedildi |
| Hatalı seed | Çakışan hesap e-postasıyla hata üretildi; işlem tamamen geri alındı |
| Foreign Key | 119 ilişki tarandı; yetim kayıt veya doğrulanmamış FK/CHECK yok |
| Geçersiz FK yazma | Var olmayan şubeye üye bağlama PostgreSQL tarafından reddedildi |

### Test yöntemi ve son durum

Testler yalnızca `fitgate_demo` üzerinde çalıştı. Üretim fonksiyonu `populate`
ve gerçek FastAPI uygulaması kullanıldı. Test session'ları dış transaction'a
savepoint ile bağlandı; başarılı seed ve API işlemleri burada doğrulandı.
Sonunda dış transaction rollback edildi. Bu nedenle **kalıcı demo kayıtları
ve giriş hesapları bırakılmadı**; `fitgate_demo` yalnızca migrate edilmiş boş
şemayı içeriyor. Test parolaları rastgele ve yalnızca bellekteydi.
Kalıcı kurulumda parolalar kullanıcıdan alınmalıdır. Bu test, ayrı süreçlerde
kalıcı commit edilmiş bir kurulumun ikinci kez çalıştırılması değildir.

Yerel tekrar üretim betikleri ve sonuçlar Git'in yok saydığı
`work/demo-postgres-validation/` dizininde: `run_validation.py`, `results.json`,
`fingerprint.py`, `live-before.txt`, `live-after.txt`. Veritabanını silen veya
sıfırlayan genel `test_fastapi.py` çalıştırılmadı; çünkü o araç
`fitgate_fastapi_test` kullanıyor ve bu görev yalnızca `fitgate_demo` testine izin veriyor.
Tam BAT kurulumunun temiz makinedeki bağımlılık yükleme/container oluşturma
adımları bu oturumda denenmedi. İşlevsel hata bulunmadı; kod düzeltmesi gerekmedi.
TestClient yalnızca httpx/Starlette deprecation uyarısı verdi.

### Mevcut fitgate verisinin korunması

`fitgate` için önce ve sonra REPEATABLE READ / READ ONLY transaction'larında
public şemadaki her tablonun satır sayısı ve sıralanmış satır içerik hash'leri,
constraint ve indeks tanımları karşılaştırıldı. Özetler birebir aynı:

```text
SHA-256: fcdd803483393b53834dc67d59e314ce7820f3b401b0465306eac073486c4538
```

Gerçek veriden dump alınmadı ve satır içerikleri rapora kopyalanmadı.
`fitgate-postgres-data` aynı bağlı volume olarak korundu. Demo veritabanının
şeması bu mevcut volume üzerinde yeni alan kullanır; volume silinmedi veya
sıfırlanmadı. `fitgate` uygulama kayıtlarına yazılmadı. Yerel yapılandırmalar
değiştirilmedi. GitHub'a push yapılmadı.
