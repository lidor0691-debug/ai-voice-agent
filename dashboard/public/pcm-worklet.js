/**
 * PCM16 AudioWorklet processor.
 *
 * Captures raw PCM16 mono audio at the AudioContext's sample rate (16kHz).
 * Buffers ~100ms of samples before posting to the main thread as an
 * ArrayBuffer of Int16 values, ready for base64 encoding and WebSocket send.
 *
 * Runs entirely in the audio rendering thread — zero main-thread blocking.
 */
class PCM16Processor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Float32Array(0);
    // 1600 samples at 16kHz = 100ms chunks
    this._bufferSize = 1600;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const samples = input[0]; // mono channel 0

    // Append incoming samples to internal buffer
    const newBuf = new Float32Array(this._buffer.length + samples.length);
    newBuf.set(this._buffer);
    newBuf.set(samples, this._buffer.length);
    this._buffer = newBuf;

    // Flush complete chunks
    while (this._buffer.length >= this._bufferSize) {
      const chunk = this._buffer.slice(0, this._bufferSize);
      this._buffer = this._buffer.slice(this._bufferSize);

      // Convert Float32 [-1, 1] to Int16 [-32768, 32767]
      const pcm16 = new Int16Array(chunk.length);
      for (let i = 0; i < chunk.length; i++) {
        const s = Math.max(-1, Math.min(1, chunk[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }

      // Transfer ownership (zero-copy) to main thread
      this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    }

    return true; // keep processor alive
  }
}

registerProcessor("pcm16-processor", PCM16Processor);
