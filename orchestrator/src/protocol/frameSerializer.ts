/**
 * Frame Serializer for Flip Disc Binary Protocol
 * 
 * Creates binary frame data using the Kaitai Struct protocol definition.
 * Format: [4B magic][2B seq][4B ts][2B width][2B height][2B payload_len][N bytes bitmap]
 */

export interface FrameData {
  width: number;
  height: number;
  bitmap: Uint8Array;
  sequenceNumber?: number;
  timestamp?: number;
}

export class FrameSerializer {
  private static sequenceCounter = 0;
  
  /**
   * Serialize frame data into binary format according to flip disc protocol
   */
  static serialize(frameData: FrameData): ArrayBuffer {
    const {
      width,
      height,
      bitmap,
      sequenceNumber = this.getNextSequence(),
      timestamp = Math.floor(Date.now() / 1000) // Unix timestamp
    } = frameData;

    // Validate input
    this.validateFrame(width, height, bitmap);

    // Calculate payload length
    const expectedPayloadLen = Math.ceil(width / 8) * height;
    if (bitmap.length !== expectedPayloadLen) {
      throw new Error(`Bitmap size ${bitmap.length} doesn't match expected ${expectedPayloadLen} for ${width}x${height}`);
    }

    // Create binary frame according to protocol
    const headerSize = 16; // Fixed header size
    const totalSize = headerSize + bitmap.length;
    const buffer = new ArrayBuffer(totalSize);
    const view = new DataView(buffer);
    const bytes = new Uint8Array(buffer);
    
    let offset = 0;
    
    // Magic number "FDIS" as literal bytes
    bytes.set([0x46, 0x44, 0x49, 0x53], offset);
    offset += 4;
    
    // Sequence number (2 bytes)
    view.setUint16(offset, sequenceNumber & 0xFFFF, true);
    offset += 2;
    
    // Timestamp (4 bytes)
    view.setUint32(offset, timestamp, true);
    offset += 4;
    
    // Width (2 bytes)
    view.setUint16(offset, width, true);
    offset += 2;
    
    // Height (2 bytes)
    view.setUint16(offset, height, true);
    offset += 2;
    
    // Payload length (2 bytes)
    view.setUint16(offset, bitmap.length, true);
    offset += 2;
    
    // Bitmap data
    const bitmapView = new Uint8Array(buffer, offset);
    bitmapView.set(bitmap);
    
    return buffer;
  }

  /**
   * Create a frame from canvas bitmap data
   */
  static createFrameFromBitmap(width: number, height: number, bitmap: boolean[]): FrameData {
    if (bitmap.length !== width * height) {
      throw new Error(`Bitmap array size ${bitmap.length} doesn't match ${width}x${height} = ${width * height}`);
    }

    // Pack bitmap into bytes (8 pixels per byte, MSB first)
    const packedBytes = Math.ceil(width / 8) * height;
    const packedBitmap = new Uint8Array(packedBytes);
    
    for (let y = 0; y < height; y++) {
      const rowStartBit = y * width;
      const rowStartByte = y * Math.ceil(width / 8);
      
      for (let x = 0; x < width; x++) {
        const bitIndex = rowStartBit + x;
        const byteIndex = rowStartByte + Math.floor(x / 8);
        const bitPosition = 7 - (x % 8); // MSB first
        
        if (bitmap[bitIndex]) {
          packedBitmap[byteIndex] |= (1 << bitPosition);
        }
      }
    }

    return {
      width,
      height,
      bitmap: packedBitmap
    };
  }

  /**
   * Validate frame parameters
   */
  private static validateFrame(width: number, height: number, bitmap: Uint8Array): void {
    if (width < 1 || width > 1024) {
      throw new Error(`Invalid width: ${width}. Must be between 1 and 1024`);
    }
    
    if (height < 1 || height > 1024) {
      throw new Error(`Invalid height: ${height}. Must be between 1 and 1024`);
    }
    
    if (!bitmap || bitmap.length === 0) {
      throw new Error('Bitmap data is required');
    }
  }

  /**
   * Get next sequence number (wraps at 65535)
   */
  private static getNextSequence(): number {
    this.sequenceCounter = (this.sequenceCounter + 1) % 65536;
    return this.sequenceCounter;
  }

  /**
   * Reset sequence counter (useful for testing)
   */
  static resetSequence(): void {
    this.sequenceCounter = 0;
  }
}
