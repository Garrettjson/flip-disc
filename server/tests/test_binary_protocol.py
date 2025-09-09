#!/usr/bin/env python3
"""
Test script for flip disc binary protocol
Tests the Kaitai-generated parser with sample frame data
"""

import sys

try:
    from gen.py.flipdisc_frame import FlipdiscFrame
    print("✓ Successfully imported Kaitai parser")
except ImportError as e:
    print(f"✗ Failed to import Kaitai parser: {e}")
    sys.exit(1)

def create_test_frame(width=28, height=7, seq=1):
    """Create a test frame with checkerboard pattern"""
    # Calculate payload size
    payload_len = ((width + 7) // 8) * height
    
    # Create checkerboard pattern
    bitmap_data = bytearray(payload_len)
    for y in range(height):
        row_start_byte = y * ((width + 7) // 8)
        for x in range(width):
            bit_pos = 7 - (x % 8)
            byte_idx = row_start_byte + x // 8
            if (x + y) % 2 == 0:  # Checkerboard pattern
                bitmap_data[byte_idx] |= (1 << bit_pos)
    
    # Build complete frame according to our binary protocol
    frame_data = bytearray()
    
    # Magic "FDIS" (0x46444953)
    frame_data.extend([0x46, 0x44, 0x49, 0x53])
    
    # Sequence number (2 bytes, little-endian)
    frame_data.extend(seq.to_bytes(2, 'little'))
    
    # Timestamp (4 bytes, little-endian)
    timestamp = 1694649600  # Fixed timestamp for testing
    frame_data.extend(timestamp.to_bytes(4, 'little'))
    
    # Width (2 bytes, little-endian)
    frame_data.extend(width.to_bytes(2, 'little'))
    
    # Height (2 bytes, little-endian)
    frame_data.extend(height.to_bytes(2, 'little'))
    
    # Payload length (2 bytes, little-endian)
    frame_data.extend(payload_len.to_bytes(2, 'little'))
    
    # Bitmap data
    frame_data.extend(bitmap_data)
    
    return bytes(frame_data)

def test_valid_frame():
    """Test parsing a valid frame"""
    print("\n🧪 Testing valid frame parsing...")
    
    frame_data = create_test_frame(28, 7, 42)
    
    try:
        parsed = FlipdiscFrame.from_bytes(frame_data)
        
        print(f"✓ Magic: {parsed.magic.hex()}")
        print(f"✓ Sequence: {parsed.seq}")
        print(f"✓ Timestamp: {parsed.timestamp}")
        print(f"✓ Dimensions: {parsed.width}x{parsed.height}")
        print(f"✓ Payload length: {parsed.payload_len}")
        print(f"✓ Expected payload length: {parsed.expected_payload_len}")
        print(f"✓ Bitmap data size: {len(parsed.bitmap_data)}")
        
        # Verify validation works
        assert parsed.payload_len == parsed.expected_payload_len
        assert len(parsed.bitmap_data) == parsed.payload_len
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to parse valid frame: {e}")
        return False

def test_invalid_magic():
    """Test frame with invalid magic number"""
    print("\n🧪 Testing invalid magic number...")
    
    frame_data = bytearray(create_test_frame(28, 7, 1))
    frame_data[0:4] = b"BADD"  # Replace magic with "BADD"
    
    try:
        parsed = FlipdiscFrame.from_bytes(bytes(frame_data))
        print("✗ Should have failed with invalid magic")
        return False
    except Exception as e:
        print(f"✓ Correctly rejected invalid magic: {type(e).__name__}")
        return True

def test_payload_mismatch():
    """Test frame with mismatched payload length"""
    print("\n🧪 Testing payload length mismatch...")
    
    frame_data = bytearray(create_test_frame(28, 7, 1))
    # Change payload length to incorrect value (should be 25 for 28x7)
    frame_data[14] = 10  
    frame_data[15] = 0
    
    try:
        parsed = FlipdiscFrame.from_bytes(bytes(frame_data))
        print("✗ Should have failed with payload mismatch")
        return False
    except Exception as e:
        print(f"✓ Correctly rejected payload mismatch: {type(e).__name__}")
        return True

def main():
    print("🚀 Testing Flip Disc Binary Protocol")
    print("=" * 50)
    
    tests = [
        test_valid_frame,
        test_invalid_magic,
        test_payload_mismatch,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Binary protocol implementation is working.")
        print("\n📋 Summary:")
        print("✓ Kaitai schema correctly defines the protocol")
        print("✓ Generated Python parser validates frames properly")
        print("✓ Protocol includes magic number, dimensions, and payload validation")
        print("✓ Ready for integration with server and orchestrator")
        return 0
    else:
        print("❌ Some tests failed. Check implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())