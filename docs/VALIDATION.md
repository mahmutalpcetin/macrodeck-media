# Validation

The working prototype was exercised on Windows with one N16R8 ESP32-S3, a 2.8-inch ILI9341 touchscreen and an HW-040 encoder. These are local bench results, not a guarantee for other hardware or every workload.

## Desktop and transport

The original working version passed **77 unit tests** covering codec bounds, dirty-region reconstruction, packet ACK handling, metadata edge cases, calibration, input deduplication, acceleration, media ownership, route selection, reconnect behavior, and atomic preferences. The shareable version adds two device-identity tests; **79 tests passed locally in a newly created Python 3.12 virtual environment** installed from `requirements-dev.txt`. Native layout and tray checks also passed in that clean environment.

Both `display` and `headless` firmware targets compiled successfully from the public project configuration, including its declared XPT2046 v1.4 dependency. Existing local PlatformIO compiler/framework caches were reused; the public project no longer requires a hardcoded package path. On 16 November 2026, the first public [GitHub Actions run](https://github.com/mahmutalpcetin/macrodeck-media/actions/runs/43818328520) passed all three jobs: Windows desktop tests, Linux display firmware build, and Linux headless firmware build. These checks ran on source commit `d71fcefb0583a7ddcd91c37960ec99bf396f614b`.

Additional native checks cover tray creation/removal, hidden startup, close/minimize-to-tray, restore, double-click, and worker shutdown. Layout was checked at 1160×800 and 940×640 with long Turkish titles. Live shortcut re-launch restored one existing instance.

## Physical measurements

| Scenario | Observed result |
| --- | --- |
| Same complete image, raw RGB565 | 153,600 bytes / 3,828 ms |
| Same image, lossless RLE565 | 26,300 bytes / 828 ms; identical decoded CRC |
| 20 mixed images plus serial reopen | Passed; mean 271 ms, maximum 906 ms |
| Wrong wire CRC / overflowing RLE / wrong pixel CRC | Rejected; later valid images accepted |
| MCU reset while USB remained open | Boot recognized and full image sent in about 1.4 s |
| Reopen after interrupted binary frame | Recovered in 5.766 s |
| Save brightness, temporarily dim, reboot | Saved brightness preserved |
| Read-only output-device polling, 30 reads | Mean 4.95 ms; audio settings unchanged |

The public copy removes the author's hardcoded device identity and filesystem paths. It has not been flashed onto a second board. Automated desktop checks do not establish physical encoder/touch latency under every workload, sleep/resume reliability on all PCs, or battery runtime.

No claim is made that the native USB HID / six-key macro pad, wireless transport, or battery hardware has been completed.
