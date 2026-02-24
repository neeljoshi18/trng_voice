import argparse
import numpy as np
import sounddevice as sd
import tempfile
import subprocess
from scipy.io import wavfile
from scipy.fftpack import fft, dct


def convert_to_pcm(infile):
    """Convert any audio file to PCM 16-bit WAV (44.1kHz mono) using ffmpeg."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp.close()
    cmd = [
        "ffmpeg", "-y", "-i", infile,
        "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1",
        tmp.name
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg conversion failed: {e.stderr.decode()}") from e
    return tmp.name


def load_wav(filename):
    """Load WAV file, auto-convert to PCM if necessary."""
    try:
        sr, data = wavfile.read(filename)
    except ValueError:
        # auto-convert if scipy can't parse it
        pcm_file = convert_to_pcm(filename)
        sr, data = wavfile.read(pcm_file)

    if data.ndim > 1:  # stereo → mono
        data = data.mean(axis=1)
    return sr, data.astype(np.float32)


def record_audio(duration=5, sr=44100):
    """Record live audio from microphone."""
    print(f"Recording {duration} seconds of audio...")
    audio = sd.rec(int(duration * sr), samplerate=sr, channels=1, dtype='float32')
    sd.wait()
    return sr, audio.flatten()


def extract_randomness(sr, data, num_codes=10000, length=12):
    """Generate random codes using FFT + cepstral features."""
    data = data - np.mean(data)

    # FFT magnitude spectrum
    spectrum = np.abs(fft(data))
    spectrum = spectrum[:len(spectrum)//2]  # keep half

    # Cepstrum (DCT of log spectrum)
    log_spec = np.log1p(spectrum)
    cepstrum = np.abs(dct(log_spec, norm='ortho'))

    # Mix spectrum and cepstrum
    features = np.concatenate([spectrum, cepstrum])
    norm = (features - np.min(features)) / (np.max(features) - np.min(features) + 1e-9)

    rng = np.random.default_rng(seed=np.sum(norm * 1e6).astype(int))

    codes = []
    for _ in range(num_codes):
        digits = [str(rng.integers(0, 10)) for _ in range(length)]
        codes.append("".join(digits))
    return codes


def save_codes(codes, outfile="random_codes.txt"):
    with open(outfile, "w") as f:
        for c in codes:
            f.write(c + "\n")
    print(f"Saved {len(codes)} codes to {outfile}")


def main():
    parser = argparse.ArgumentParser(description="Voice-based TRNG with FFT + cepstrum")
    parser.add_argument("--mode", choices=["mic", "file"], required=True, help="Entropy source")
    parser.add_argument("--infile", type=str, help="Path to WAV file (if mode=file)")
    parser.add_argument("--outfile", type=str, default="random_codes.txt", help="Output text file")
    parser.add_argument("--batch", type=int, default=10000, help="Number of codes to generate")
    parser.add_argument("--length", type=int, default=12, help="Digits per code")
    parser.add_argument("--duration", type=int, default=5, help="Recording duration (seconds) for mic mode")
    args = parser.parse_args()

    if args.mode == "mic":
        sr, data = record_audio(duration=args.duration)
    else:
        if not args.infile:
            raise ValueError("You must provide --infile for file mode")
        sr, data = load_wav(args.infile)

    codes = extract_randomness(sr, data, num_codes=args.batch, length=args.length)
    save_codes(codes, args.outfile)


if __name__ == "__main__":
    main()
