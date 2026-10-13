# FitGate Temiz Kaynak Kopyası

Tarih: 13 Ekim 2026. Bu rapor GitHub yayını öncesindeki temiz kopya hazırlığının
sonuçlarını kaydeder; aşağıdaki GitHub işlem durumları o aşamaya aittir.
Güncel depo/klasör geçişi için `GELISTIRME-GECIS-PLANI.md` belgesine bakın.

## Korunan Kaynaklar

- React ekranları, stiller, paket kilidi ve frontend testleri.
- FastAPI, SQLAlchemy modelleri, iş kuralları ve backend testleri.
- 16 Alembic migration; mevcut PostgreSQL şeması korunur.
- Firmware 7 kaynakları ve firmware testleri. Prototip derleme bayrağı gerekir;
  varsayılan derleme iki sensörlü Firmware 6 davranışıdır.
- USB Bridge ve testleri; kaynakları değiştirilmemiştir.
- BAT ve PowerShell başlatıcıları, güvenlik ve başlatıcı testleri.
- Türkçe README, Windows/Docker kurulum rehberi ve güvenli env örnekleri.
- Manuel işletim, prototip testleri ve açıkça çalıştırılan demo araçları.

Eski veritabanı tablo adlarındaki `gym_` öneki uyumluluk için korunur;
bu isimler Django runtime bağımlılığı değildir. Eski export okuyucusu da
Django gerektirmediği için korunmuştur. Demo reset başlangıçta çağrılmaz.

## Dahil Edilmeyenler

- Önceki `.git` ve tüm Git geçmişi.
- Eski `backend/gym`, `backend/config`, SQL Server `backend/database` kaynakları.
- Django başlatıcıları, bağımlılık kilidi ve Django env örneği.
- Eski Django migration ve testleri; aktif Alembic ve uygulama testleri korunur.
- Eski mimari taslakları ve önceki yerel güvenlik/kurulum denetim raporları.
- Gerçek env, anahtar, parola, telefon/e-posta, RFID eşleştirmesi ve kullanıcı kayıtları.
- Veritabanı yedekleri, flash yedekleri, work/outputs, yüklemeler ve günlükler.
- node_modules, sanal ortam, build/dist ve diğer yeniden üretilebilir çıktılar.

İlk kopyalamada 217 kaynak dosyası alındı, 38 eski/yerel rapor dosyası dışarıda
bırakıldı. Bu raporla hazırlık dağıtımı 218 dosyaydı; yayın için geçiş planı
ayrıca eklendi. Git dışındaki yerel veriler
kopya adaylarına hiç alınmadı; özgün klasörde silinmedi.

## Yalnızca Kopyadaki Uyarlamalar

README, backend README, backend FastAPI rehberi, Windows kurulum rehberi ve
prototip rehberi kaldırılan eski dosyalara/yerel araçlara yönlendirmeyecek biçimde
düzenlendi. Arduino CLI ayrıca kurulacak şekilde belgelenmiştir.

Kurulum güvenlik testinde eski Django seed yokken arşiv dosyalarının gerçekten
dağıtıma dahil olmadığını doğrulayan kontrol eklendi. Çalışan uygulama, frontend,
firmware, Bridge ve başlatıcıların kaynakları özgün sürümle aynıdır.

## Güvenlik ve Bütünlük

Tüm kaynak dosyaları içerik taramasından geçirildi. Yerel gerçek secret/parola,
geçmiş seed parolaları, RFID ve kişisel iletişim değerleri yalnızca bellekte
karşılaştırıldı; değerler rapora veya dosyaya yazılmadı. Canlı veritabanından
gerekli karşılaştırmalar salt okunur transaction ile alındı.

Kaynak taramasında hassas eşleşme bulunmadı. Birim testlerindeki sentetik
kimlik/credential örnekleri gerçek hesap bilgileri değildir; test kaynakları
korundu. Gerçek env ve çıktılar için gitignore kuralları ayrıca doğrulandı.

Özgün projedeki kopya adaylarının SHA-256 değerleri işlem öncesi ve sonrası
karşılaştırıldı; özgün kaynak değişikliği ve eksik aktif kaynak bulunmadı.
Eski Git indeksi/geçmişi değiştirilmedi. Docker'a yazma, migration uygulama,
servis yeniden başlatma, kart okutma veya firmware yükleme yapılmadı.

## Doğrulama Sonuçları

| Kontrol | Sonuç |
|---|---|
| Yeni Python sanal ortamı ve kilitli bağımlılık kurulumu | Başarılı |
| pip check | Bağımlılık hatası yok |
| Yeni npm ci kurulumu | Başarılı |
| React birim testleri | 72 geçti |
| React üretim derlemesi | Başarılı |
| USB Bridge birim testleri | 36 geçti; gerçek COM açılmadı |
| Kurulum/güvenlik testleri | 7 geçti |
| Python sözdizimi ve Django olmadan FastAPI import | Başarılı; DB bağlantısı engellenerek kontrol edildi |
| Alembic zinciri | 16 revision, tek head; eksiksiz |
| İlk migration çevrimdışı SQL üretimi | Başarılı |
| Tam çevrimdışı Alembic upgrade | Stok migration canlı veri sorgusu nedeniyle desteklenmiyor |
| PowerShell betik sözdizimi | 13 dosya, hata yok |
| Firmware 7 derlemesi | Başarılı; 19.160 bayt flash, 1.412 bayt RAM |
| Firmware C++ mantık testleri | Başarılı |

React derlemesinde lucide-react `use client` yönergesi hakkında engelleyici
olmayan iki uyarı çıktı. Derleme başarıyla tamamlandı.

Tam çevrimdışı Alembic denemesi `c97af583bc41` revision'ının mevcut stok
kayıtlarını kontrol eden `scalar` sorgusunda durur; bu gerçek PostgreSQL
migration başarısızlığı olarak yorumlanmamalıdır. Migration'lar değiştirilmedi.

Bu aşamada PostgreSQL üzerinde tüm backend/entegrasyon testleri,
Playwright ekran testleri, gerçek servis start/stop ve fiziksel donanım testleri
yeniden çalıştırılmadı. Temiz kopyaya canlı env veya kullanıcı verisi taşınmadı.
Başlatma öncesinde ayrı yerel yapılandırma gerekir; aynı portlarda çalışan
özgün projeyle ikinci servis grubu başlatılmamalıdır.

Kurulum/derlemede üretilen bağımlılık klasörleri ve çıktılar ayrı doğrulama
klasöründe bırakıldı; son `FitGate-GitHub-Temiz-20261013` kaynak kopyasına
alınmadı. Yeni ortamda README adımlarıyla yeniden üretilir.

## Sonraki Aşama

Bu kopya kaynak düzeyinde yeniden yayımlamaya hazırdır. Eski GitHub deposunu
silme, yeni PRIVATE depo oluşturma, Git init/commit ve push henüz yapılmadı.
Yeni aşama açık kullanıcı onayı gerektirir. Eski depoyu silmeden önce güvenli
yerel arşivlerin varlığı ve yeni depoya erişim ayrıca doğrulanmalıdır.
