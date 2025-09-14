import numpy as np

from flipdisc.hardware.formats import encode_panel_message, panel_bits_to_column_bytes


def test_panel_bits_to_column_bytes_basic():
    # 7x7 with a diagonal from top-left to bottom-right
    bits = np.zeros((7, 7), dtype=bool)
    for i in range(7):
        bits[i, i] = True
    col_bytes = panel_bits_to_column_bytes(bits)
    # Each column i should have bit i set => value == (1 << i)
    assert len(col_bytes) == 7
    assert list(col_bytes) == [1 << i for i in range(7)]


def test_encode_panel_message_cmds():
    for w, expected_cmd in [(7, 0x87), (14, 0x93), (28, 0x84)]:
        bits = np.zeros((7, w), dtype=bool)
        msg = encode_panel_message(bits, address=1, refresh=(w == 7))
        assert msg[0] == 0x80
        assert msg[1] == expected_cmd
        assert msg[-1] == 0x8F
        # Data length should equal width
        assert len(msg) == 1 + 1 + 1 + w + 1
