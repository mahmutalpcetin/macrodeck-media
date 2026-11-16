# MacroDeck Medya 2.0

ESP32-S3 + 2,8 inç dokunmatik ekran + basmalı encoder. Apple Music, Spotify ve Windows’a medya bilgisi paylaşan tarayıcıları takip eden masaüstü kumandası.

## Açılış

Kurulum için ana [README](../README.md) dosyasını izle. İlk bağlantıda **Bağlantı** sekmesinden COM portunu seçip **Bağlan** düğmesine bas. Doğrulanan kartın USB kimliği yalnızca bu bilgisayarda saklanır; daha sonra otomatik bağlantı için kullanılır.

Uygulama arka planda açık kalmalı. **×**, küçültme düğmesi veya **Simgeye gizle** pencereyi sağ alttaki bildirim alanına gizler; görev çubuğunda yer kaplamaz ve kart çalışmaya devam eder. Simgeye çift tıkla veya sağ tık → **MacroDeck’i aç** ile pencereye dön. Tamamen kapatmak için sağ tık → **Çıkış** seç; bu, bilgisayarın medya bilgisi ve görüntü akışını durdurur. Windows simgeyi **^ gizli simgeler** menüsüne yerleştirebilir.

Aynı masaüstü kısayolunu tekrar açmak gizli pencereyi geri getirir; ikinci USB bağlantısı oluşturmaz. Windows başlangıcı isteğe bağlıdır: **Bağlantı → Windows açılınca başlat**. Bu seçenek kullanılırsa uygulama bildirim alanında gizli başlar. Bildirim simgesi oluşturulamazsa pencere gizlenmez; normal kapatma davranışı korunur.

## Cihaz ekranı

- **Sol üstte kaynak adı:** açık medya kaynakları ve Otomatik seçeneğinin bulunduğu listeyi açar. Bir kaynak seçilirse ayar korunur; kaynak kapalıysa başka uygulamaya atlamaz. Nokta sabit kaynağı, küçük ok otomatik modu belirtir.
- **Saat veya dişli:** parlaklık menüsünü açar. Çubuğu sürükle; ± düğmeleri veya %25/%50/%100 seçenekleriyle de ayarla. Alt sınır %5’tir. GERİ ile çık.
- **Sağ üst:** oynatma durum yazısı yerine ses çıkış cihazının adı gösterilir; uzun adlar kısaltılır. Tam ad bilgisayar penceresinde ses bilgisinin altındadır. Açık medya uygulamasının ses oturumuyla eşleşen çıkış aranır; eşleşme bulunmazsa sistemin varsayılan çıkışı kullanılır ve bilgisayarda **Varsayılan çıkış** diye belirtilir. Bir uygulamanın birden fazla çıkışı varsa tek bir cihaz tahmin edilmez. Kontrol yaklaşık iki saniyede bir yenilenir; ses yönlendirme ayarları değiştirilmez.
- **Alt üç düğme:** önceki / oynat-duraklat / sonraki. Kaynağın desteklemediği düğmeler soluktur. Fiziksel medya kontrolü son onaylanmış ekranın oturumunu hedefler; kaynak geçişi sürerken başka uygulamaya komut göndermez.
- **Encoder:** çevir = ses; 1 bas = oynat/duraklat; 2 bas = sonraki; 3 bas = önceki; yaklaşık 0,7 saniye basılı tut = sessize al/aç. Yavaş çevirme %1, hızlı çevirme %2/%3/%5/%7/%9 adımlarını kullanır.
- **Bekleme:** varsayılan olarak 60 saniye duraklama ve hareketsizlikten sonra saat ekranı gelir. Parlaklık en fazla %15 olur. İlk dokunuş sadece uyandırır; encoder veya oynatma da eski parlaklığı geri getirir.

Geniş video küçük resimleri kesilmeden gösterilir. Uzun başlıklar üç satıra sığdırılır; tam başlık bilgisayar penceresinde okunabilir. CPU, NVIDIA GPU ve RAM yüzdeleri üstte görünür. Bir değer okunamıyorsa sıfır uydurulmaz; çizgi gösterilir.

## Bilgisayar penceresi

**Önizleme** büyüyüp küçülür; ekrandaki menüler buradan tıklanıp parlaklık çubuğu sürüklenebilir.

- **Kontrol:** kaynak seçimi, medya düğmeleri, parlaklık, bekleme süresi ve bekleme parlaklığı. Bekleme 30 saniye / 1 / 2 / 5 dakika veya Kapalı seçilebilir. Ekran ayarlarını uygula düğmesi tercihi kaydeder.
- **Tuşlar:** altı fiziksel tuş için işlev ve encoder yön/adım ayarları. Bu tuşlar henüz fiziksel olarak bağlanmadı; HID tarafı mevcut COM bağlantısında kullanılmıyor.
- **Bağlantı:** otomatik/elle bağlantı, kalibrasyon, başlangıç seçeneği, demo ve yerel tanılama raporu.

Pencere kısa olduğunda ayarlar kaydırılabilir. Demo gerçek oynatmayı değiştirmez. Tanılama raporu otomatik gönderilmez; kullanıcı dosya olarak kaydeder.

## Güncel ve doğrulanmış bağlantılar

Bu tablo eski 13 Kasım lehim öncesi planının yerini alır. Bağlantı değiştirmeden önce USB’yi çıkar.

| LCD / modül | ESP32 / bağlantı |
| --- | --- |
| LCD VCC | 3V3 |
| LCD GND | Ortak GND |
| LCD SDI / MOSI | GPIO13 |
| LCD SCK | GPIO14 |
| LCD D/C | GPIO15 |
| LCD RESET | GPIO16; kartın RST/EN ucu değil |
| LCD CS | GPIO17 |
| LCD SDO / MISO | Boş; GPIO18’e bağlanmaz |
| LCD LED | 4,7 kΩ seri direnç üzerinden GPIO18 |
| Touch T_CLK | GPIO39 |
| Touch T_DIN | GPIO40 |
| Touch T_OUT | GPIO41 |
| Touch T_CS | GPIO42 |
| Touch T_IRQ | GPIO2 |
| Encoder CLK | HV1 → LV1 → GPIO10 |
| Encoder DT | HV2 → LV2 → GPIO11 |
| Encoder SW | HV3 → LV3 → GPIO12 |
| Encoder + ve dönüştürücü HV | USB’den doğrulanmış 5Vin çıkışı |
| Dönüştürücü LV | 3V3 |
| Encoder/dönüştürücü GND | Ortak GND |

**LED’in eski doğrudan 3V3 jumperı artık takılmaz.** Bu ekranda kart üzerindeki sürücüyle parlaklık değişimi kullanıcı tarafından optik olarak doğrulandı; ayrıca MOSFET alınmadı. Başka ekran kartına aynı varsayım uygulanmaz.

Bu YD kartının IN-OUT köprüsü daha önce lehimlendi ve 5Vin’de USB kaynaklı yaklaşık 4,7 V ölçüldü. Aynı anda harici 5 V besleme kullanma. 5 V modül sinyalleri ESP32’ye doğrudan bağlanmaz. GPIO19/20 native USB’ye ayrıdır; 35/36/37 PSRAM’a ayrıldığı için harici bağlantıda kullanılmaz. SD kart bu projede kullanılmıyor.

## Yazılım yapısı

Kartta **C++**, bilgisayarda **Python** çalışır. Windows yerel medya oturumları okunur; Apple/Spotify hesabı şifresi veya API anahtarı gerekmez. Uygulama içeriği dışarı gönderen bir özellik eklenmedi.

- `../desktop/app.py`, `../desktop/desktop_ui.py`: masaüstü pencere ve önizleme.
- `../desktop/tray.py`: Windows bildirim simgesi, aç/çıkış menüsü ve Explorer yeniden başladığında simgeyi geri ekleme.
- `../desktop/backend.py`: bağımsız medya, dokunmatik, encoder ve cihaz döngüsü.
- `../desktop/media.py`: aktif/sabit kaynak seçimi, bilgi okuma ve kontrollü komut gönderimi.
- `../desktop/rendering.py`: 320×240 çizim ve tasarım.
- `../desktop/protocol.py`, `../desktop/frame_codec.py`: değişen bölgeler, kayıpsız sıkıştırma, USB ve piksel doğrulaması.
- `../desktop/resources.py`: Windows CPU/RAM ve kurulu NVIDIA sürücüsünden GPU okuması; gerekirse nvidia-smi geri dönüşü.
- `../desktop/audio_output.py`: Windows ses cihazlarının adları ve medya uygulamasının ses oturumu üzerinden çıkış eşleştirmesi.
- `../firmware/src/main.cpp`, `frame_codec.h`: alıcı, doğrulama, LCD, USB, encoder ve PWM.

Tercihler yerel JSON dosyalarında tutulur; yazma başarısızlığında önceki dosyayı koruyan atomik kayıt kullanılır. Elle seçilen parlaklık kartın kalıcı belleğine de kaydedilir. Geçici bekleme kısılması kayıtlı parlaklığı değiştirmez; kart yeniden başladığında kayıtlı seviye kullanılır.

## Kurulum, derleme ve sınırlar

Güncel, bilgisayardan bağımsız komutlar ana [README](../README.md) içindedir. Kablosuz bağlantı, batarya ve altı tuşun fiziksel kurulumu tamamlanmadı. Windows’un paylaşmadığı medya bilgileri alınamaz.
