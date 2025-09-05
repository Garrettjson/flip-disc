# RBM (Raw Bitmap) Frame Format — v1

A compact, language-agnostic, versioned binary framing for 1‑bit packed bitmaps.

Authoritative rules:

- Multi-byte integers are big-endian (network order).
- Pixels are row-major, MSB-first within each byte.
- Row stride is `ceil(width / 8)` bytes; rows are tightly packed with no extra padding beyond the stride.

Header layout (fixed 16 bytes):

- `magic` (2 bytes): ASCII `RB`
- `version` (1 byte): `1`
- `flags` (1 byte): bitfield (bit 0: invert, others reserved)
- `width` (2 bytes, uint16)
- `height` (2 bytes, uint16)
- `seq` (4 bytes, uint32) — monotonically increasing frame sequence number
- `frame_duration_ms` (2 bytes, uint16) — intended display duration; 0 means “asap”
- `reserved` (2 bytes): set to 0 for now

Payload:

- `bitmap` (N bytes): `height * ceil(width/8)` bytes of packed bits, row-major, MSB-first per byte.

Notes:

- The payload length is implied by width/height; transports that require explicit length (e.g., TCP) should send the header + payload in a single message boundary or prefix with a length in their own envelope.
- Sequence numbers wrap at `2^32`; receivers should accept wrap-around.
- Invert flag can be used for displays wired with reversed polarity; default is 0 (no invert).

Compatibility:

- This format is intended to be stable across Go, Python, and TypeScript implementations.
- Future expansions can add alternative formats (e.g., XOR or dirty rects) gated by `flags` or a new `format_id` if needed.

