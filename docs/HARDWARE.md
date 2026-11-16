# Tested hardware and wiring

YD ESP32-S3 N16R8, KMRTM28028-SPI 2.8-inch ILI9341 + HR2046/XPT2046, HW-040 encoder, 4-channel 5 V / 3.3 V level shifter. Disconnect USB before rewiring. GPIO numbers are chip labels, not physical header positions. The table below retains Turkish labels from the build notes.

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


The LCD LED connection controls the onboard backlight driver on this tested module. Do not power a bare backlight LED directly from a GPIO. Confirm the circuit on a different module. The optional six keys are not installed; their reserved firmware pins are GPIO4–9.
