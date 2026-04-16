"""
Minimal audio conversion utilities for the Gemini Live POC bridge.

Twilio Media Streams: G.711 μ-law, 8 kHz, mono, base64-encoded.
Gemini Live input:    PCM16 LE, 16 kHz, mono, base64-encoded.
Gemini Live output:   PCM16 LE, 24 kHz, mono, base64-encoded.

Pure-Python implementation — no numpy / audioop dependency.
audioop was removed in Python 3.13; this file replaces it for the POC.
"""

import base64
import struct

# ── μ-law constants ───────────────────────────────────────────────────────────
_ULAW_BIAS = 132   # 0x84 — standard G.711 bias


def _ulaw_to_linear(byte_val: int) -> int:
    """Decode a single G.711 μ-law byte to a signed 16-bit linear PCM sample."""
    byte_val = ~byte_val & 0xFF
    sign     = byte_val & 0x80
    exp      = (byte_val >> 4) & 0x07
    mantissa = byte_val & 0x0F
    linear   = ((mantissa << 1) + 33) << exp
    return -linear if sign else linear


def _linear_to_ulaw(sample: int) -> int:
    """Encode a signed 16-bit linear PCM sample to a G.711 μ-law byte."""
    sign = 0
    if sample < 0:
        sample = -sample
        sign   = 0x80
    sample = min(sample + _ULAW_BIAS, 32767)
    # Standard G.711 exponent: find highest set bit position above bit 5
    exp = 7
    for exp_val, threshold in enumerate([0x100, 0x200, 0x400, 0x800,
                                          0x1000, 0x2000, 0x4000, 0x8000]):
        if sample < threshold:
            exp = exp_val
            break
    mantissa = (sample >> (exp + 3)) & 0x0F
    return (~(sign | (exp << 4) | mantissa)) & 0xFF


# ── Conversion: Twilio → Gemini ───────────────────────────────────────────────

def twilio_to_gemini(b64_ulaw_8k: str) -> str:
    """
    Convert a base64 G.711 μ-law 8 kHz chunk (Twilio inbound)
    to base64 PCM16 LE 16 kHz (Gemini Live input).

    Upsampling 8 kHz → 16 kHz: nearest-neighbour (duplicate each sample).
    Sufficient quality for a real-time phone call POC.
    """
    raw      = base64.b64decode(b64_ulaw_8k)
    # decode μ-law → 16-bit linear, then duplicate each sample for 2× rate
    samples  = []
    for byte in raw:
        s = _ulaw_to_linear(byte)
        samples.append(s)
        samples.append(s)   # duplicate → 16 kHz
    pcm_bytes = struct.pack(f"<{len(samples)}h", *samples)
    return base64.b64encode(pcm_bytes).decode("ascii")


# ── Conversion: Gemini → Twilio ───────────────────────────────────────────────

def gemini_to_twilio(b64_pcm16_24k: str) -> str:
    """
    Convert a base64 PCM16 LE 24 kHz chunk (Gemini Live output)
    to base64 G.711 μ-law 8 kHz (Twilio outbound media payload).

    Downsampling 24 kHz → 8 kHz: keep every 3rd sample.
    """
    raw      = base64.b64decode(b64_pcm16_24k)
    n        = len(raw) // 2
    samples  = struct.unpack(f"<{n}h", raw[:n * 2])
    # Average every group of 3 samples (box filter) then take one per group.
    # Simple anti-aliasing — much cleaner than plain decimation (samples[::3]).
    n3 = (len(samples) // 3) * 3
    downsampled = [
        (samples[i] + samples[i + 1] + samples[i + 2]) // 3
        for i in range(0, n3, 3)
    ]
    ulaw_bytes  = bytes(_linear_to_ulaw(s) for s in downsampled)
    return base64.b64encode(ulaw_bytes).decode("ascii")
