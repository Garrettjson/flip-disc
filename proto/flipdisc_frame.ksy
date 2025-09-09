meta:
  id: flipdisc_frame
  title: Flip Disc Display Frame Protocol
  file-extension: flipdisc
  endian: le
  encoding: UTF-8
  license: MIT

doc: |
  Binary protocol for flip disc display frames.
  
  Each frame contains:
  - Fixed 16-byte header with magic, sequence, timestamp, dimensions
  - Variable-length bitmap payload (1 bit per pixel, packed)
  
  The payload length is validated to match ceil(width/8) * height.

seq:
  - id: magic
    contents: [0x46, 0x44, 0x49, 0x53]  # "FDIS" magic number
    doc: Magic number identifying flip disc frame format
    
  - id: seq
    type: u2
    doc: Sequence number for frame ordering
    
  - id: timestamp
    type: u4
    doc: Unix timestamp when frame was generated
    
  - id: width
    type: u2
    doc: Frame width in pixels
    valid:
      min: 1
      max: 1024
    
  - id: height
    type: u2
    doc: Frame height in pixels  
    valid:
      min: 1
      max: 1024
      
  - id: payload_len
    type: u2
    doc: Length of bitmap data in bytes
    valid:
      expr: payload_len == expected_payload_len
      
  - id: bitmap_data
    size: payload_len
    doc: Packed bitmap data (1 bit per pixel, MSB first)

instances:
  expected_payload_len:
    value: ((width + 7) / 8) * height
    doc: Expected payload length based on width and height
    
  total_pixels:
    value: width * height
    doc: Total number of pixels in the frame
    
  bytes_per_row:
    value: (width + 7) / 8
    doc: Number of bytes needed per row of pixels