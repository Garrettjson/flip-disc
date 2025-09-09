// This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define(['exports', 'kaitai-struct/KaitaiStream'], factory);
  } else if (typeof exports === 'object' && exports !== null && typeof exports.nodeType !== 'number') {
    factory(exports, require('kaitai-struct/KaitaiStream'));
  } else {
    factory(root.FlipdiscFrame || (root.FlipdiscFrame = {}), root.KaitaiStream);
  }
})(typeof self !== 'undefined' ? self : this, function (FlipdiscFrame_, KaitaiStream) {
/**
 * Binary protocol for flip disc display frames.
 * 
 * Each frame contains:
 * - Fixed 16-byte header with magic, sequence, timestamp, dimensions
 * - Variable-length bitmap payload (1 bit per pixel, packed)
 * 
 * The payload length is validated to match ceil(width/8) * height.
 */

var FlipdiscFrame = (function() {
  function FlipdiscFrame(_io, _parent, _root) {
    this._io = _io;
    this._parent = _parent;
    this._root = _root || this;

    this._read();
  }
  FlipdiscFrame.prototype._read = function() {
    this.magic = this._io.readBytes(4);
    if (!((KaitaiStream.byteArrayCompare(this.magic, new Uint8Array([70, 68, 73, 83])) == 0))) {
      throw new KaitaiStream.ValidationNotEqualError(new Uint8Array([70, 68, 73, 83]), this.magic, this._io, "/seq/0");
    }
    this.seq = this._io.readU2le();
    this.timestamp = this._io.readU4le();
    this.width = this._io.readU2le();
    if (!(this.width >= 1)) {
      throw new KaitaiStream.ValidationLessThanError(1, this.width, this._io, "/seq/3");
    }
    if (!(this.width <= 1024)) {
      throw new KaitaiStream.ValidationGreaterThanError(1024, this.width, this._io, "/seq/3");
    }
    this.height = this._io.readU2le();
    if (!(this.height >= 1)) {
      throw new KaitaiStream.ValidationLessThanError(1, this.height, this._io, "/seq/4");
    }
    if (!(this.height <= 1024)) {
      throw new KaitaiStream.ValidationGreaterThanError(1024, this.height, this._io, "/seq/4");
    }
    this.payloadLen = this._io.readU2le();
    var _ = this.payloadLen;
    if (!(this.payloadLen == this.expectedPayloadLen)) {
      throw new KaitaiStream.ValidationExprError(this.payloadLen, this._io, "/seq/5");
    }
    this.bitmapData = this._io.readBytes(this.payloadLen);
  }

  /**
   * Number of bytes needed per row of pixels
   */
  Object.defineProperty(FlipdiscFrame.prototype, 'bytesPerRow', {
    get: function() {
      if (this._m_bytesPerRow !== undefined)
        return this._m_bytesPerRow;
      this._m_bytesPerRow = Math.floor((this.width + 7) / 8);
      return this._m_bytesPerRow;
    }
  });

  /**
   * Expected payload length based on width and height
   */
  Object.defineProperty(FlipdiscFrame.prototype, 'expectedPayloadLen', {
    get: function() {
      if (this._m_expectedPayloadLen !== undefined)
        return this._m_expectedPayloadLen;
      this._m_expectedPayloadLen = Math.floor((this.width + 7) / 8) * this.height;
      return this._m_expectedPayloadLen;
    }
  });

  /**
   * Total number of pixels in the frame
   */
  Object.defineProperty(FlipdiscFrame.prototype, 'totalPixels', {
    get: function() {
      if (this._m_totalPixels !== undefined)
        return this._m_totalPixels;
      this._m_totalPixels = this.width * this.height;
      return this._m_totalPixels;
    }
  });

  /**
   * Magic number identifying flip disc frame format
   */

  /**
   * Sequence number for frame ordering
   */

  /**
   * Unix timestamp when frame was generated
   */

  /**
   * Frame width in pixels
   */

  /**
   * Frame height in pixels
   */

  /**
   * Length of bitmap data in bytes
   */

  /**
   * Packed bitmap data (1 bit per pixel, MSB first)
   */

  return FlipdiscFrame;
})();
FlipdiscFrame_.FlipdiscFrame = FlipdiscFrame;
});
