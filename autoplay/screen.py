"""Live screen capture via scrcpy's server, decoded with PyAV.

A background thread pulls the H.264 stream off the scrcpy socket and keeps the
newest decoded frame; `latest()` hands that frame to the matching code. Falls
back to `adb exec-out screencap` if the stream cannot be established.
"""

import os
import random
import socket
import threading
import time

import av
import cv2
import numpy as np

from .log import step

SERVER_JAR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vendor", "scrcpy-server.jar")
SERVER_VERSION = "3.1"
REMOTE_JAR = "/data/local/tmp/autoplay-scrcpy-server.jar"

# Stream tuning - see .agent/design.md task 3, measured with the bench_*.py
# scripts on a 1080x2400 device.
#
# max_size caps the LONGEST edge, so on a tall phone it is roughly 2.2x the
# frame width. Two limits bracket the choice:
#
#   - Template matching cost scales with frame area and dominates every step.
#     A first sweep for close-popup costs 7.5s on the native 864x1920 frame but
#     2.7s at 540x1200, and a cached re-match 275ms vs 51ms. At native a single
#     find() can outlast the timeout the caller is waiting inside, so the poll
#     loop gets one attempt and gives up.
#   - OCR has a hard floor. RapidOCR reads the notification prompt fine down to
#     495x1100 and loses it at 472x1050 - a cliff, not a slope. OCR runtime is
#     near-flat across sizes (it downscales internally), so there is nothing to
#     win by going below it anyway.
#
# 1200 sits above the OCR cliff with headroom while cutting match cost ~3x.
DEFAULT_MAX_SIZE = 1200  # longest edge in px; 0 would stream the device's own size
DEFAULT_BIT_RATE = 8_000_000  # a 540-wide stream does not need 12 Mbps
# 15 and 30 measured the same glass-to-frame lag (~350-400ms); 60 was far worse
# (935ms). 30 is the cheaper of the two equals in frame age.
DEFAULT_MAX_FPS = 30


class ScreenError(RuntimeError):
    pass


class _SocketSource:
    """File-like adapter so PyAV can read the scrcpy socket directly."""

    def __init__(self, sock, prefix=b"", stop=None):
        self._sock = sock
        self._prefix = prefix
        self._stop = stop

    def read(self, size):
        if self._prefix:
            chunk, self._prefix = self._prefix[:size], self._prefix[size:]
            return chunk
        while self._stop is None or not self._stop.is_set():
            try:
                return self._sock.recv(size)
            except socket.timeout:
                continue
            except OSError:
                return b""
        return b""


class Screen:
    def __init__(
        self,
        device,
        port=27183,
        bit_rate=DEFAULT_BIT_RATE,
        max_fps=DEFAULT_MAX_FPS,
        max_size=DEFAULT_MAX_SIZE,
        encoder=None,
    ):
        self.device = device
        self.port = port
        self.bit_rate = bit_rate
        self.max_fps = max_fps
        self.max_size = max_size
        self.encoder = encoder

        self._proc = None
        self._sock = None
        self._thread = None
        self._stop = threading.Event()
        self._frame = None
        self._frame_lock = threading.Lock()
        self._frame_event = threading.Event()
        self._streaming = False
        # scid must be a positive 31-bit hex value
        self._scid = f"{random.randint(1, 0x7FFFFFFF):08x}"

    # -- lifecycle -------------------------------------------------------

    def start(self):
        try:
            self._start_stream()
            self._streaming = True
            frame = self.latest()
            fh, fw = frame.shape[:2]
            scaled = "" if (fw, fh) == (self.device.width, self.device.height) else (
                f" (scaled from {self.device.width}x{self.device.height})"
            )
            step(f"screen: live stream {fw}x{fh} via scrcpy{scaled}")
        except Exception as exc:  # noqa: BLE001 - fall back to slower capture
            self.stop()
            self._streaming = False
            step(f"screen: scrcpy stream unavailable ({exc}); using adb screencap")

    def _start_stream(self):
        if not os.path.exists(SERVER_JAR):
            raise ScreenError(f"missing {SERVER_JAR}")
        self.device.push(SERVER_JAR, REMOTE_JAR)

        local = f"tcp:{self.port}"
        self.device.forward_remove(local)
        self.device.forward(local, f"localabstract:scrcpy_{self._scid}")

        args = [
            "shell",
            f"CLASSPATH={REMOTE_JAR}",
            "app_process",
            "/",
            "com.genymobile.scrcpy.Server",
            SERVER_VERSION,
            f"scid={self._scid}",
            "tunnel_forward=true",
            "audio=false",
            "control=false",
            "cleanup=false",
            "raw_stream=true",
            f"max_size={self.max_size}",
            f"video_bit_rate={self.bit_rate}",
            f"max_fps={self.max_fps}",
        ]
        if self.encoder:
            args.append(f"video_encoder={self.encoder}")
        self._proc = self.device.popen(*args)

        self._sock, first_chunk = self._connect()

        self._stop.clear()
        self._frame_event.clear()
        self._thread = threading.Thread(target=self._reader, args=(first_chunk,), daemon=True)
        self._thread.start()

        if not self._frame_event.wait(timeout=10):
            raise ScreenError("no video frame received within 10s")

    def _connect(self, timeout=15):
        """Connect to the forwarded scrcpy socket and return it with its first bytes.

        `adb forward` accepts the TCP connection even before the server has bound
        its abstract socket, and such a premature connection just reports EOF. So
        a connection only counts once it has actually delivered data.
        """
        deadline = time.time() + timeout
        last_err = "timed out"
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise ScreenError("scrcpy server exited during startup")
            sock = None
            try:
                sock = socket.create_connection(("127.0.0.1", self.port), timeout=3)
                sock.settimeout(2.0)
                chunk = sock.recv(1 << 16)
                if chunk:
                    return sock, chunk
                last_err = "server not listening yet (EOF)"
            except OSError as exc:
                last_err = str(exc)
            if sock is not None:
                sock.close()
            time.sleep(0.3)
        raise ScreenError(f"cannot connect to scrcpy socket: {last_err}")

    def _reader(self, first_chunk=b""):
        """Demux and decode the stream until stopped.

        PyAV reads the socket itself through a file-like wrapper. Hand-feeding
        `recv()` chunks into `CodecContext.parse()` instead looks simpler, but
        a chunk boundary that splits a NAL unit can desynchronise the parser
        badly enough to fault inside libav - so let PyAV own the framing.
        """
        source = _SocketSource(self._sock, first_chunk, self._stop)
        try:
            # The format is known, so keep probing short - it is startup latency
            # paid on every run.
            container = av.open(
                source,
                format="h264",
                mode="r",
                buffer_size=1 << 16,
                options={"probesize": "32", "analyzeduration": "0"},
            )
        except Exception:  # noqa: BLE001 - surfaced by the frame-wait timeout
            return
        try:
            # Ask the decoder to emit each frame as soon as it is decoded rather
            # than holding any reorder buffer. This has to be set after open:
            # passing `fflags=nobuffer` to av.open instead starves the demuxer
            # at startup - measured 21.9s to the first frame instead of 0.03s.
            stream = container.streams.video[0]
            stream.thread_type = "NONE"
            stream.codec_context.flags |= av.codec.context.Flags.low_delay
        except Exception:  # noqa: BLE001 - a nice-to-have, not worth failing over
            pass
        try:
            for frame in container.decode(video=0):
                if self._stop.is_set():
                    break
                # Own the pixels outright: the decoder recycles its frame
                # buffers, so handing one to the main thread lets a later
                # decode rewrite it mid-match.
                img = np.ascontiguousarray(frame.to_ndarray(format="bgr24"))
                with self._frame_lock:
                    self._frame = img
                self._frame_event.set()
        except Exception:  # noqa: BLE001 - the stream ends when the session does
            pass
        finally:
            try:
                container.close()
            except Exception:  # noqa: BLE001
                pass

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                self._proc.kill()
            self._proc = None
        self.device.forward_remove(f"tcp:{self.port}")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    # -- frames ----------------------------------------------------------

    def latest(self, max_age=0.0):
        """Return the newest screen frame as a BGR ndarray."""
        if not self._streaming:
            return self._screencap()
        if max_age > 0:
            # Force a fresher frame than whatever is currently buffered.
            self._frame_event.clear()
            self._frame_event.wait(timeout=max_age)
        with self._frame_lock:
            frame = self._frame
        if frame is None:
            return self._screencap()
        # Callers hold a frame across slow matching work, so give them a copy
        # rather than the buffer the reader thread keeps replacing.
        return frame.copy()

    def to_device(self, x, y):
        """Map a point in frame coordinates to device coordinates.

        The encoder may refuse the device's exact resolution and scrcpy then
        streams a smaller frame (e.g. 864x1920 for a 1080x2400 screen), so
        matches found in a frame have to be scaled before they can be tapped.
        """
        with self._frame_lock:
            frame = self._frame
        if frame is None:
            return int(x), int(y)
        fh, fw = frame.shape[:2]
        if not fw or not fh:
            return int(x), int(y)
        return (
            int(round(x * self.device.width / fw)),
            int(round(y * self.device.height / fh)),
        )

    def _screencap(self):
        png = self.device.screencap()
        img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ScreenError("screencap returned an undecodable image")
        return img
