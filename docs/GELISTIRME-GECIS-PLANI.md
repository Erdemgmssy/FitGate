# FitGate Temiz Depoya Geçiş

## Klasörler ve Depolar

Yeni ana geliştirme klasörü: `FitGate-GitHub-Temiz-20261013`.
Yeni PRIVATE depo: https://github.com/Erdemgmssy/FitGate
Eski PRIVATE depo: https://github.com/Erdemgmssy/FitGate-Eski-Arsiv

Eski çalışan `harika-bir-yakla-m-projeyi-mod` klasörü mevcut yerel hizmetleri
çalıştırmaya devam eder. Yeni klasörün oluşturulması çalışan süreçleri veya
veritabanını otomatik olarak taşımaz. Eski klasör operasyon/arşiv içindir;
bundan sonra geliştirme, commit ve push yalnızca yeni klasörde yapılır.

## Her Push Öncesi

GitHub yeniden adlandırma eski URL'yi yönlendirebilir. Aynı isimle yeni repo
oluşturulduğunda eski klasördeki eski `origin` URL'si yeni depoya gidebilir.
Bu nedenle eski klasörden push, yeni branch/tag gönderme, force push veya
eski commit'leri yeni klasöre fetch/merge/cherry-pick etme yapılmamalıdır.

Yeni klasörde PowerShell'de:

```powershell
git rev-parse --show-toplevel
git remote -v
git branch --show-current
git rev-list --max-parents=0 main
git status --short
```

Kök klasör `FitGate-GitHub-Temiz-20261013`, dal `main`, origin yeni FitGate
deposu olmalıdır. Kök commit `Initial commit - Clean FitGate` olmalıdır.
Başlangıçta tek commit vardır; sonraki geliştirmeler bu kökten devam eder.
`git -C` ile açıkça yeni klasörü hedeflemek yanlış dizinden işlem riskini azaltır.

## Eski Klasör İçin Koruma

Bu işlem sırasında eski klasörde dosya veya Git ayarı değiştirilmez.
Kullanıcı ayrıca onayladığında eski klasörün origin fetch URL'si arşiv adresine
güncellenmeli ve push URL'si geçersiz yerel bir hedefe ayarlanarak push
devre dışı bırakılmalıdır. Eski origin'i yeni FitGate URL'sinde bırakmak kalıcı
güvenlik önlemi değildir. Bu koruma uygulanana kadar eski klasörde Git işlemi
yapılmamalıdır; IDE/Git araçlarında yalnızca yeni klasör açılmalıdır.

Eski repo silinmez; eski parolaların bulunduğu tarihçe yalnızca PRIVATE arşivde
kalır. Arşive erişimi sınırlayın. Eski repo silme kararı ayrı son onay gerektirir.

## Yerel Çalıştırmaya Geçiş

1. Yeni kopya kaynak kodudur; gerçek env, kullanıcı, UID ve DB yedeği içermez.
2. Çalışan eski servisleri taşımak ayrı, açıkça onaylanmış bir bakım adımıdır.
3. Mevcut PostgreSQL container/volume korunur. Yeni ilk kurulum veya demo reset
   aracı mevcut volume üzerinde çalıştırılmamalıdır.
4. Yerel env dosyaları gerekirse kullanıcı onayıyla güvenli biçimde yeni konuma
   aktarılır; Git dışında kalır. Secret/cihaz kaydı yeniden oluşturulmaz.
5. Önce eski başlatıcının sahip olduğu servisler durdurulur, sonra yeni klasörden
   başlatılır. Aynı portlara iki farklı kaynak klasöründen servis açılmaz.
6. USB yeniden bağlantısı/reset servoyu hareket ettirebilir; bakım öncesi fiziksel
   güvenlik onayı alınır. Firmware yükleme bu geçişin parçası değildir.
7. Ayrı test veritabanında backend ve online Alembic doğrulaması tamamlanır;
   canlı kayıtlar test fixture'leriyle değiştirilmez.

24 demo üye, personel hesapları ve 7 RFID eşleştirmesi kaynak kopyasının değil,
mevcut yerel PostgreSQL'in verileridir. Depo yenileme bunları sıfırlamaz.

## Test Sınırları

Temiz kaynak hazırlığında 72 frontend, 36 Bridge ve 7 güvenlik testi geçti;
React ve Firmware 7 derlendi. 16 Alembic revision zinciri kontrol edildi.
Stok migration veri sorgusu gerektirdiği için tam offline upgrade desteklenmez.
Gerçek PostgreSQL üzerinde tüm backend/entegrasyon testleri ve online migration
kontrolü bu yayın işleminin parçası değildir; başarılı varsayılmamalıdır.
