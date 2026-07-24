// Runs off the main thread (AudioWorkletGlobalScope) — downsamples mic audio to
// 16kHz PCM16LE and posts fixed-size chunks back to the main thread, mirroring
// what the deprecated ScriptProcessorNode used to do inline. Self-contained
// (no imports available in this scope), so the downsample/PCM16 conversion
// logic here intentionally mirrors lib/pcm.ts rather than sharing it.

const TARGET_SAMPLE_RATE = 16000
const TARGET_CHUNK_SAMPLES_AT_16K = 4096

function downsampleTo16k(input, inputSampleRate) {
  if (inputSampleRate === TARGET_SAMPLE_RATE) return input

  const ratio = inputSampleRate / TARGET_SAMPLE_RATE
  const outLength = Math.floor(input.length / ratio)
  const output = new Float32Array(outLength)

  for (let i = 0; i < outLength; i++) {
    const srcPos = i * ratio
    const i0 = Math.floor(srcPos)
    const i1 = Math.min(i0 + 1, input.length - 1)
    const frac = srcPos - i0
    output[i] = input[i0] * (1 - frac) + input[i1] * frac
  }
  return output
}

function floatTo16BitPCM(input) {
  const buffer = new ArrayBuffer(input.length * 2)
  const view = new DataView(buffer)
  for (let i = 0; i < input.length; i++) {
    const clamped = Math.max(-1, Math.min(1, input[i]))
    view.setInt16(i * 2, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true)
  }
  return buffer
}

class PCMRecorderProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this._buffer = []
  }

  process(inputs) {
    const channelData = inputs[0] && inputs[0][0]
    if (!channelData) return true

    for (let i = 0; i < channelData.length; i++) {
      this._buffer.push(channelData[i])
    }

    const chunkSizeAtNativeRate = Math.ceil(TARGET_CHUNK_SAMPLES_AT_16K * (sampleRate / TARGET_SAMPLE_RATE))
    while (this._buffer.length >= chunkSizeAtNativeRate) {
      const chunk = new Float32Array(this._buffer.splice(0, chunkSizeAtNativeRate))
      const downsampled = downsampleTo16k(chunk, sampleRate)
      const pcm16 = floatTo16BitPCM(downsampled)
      this.port.postMessage(pcm16, [pcm16])
    }

    return true
  }
}

registerProcessor("pcm-recorder-processor", PCMRecorderProcessor)
