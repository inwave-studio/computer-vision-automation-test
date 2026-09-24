# Latency benchmarks

Tooling behind the tuning in `.agent/design.md` task 3. These talk to a real
device, so they are run by hand, not as part of the test suite. Run them from
the project root so `autoplay` imports:

    python bench/bench_downscale.py --capture

| script | question it answers |
| --- | --- |
| `bench_downscale.py` | how far can the stream shrink before OCR/matching miss? |
| `bench_encoder.py` | which `video_encoder` gives the lowest lag? |
| `bench_lag.py` | glass-to-frame lag; `lag_once()` is reused by the others |
| `bench_latency.py` | startup / grab / OCR / match cost across sizes |
| `bench_buffer.py` | does a smaller decoder buffer help? |
| `bench_accuracy.py` | is a given size still accurate on a live screen? |
| `bench_popup.py` | does the smallest template survive a reduced stream? |
| `bench_scale_probe.py` | matching alone, with app timing removed |

`bench_downscale.py` and `bench_scale_probe.py` cache a captured frame as a
PNG next to where they run and reuse it; delete it to recapture.

## Results on a 1080x2400 device (Redmi 23021RAAEG, Android 15)

Frame grabs are free (~0ms) and OCR is near-flat across sizes, because
RapidOCR downscales internally. Template matching is the whole cost, and it
scales with frame area - so the stream size is the lever that matters.

| longest edge | frame | OCR | first sweep | cached match |
| --- | --- | --- | --- | --- |
| native | 864x1920 | ok | 7505ms | 275ms |
| 1400 | 630x1400 | ok | 4020ms | 90ms |
| **1200** | **540x1200** | **ok** | **2699ms** | **51ms** |
| 1100 | 495x1100 | ok | - | - |
| 1050 | 472x1050 | **misses text** | - | - |
| 1000 | 450x1000 | misses text | 1790ms | 31ms |

OCR fails at a cliff, not a slope: it reads the notification prompt at 1100
and loses it at 1050. 1200 is the setting - above the cliff with headroom,
and ~3x cheaper to match than native.

Encoders, measured as glass-to-frame lag:

| encoder | lag (median) | startup |
| --- | --- | --- |
| scrcpy default | 298ms | 1179ms |
| `c2.qti.avc.encoder` (hw) | 284ms | 957ms |
| `c2.android.avc.encoder` (sw) | 375ms | 1350ms |
| `c2.qti.hevc.encoder` | stream failed | - |

Hardware AVC wins, and scrcpy already picks it by default, so `encoder` stays
unset - naming `c2.qti.*` outright would break every non-Qualcomm device.

Decoder buffering: `fflags=nobuffer` passed to `av.open` is actively harmful,
starving the demuxer so the first frame takes 21.9s instead of 0.03s. Setting
`low_delay` on the decoder *after* open costs nothing and is roughly
lag-neutral (396ms vs 383ms), so it is kept but is not where the win is.
