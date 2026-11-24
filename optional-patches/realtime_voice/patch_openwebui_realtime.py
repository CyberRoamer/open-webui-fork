#!/usr/bin/env python3
"""
Applies offline Realtime Voice capability patch to Open WebUI's CallOverlay in D5GoHi-U.js.
Adds RealtimeVoiceClient that establishes WebSocket connection to /api/v1/audio/realtime/ws,
streams 16kHz PCM audio frames, handles barge-in cancellations, and plays streaming audio deltas.
"""

import sys
import shutil

TARGET_FILES = [
    "/mnt/ai-docker/litellm/open-webui-patches/D5GoHi-U.js",
    "/mnt/ai-docker/gateway/open-webui-patches/D5GoHi-U.js",
]

RT_CLASS_CODE = r"""
class RealtimeVoiceClient {
  constructor(opts) {
    this.opts = opts || {};
    this.ws = null;
    this.audioCtx = null;
    this.scriptNode = null;
    this.sourceNode = null;
    this.playQueue = [];
    this.isPlaying = false;
    this.currentSource = null;
    this.connected = false;
    this.targetRate = 22050;
  }
  connect() {
    try {
      const loc = window.location;
      const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = proto + '//' + loc.host + '/api/v1/audio/realtime/ws';
      this.ws = new WebSocket(wsUrl);
      this.ws.binaryType = 'arraybuffer';
      this.ws.onopen = () => {
        this.connected = true;
        console.log('[RealtimeVoice] WebSocket connected to Gateway proxy');
        this.ws.send(JSON.stringify({
          type: 'session.update',
          session: {
            llm_model: this.opts.modelId || 'GLM-4.7-Flash',
            tts_voice: this.opts.voice || 'en_US-lessac-medium',
            protocol_mode: 'openai'
          }
        }));
      };
      this.ws.onmessage = (ev) => {
        if (ev.data instanceof ArrayBuffer) {
          this.enqueuePcm(new Int16Array(ev.data));
          return;
        }
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === 'response.audio.delta' || msg.type === 'assistant.audio.delta') {
            const b64 = msg.delta || msg.audio;
            if (b64) {
              const bin = atob(b64);
              const bytes = new Uint8Array(bin.length);
              for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
              this.enqueuePcm(new Int16Array(bytes.buffer));
            }
          } else if (msg.type === 'response.cancelled' || msg.type === 'interrupted') {
            this.stopPlayback();
            if (this.opts.onInterrupted) this.opts.onInterrupted();
          } else if (msg.type === 'speech.started' || msg.type === 'input_audio_buffer.speech_started') {
            this.stopPlayback();
            if (this.opts.onSpeechStarted) this.opts.onSpeechStarted();
          } else if (msg.type === 'speech.stopped' || msg.type === 'input_audio_buffer.speech_stopped') {
            if (this.opts.onSpeechStopped) this.opts.onSpeechStopped();
          } else if (msg.type === 'user.transcription') {
            if (this.opts.onUserTranscript) this.opts.onUserTranscript(msg.text);
          }
        } catch (e) {
          console.warn('[RealtimeVoice] msg parse err', e);
        }
      };
      this.ws.onerror = (e) => {
        console.warn('[RealtimeVoice] WebSocket error, fallback to REST', e);
        this.connected = false;
      };
      this.ws.onclose = () => {
        this.connected = false;
      };
    } catch (e) {
      console.warn('[RealtimeVoice] Init error', e);
      this.connected = false;
    }
  }
  startStreaming(stream, ctx) {
    if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
    this.audioCtx = ctx;
    const src = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(2048, 1, 1);
    proc.onaudioprocess = (e) => {
      if (!this.connected || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      if (this.opts.isMuted && this.opts.isMuted()) return;
      const inp = e.inputBuffer.getChannelData(0);
      const pcm16 = this.downsampleTo16k(inp, ctx.sampleRate);
      if (pcm16 && pcm16.length > 0) {
        this.ws.send(pcm16.buffer);
      }
    };
    src.connect(proc);
    proc.connect(ctx.destination);
    this.sourceNode = src;
    this.scriptNode = proc;
  }
  downsampleTo16k(inp, srate) {
    if (srate === 16000) {
      const out = new Int16Array(inp.length);
      for (let i = 0; i < inp.length; i++) {
        let s = Math.max(-1, Math.min(1, inp[i]));
        out[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }
      return out;
    }
    const ratio = srate / 16000;
    const newLen = Math.round(inp.length / ratio);
    const out = new Int16Array(newLen);
    for (let i = 0; i < newLen; i++) {
      const idx = Math.min(Math.round(i * ratio), inp.length - 1);
      let s = Math.max(-1, Math.min(1, inp[idx]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return out;
  }
  enqueuePcm(int16Arr) {
    if (!this.audioCtx) this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const float32 = new Float32Array(int16Arr.length);
    for (let i = 0; i < int16Arr.length; i++) float32[i] = int16Arr[i] / 32768.0;
    const buf = this.audioCtx.createBuffer(1, float32.length, this.targetRate);
    buf.getChannelData(0).set(float32);
    this.playQueue.push(buf);
    if (!this.isPlaying) this.playNext();
    if (this.opts.onAssistantSpeaking) this.opts.onAssistantSpeaking(true);
  }
  playNext() {
    if (this.playQueue.length === 0) {
      this.isPlaying = false;
      if (this.opts.onAssistantSpeaking) this.opts.onAssistantSpeaking(false);
      return;
    }
    this.isPlaying = true;
    const buf = this.playQueue.shift();
    const src = this.audioCtx.createBufferSource();
    src.buffer = buf;
    src.connect(this.audioCtx.destination);
    this.currentSource = src;
    src.onended = () => {
      this.currentSource = null;
      this.playNext();
    };
    src.start();
  }
  stopPlayback() {
    this.playQueue = [];
    if (this.currentSource) {
      try { this.currentSource.stop(); } catch(e) {}
      this.currentSource = null;
    }
    this.isPlaying = false;
    if (this.opts.onAssistantSpeaking) this.opts.onAssistantSpeaking(false);
  }
  interrupt() {
    this.stopPlayback();
    if (this.connected && this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'response.cancel' }));
    }
  }
  disconnect() {
    this.stopPlayback();
    if (this.scriptNode) {
      try { this.scriptNode.disconnect(); } catch(e) {}
      this.scriptNode = null;
    }
    if (this.sourceNode) {
      try { this.sourceNode.disconnect(); } catch(e) {}
      this.sourceNode = null;
    }
    if (this.ws) {
      try { this.ws.close(); } catch(e) {}
      this.ws = null;
    }
    this.connected = false;
  }
}
"""

TARGET_FUNC_START = "function rf(e,t){Vt(t,!1);"
REPLACEMENT_FUNC_START = RT_CLASS_CODE + "\nfunction rf(e,t){Vt(t,!1);let rtClient=null;"

TARGET_TE = "te=ve=>{const de=new AudioContext,ze=de.createMediaStreamSource(ve),oe=de.createAnalyser();"
REPLACEMENT_TE = """te=ve=>{const de=new AudioContext,ze=de.createMediaStreamSource(ve),oe=de.createAnalyser();
if(!rtClient){try{rtClient=new RealtimeVoiceClient({modelId:H(),voice:ae(),isMuted:()=>r(V),onAssistantSpeaking:s=>c(W,s),onSpeechStarted:()=>{c(N,!0);c(W,!1)},onSpeechStopped:()=>{c(N,!1)},onInterrupted:()=>{c(W,!1)}});rtClient.connect()}catch(err){console.warn('Realtime init failed',err)}}
if(rtClient){try{rtClient.startStreaming(ve,de)}catch(err){console.warn('Realtime stream failed',err)}}"""

TARGET_ME = "Me=async(ve=!0)=>{if(i()){const de=C.slice(0);"
REPLACEMENT_ME = "Me=async(ve=!0)=>{if(rtClient&&rtClient.connected){C=[];y=!1;U=!1;c(N,!1);return}if(i()){const de=C.slice(0);"

TARGET_LE = ',le=async()=>{c(W,!1),D&&k()(),_e&&(speechSynthesis.cancel(),_e=null);const ve=document.getElementById("audioElement");ve&&(ve.muted=!0,'
REPLACEMENT_LE = ',le=async()=>{rtClient&&rtClient.interrupt();c(W,!1),D&&k()(),_e&&(speechSynthesis.cancel(),_e=null);const ve=document.getElementById("audioElement");ve&&(ve.muted=!0,'

def patch_file(filepath: str, backup: bool = True) -> bool:
    print(f"Checking {filepath}...")
    if not os.path.exists(filepath):
        print(f"  Warning: File does not exist: {filepath}")
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if "RealtimeVoiceClient" in content:
        print(f"  Already patched with RealtimeVoiceClient: {filepath}")
        return True

    # Validate version anchors
    missing = []
    if TARGET_FUNC_START not in content:
        missing.append("TARGET_FUNC_START")
    if TARGET_TE not in content:
        missing.append("TARGET_TE")
    if TARGET_ME not in content:
        missing.append("TARGET_ME")
    if TARGET_LE not in content:
        missing.append("TARGET_LE")

    if missing:
        raise RuntimeError(f"Cannot patch {filepath}: missing expected anchors {missing}. Open WebUI version mismatch.")

    # Create backup before modifying
    backup_path = f"{filepath}.orig"
    if backup and not os.path.exists(backup_path):
        shutil.copy2(filepath, backup_path)
        print(f"  Created backup at {backup_path}")

    # Perform atomic replacement
    content = content.replace(TARGET_FUNC_START, REPLACEMENT_FUNC_START, 1)
    content = content.replace(TARGET_TE, REPLACEMENT_TE, 1)
    content = content.replace(TARGET_ME, REPLACEMENT_ME, 1)
    content = content.replace(TARGET_LE, REPLACEMENT_LE, 1)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Successfully applied realtime voice patch to {filepath}")
    return True


def rollback_file(filepath: str) -> bool:
    print(f"Rolling back {filepath}...")
    backup_path = f"{filepath}.orig"
    if os.path.exists(backup_path):
        shutil.copy2(backup_path, filepath)
        print(f"  Successfully restored {filepath} from backup {backup_path}")
        return True

    if not os.path.exists(filepath):
        print(f"  Warning: File does not exist: {filepath}")
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if "RealtimeVoiceClient" not in content:
        print(f"  File is already clean (unpatched): {filepath}")
        return True

    # Reverse replacements
    content = content.replace(REPLACEMENT_LE, TARGET_LE, 1)
    content = content.replace(REPLACEMENT_ME, TARGET_ME, 1)
    content = content.replace(REPLACEMENT_TE, TARGET_TE, 1)
    content = content.replace(REPLACEMENT_FUNC_START, TARGET_FUNC_START, 1)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Successfully reversed patch in {filepath}")
    return True


def check_file(filepath: str) -> dict:
    if not os.path.exists(filepath):
        return {"filepath": filepath, "status": "missing"}
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    is_patched = "RealtimeVoiceClient" in content
    has_backup = os.path.exists(f"{filepath}.orig")
    has_anchors = (
        TARGET_FUNC_START in content or REPLACEMENT_FUNC_START in content
    )
    return {
        "filepath": filepath,
        "is_patched": is_patched,
        "has_backup": has_backup,
        "valid_bundle": has_anchors,
    }


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Manage Open WebUI Realtime Voice patches.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--patch", action="store_true", help="Apply realtime voice patch (default)")
    group.add_argument("--rollback", action="store_true", help="Rollback patch to original file")
    group.add_argument("--check", action="store_true", help="Check patch status and file integrity")
    args = parser.parse_args()

    if args.rollback:
        for f in TARGET_FILES:
            rollback_file(f)
    elif args.check:
        print("Checking patch status:")
        for f in TARGET_FILES:
            info = check_file(f)
            print(f"  {f}: patched={info.get('is_patched')}, backup={info.get('has_backup')}, valid={info.get('valid_bundle')}")
    else:
        for f in TARGET_FILES:
            patch_file(f)
