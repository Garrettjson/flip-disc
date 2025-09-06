from __future__ import annotations

from dataclasses import dataclass

from .rbm import encode_rbm


@dataclass
class IngestClient:
    """Posts RBM frames to the orchestrator ingest endpoint.

    Display/config are delivered over WebSocket; this client only handles frame POSTs.
    """

    orch_url: str
    worker_id: str

    def post_rbm(self, bits: bytes, width: int, height: int, seq: int) -> None:
        """POST RBM payload to orchestrator; duration remains 0 (orchestrator owns pacing)."""
        import urllib.request

        url = f"{self.orch_url}/workers/{self.worker_id}/frame"
        payload = encode_rbm(bits, width, height, seq=seq, frame_duration_ms=0)
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/octet-stream")
        with urllib.request.urlopen(req, timeout=5) as resp:  # drain response
            _ = resp.read()

