# GitHub öncesi son doğrulama

16 Ekim 2026 — `feature/demo-database-setup`. Push veya merge yapılmadı.

## Gerçek veritabanı

Gerçek `127.0.0.1:5433/fitgate` bağlantısı yalnızca
`default_transaction_read_only=on` ve `REPEATABLE READ / READ ONLY`
transaction ile kullanıldı; `transaction_read_only=on` SQL üzerinden doğrulandı.
Üye, personel ve ödeme kayıtlarına yazma yapılmadı. Migration head
`b821d74ea39c`; 119 yabancı anahtarda yetim kayıt yok. Doğrulanmamış constraint,
geçersiz/hazır olmayan indeks veya negatif ürün stoğu bulunmadı.

Önceki `work/demo-postgres-validation/live-before.txt` ve `live-after.txt`
kayıtlarıyla aynı PostgreSQL `row_to_json` / sıralı MD5 yöntemi kullanıldı.
Her iki eski kayıt için de **44 tablo + constraint ve indeks özetleri = 46/46**
eşleşti; satır sayıları ve içerik hash’lerinde fark yok. Eski kayıtların normalize
edilmiş SHA-256 değeri önceki rapordaki
`fcdd803483393b53834dc67d59e314ce7820f3b401b0465306eac073486c4538`
değeriyle de eşleşti. Gerçek satır içerikleri dosyaya veya rapora kopyalanmadı.
Bu oturumun başlangıç/bitiş mantıksal parmak izleri de aynı kaldı.

Eski parmak izleri public şemadaki tabloları ve constraint/indeks tanımlarını
kapsar. Sequence sayaçları, roller/izinler, fonksiyon/view tanımları, diğer
şemalar, WAL, loglar veya volume dosyalarının birebir içeriği için geçmiş
karşılaştırma kaydı yoktur. Önceki oturumdaki container açılışının dahili disk
yazıları bu mantıksal karşılaştırmayla dışlanamaz. Mantıksal iş verilerinin aynı
olması, volume’ün fiziksel dosyalarının değişmediği anlamına gelmez.

## Tam backend regresyonu

Eski çalıştırıcı, env dosyasındaki sunucuda aynı adlı test veritabanını
sıfırlayabildiğinden güvenli hedef kontrolü eklendi. `tools/test_fastapi.py`
artık import edildiğinde işlem yapmayan bir giriş noktasıdır; uygulama
`tools/isolated_regression.py` içindedir.

- Açık `--isolated-demo-container` bayrağı zorunludur.
- Kaynak yalnızca `fitgate-demo-test`, ayrı `fitgate-demo-test-data` volume’ü,
  `127.0.0.1:5434/fitgate_demo` ve `fitgate` kullanıcısı olabilir.
- Yerel Docker bağlamı, loopback bağlaması ve PostgreSQL 17.11 denetlenir.
- Maintenance ve test bağlantılarının SQL sistem kimliği container içindeki
  sunucuyla eşleşmeden yazma/reset yapılmaz.
- Sabit reset hedefi **`127.0.0.1:5434/fitgate_fastapi_test`** olur.
- Bu hedefin başlangıçta mevcut olmadığı salt okunur sorguyla doğrulandı.
  Ayrı test veritabanı oluşturuldu; DROP/TRUNCATE ve fixture işlemleri yalnızca
  bu veritabanında çalıştı. Container veya volume silinmedi.

**262 test geçti, 60 alt kontrol geçti, başarısız/atlanmış test yok.** Süre
77,59 saniye; yalnızca mevcut httpx/Starlette deprecation uyarısı var.
`fitgate_demo` tablolarının önce/sonra satır sayıları ve içerik hash’leri aynı;
20 üye ve 5 personelli inceleme verileri korundu. Test veritabanı da yerinde
bırakıldı. Yeni hedef korumaları dahil **25 güvenlik/kurulum testi** geçti.

## Standart kurulum tutarlılığı

BAT girişleri ve başvurdukları kaynak/kilit dosyaları mevcut. Beş PowerShell
dosyası parser kontrolünden geçti. Kurulum sırası tek akıştır:

`FitGate-Kurulum.bat` → PowerShell → `local_postgres.py` → `install_sample.py`
→ boşluk/kimlik kontrolü → Alembic → ortak örnek veri üreticisi.

Demo/boş seçimi ve admin parola sorusu standart akışta yoktur. README’de altı
örnek hesap ve parolası var; otomatik örnek kayıt yüklemesi açıklanıyor.
Günlük başlangıç ayrı `FitGate-Baslat.bat` yoludur ve örnek veriyi tekrar yüklemez.

| Ortam | PostgreSQL | Veritabanı | Backend / frontend |
|---|---|---|---|
| Mevcut gerçek kurulum | `127.0.0.1:5433` | `fitgate` | Mevcut ayarları korunur |
| Yeni standart kurulum | `127.0.0.1:5433` | `fitgate_local` | `8001` / `5174` |
| İzole inceleme | `127.0.0.1:5434` | `fitgate_demo` | `8014` / `5184` |
| Backend regresyonu | `127.0.0.1:5434` | `fitgate_fastapi_test` | HTTP test istemcisi |

Standart backend portu, frontend proxy’si ve izinli origin’ler uyumlu; frontend
strict port kullanır. Yeni kurulum mevcut gerçek kurulumla aynı kaynak adlarını
kullandığı için bu bilgisayarda yan yana otomatik kurulmaz: mevcut ayar,
container veya volume kontrolünde durur. Gerçek sunucuda `fitgate_local` yok;
standart yükleyici `fitgate` hedefini reddediyor. Test sunucusu farklı sistem
kimliği/port/container/volume ile ayrıdır.

## Koruma ve kalan riskler

Bu oturumda `fitgate-postgres` yeniden başlatılmadı, durdurulmadı veya silinmedi.
Container kimlikleri, başlangıç zamanları, restart sayaçları ve mount bilgileri
başlangıç/bitişte aynı. İki Docker volume’ünün kimliği/metadata’sı korundu;
izole test volume’üne test veritabanı yazıları beklendiği gibi yapıldı.
Envanterdeki beş env dosyasının hash’leri aynı; mevcut `.env.fastapi` hash’i
önceki rapordaki değerle de eşleşiyor. Kişisel satırlar, gerçek env veya yedek
dosyaları Git değişikliklerine eklenmedi.

Temiz Windows üzerinde sıfırdan Docker oluşturma + standart kurulum uçtan uca
henüz doğrulanmadı. Mevcut kaynaklar korunarak kurulum dosya/ayar/port kontrolleri,
geçici dizin/Docker mock testleri ve tam izole PostgreSQL backend regresyonu
tamamlandı. Fiziksel donanım testi ve disk düzeyinde forensic karşılaştırma
yapılmadı. Önceki frontend build’indeki iki bağımlılık uyarısı da geçerlidir.

Ayrıntılı yerel kanıtlar, gerçek verilerle ilişkili özetleri GitHub’a taşımamak
için Git dışındaki `work/final-validation/` altında tutulur: `before.json`,
`after.json`, `demo-before.json`, `regression-result.json`,
`backend-regression.log`, `consistency.json`.
