#!/usr/bin/env python3
import argparse, json, wave, tempfile, subprocess, os, shutil
from pathlib import Path

def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found in PATH. Install ffmpeg and retry.")

def ensure_pcm_wav_preserve(infile):
    """
    If infile is a PCM WAV already, return (infile, params).
    Otherwise convert to PCM WAV but PRESERVE the input sample-rate and channel count.
    Returns (wav_path, wave_params)
    """
    # Try open as wav/PCM
    try:
        with wave.open(infile, 'rb') as w:
            params = w.getparams()
            # comptype == 'NONE' implies PCM in wave module
            if params.comptype == 'NONE':
                return infile, params
    except wave.Error:
        pass

    # Need ffmpeg to convert (preserve sample rate & channels by NOT specifying -ar or -ac)
    check_ffmpeg()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
    tmp.close()
    # convert to signed 16-bit little-endian PCM but KEEP original rate & channels
    cmd = ["ffmpeg", "-y", "-i", infile, "-acodec", "pcm_s16le", tmp.name]
    subprocess.run(cmd, check=True)
    with wave.open(tmp.name, 'rb') as w:
        params = w.getparams()
    return tmp.name, params

def wav2hex(infile, outfile):
    wav_path, params = ensure_pcm_wav_preserve(infile)
    try:
        with wave.open(wav_path, 'rb') as w:
            frames = w.readframes(w.getnframes())
            header = {
                "type": "wav_pcm",
                "nchannels": w.getnchannels(),
                "sampwidth": w.getsampwidth(),
                "framerate": w.getframerate(),
                "nframes": w.getnframes(),
                "orig_filename": os.path.basename(infile)
            }
        with open(outfile, 'w') as f:
            f.write(json.dumps(header) + "\n")
            f.write(frames.hex())
        print(f"Saved PCM frames + header to {outfile}")
    finally:
        if wav_path != infile:
            try:
                os.remove(wav_path)
            except Exception:
                pass

def hex2wav(infile, outfile):
    with open(infile, 'r') as f:
        header_line = f.readline().strip()
        hexstr = f.read().strip()
    header = json.loads(header_line)
    if header.get('type') != 'wav_pcm':
        raise RuntimeError("This hex file is not of type 'wav_pcm'. Use 'hex2file' if you encoded the whole file.")
    frames = bytes.fromhex(hexstr)
    with wave.open(outfile, 'wb') as w:
        w.setnchannels(header['nchannels'])
        w.setsampwidth(header['sampwidth'])
        w.setframerate(header['framerate'])
        w.writeframes(frames)
    print(f"Restored WAV written to {outfile} (channels={header['nchannels']}, "
          f"rate={header['framerate']}, sampwidth={header['sampwidth']})")

def file2hex(infile, outfile):
    # exact file bytes -> hex (bit perfect round-trip)
    with open(infile, 'rb') as f:
        data = f.read()
    header = {
        "type": "raw_file",
        "orig_filename": os.path.basename(infile),
        "size": len(data)
    }
    with open(outfile, 'w') as f:
        f.write(json.dumps(header) + "\n")
        f.write(data.hex())
    print(f"Saved raw file bytes to {outfile} (size={len(data)} bytes)")

def hex2file(infile, outfile=None):
    with open(infile, 'r') as f:
        header_line = f.readline().strip()
        hexstr = f.read().strip()
    header = json.loads(header_line)
    if header.get('type') != 'raw_file':
        raise RuntimeError("This hex file is not of type 'raw_file'. Use 'hex2wav' for wav_pcm type.")
    data = bytes.fromhex(hexstr)
    if outfile is None:
        outfile = header.get('orig_filename', 'restored.bin')
    with open(outfile, 'wb') as f:
        f.write(data)
    print(f"Restored original file bytes to {outfile} (expected size={header.get('size')})")

def rawhex2wav(infile, outfile, nchannels, sampwidth, framerate):
    # For older hex files that only have raw frames (no header) you can use this helper:
    with open(infile, 'r') as f:
        hexstr = f.read().strip()
    frames = bytes.fromhex(hexstr)
    with wave.open(outfile, 'wb') as w:
        w.setnchannels(int(nchannels))
        w.setsampwidth(int(sampwidth))
        w.setframerate(int(framerate))
        w.writeframes(frames)
    print(f"Restored WAV ({nchannels}ch, {framerate}Hz, sampwidth={sampwidth}) to {outfile}")

def main():
    p = argparse.ArgumentParser(description="File/WAV <-> Hex stream tool (safe restoration options)")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("file2hex"); a.add_argument("infile"); a.add_argument("outfile")
    b = sub.add_parser("hex2file"); b.add_argument("infile"); b.add_argument("outfile", nargs="?")
    c = sub.add_parser("wav2hex"); c.add_argument("infile"); c.add_argument("outfile")
    d = sub.add_parser("hex2wav"); d.add_argument("infile"); d.add_argument("outfile")
    e = sub.add_parser("rawhex2wav", help="Reconstruct raw-frame-only hex to WAV using provided params")
    e.add_argument("infile"); e.add_argument("outfile"); e.add_argument("--nchannels", required=True)
    e.add_argument("--sampwidth", required=True, help="bytes per sample (e.g. 2)"); e.add_argument("--framerate", required=True)

    args = p.parse_args()

    try:
        if args.cmd == "file2hex":
            file2hex(args.infile, args.outfile)
        elif args.cmd == "hex2file":
            hex2file(args.infile, args.outfile)
        elif args.cmd == "wav2hex":
            wav2hex(args.infile, args.outfile)
        elif args.cmd == "hex2wav":
            hex2wav(args.infile, args.outfile)
        elif args.cmd == "rawhex2wav":
            rawhex2wav(args.infile, args.outfile, args.nchannels, args.sampwidth, args.framerate)
    except subprocess.CalledProcessError as e:
        print("ffmpeg returned an error:", e)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    main()
