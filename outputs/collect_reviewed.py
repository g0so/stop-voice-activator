#!/usr/bin/env python3
"""Eight-clip training pilot with playback and explicit review after every capture."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import wave
from collect_dataset import capture, audio_stats

BASE = Path(__file__).resolve().parent
PLAN = ['stop', 'shop', 'stop', 'start', 'stop', 'shit', 'stop', 'shop']


def playback(path):
    for name in ('paplay', 'aplay'):
        player = shutil.which(name)
        if player:
            try:
                result = subprocess.run([player, str(path)], capture_output=True, timeout=15)
                if result.returncode == 0:
                    return True
            except subprocess.TimeoutExpired:
                pass
    print('Automatic playback unavailable. Open this WAV in your audio player:', path)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', help='Omit to auto-detect one USB serial port')
    parser.add_argument('--split', choices=['train', 'validation', 'test'], default='train',
                        help='Keep training, tuning and final evaluation recordings separate')
    args = parser.parse_args()
    import serial
    from serial.tools import list_ports
    ports = [p.device for p in list_ports.comports() if p.device.startswith(('/dev/ttyUSB', '/dev/ttyACM'))]
    port = args.port
    if not port:
        if len(ports) != 1:
            parser.error(f'Specify --port. Available USB ports: {ports}')
        port = ports[0]
    session = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:8]
    folder = BASE / 'dataset/reviewed_restart' / args.split / 's01' / session
    folder.mkdir(parents=True, exist_ok=False)
    print(f'Fresh eight-clip {args.split} batch. Old recordings are preserved.')
    if args.split != 'train':
        print('These clips are reserved and must not be used for gradient training.')
    print('20–30 cm away; natural voice; normal fan. Say only the displayed word once.')
    print('After each capture, listen to playback, then explicitly accept or redo it.')
    print('Folder:', folder, flush=True)
    accepted = []
    try:
        with serial.Serial(port, 921600, timeout=1) as device:
            time.sleep(2)
            for index, word in enumerate(PLAN, 1):
                while True:
                    answer = input(f'\nClip {index}/8: say {word.upper()}. Enter to record, q to quit: ').strip().lower()
                    if answer == 'q':
                        return
                    audio = capture(device)
                    stats = audio_stats(audio)
                    wav = folder / f'{index:02d}_{word}_{uuid.uuid4().hex[:10]}.wav'
                    with wave.open(str(wav), 'wb') as w:
                        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(audio)
                    record = {'speaker': 's01', 'session': session, 'split': args.split,
                              'source': 'ESP32 INMP441', 'prompt_index': index, 'prompt': word,
                              'label': 'stop' if word == 'stop' else 'other_speech',
                              'wav': wav.name, 'accepted': False, 'review': 'pending',
                              'sample_rate': 16000, 'duration_seconds': 5,
                              'keyword_timing': 'unannotated; verify crop before training', **stats}
                    sidecar = wav.with_suffix('.json')
                    sidecar.write_text(json.dumps(record, indent=2) + '\n')
                    print(f'Saved: {wav}\nPeak={stats["peak"]}; clipped={stats["clipped_samples"]}')
                    if stats['clipped_samples'] or not stats['peak']:
                        print('Clipping or complete silence detected: redo this clip after adjusting the setup.')
                        record['review'] = 'quality check rejected'
                        sidecar.write_text(json.dumps(record, indent=2) + '\n')
                        continue
                    print('Playing your recording now. Stay silent during playback.', flush=True)
                    playback(wav)
                    while True:
                        answer = input(f'Did you hear exactly one clear "{word}"? y=accept, r=redo, p=replay, q=quit: ').strip().lower()
                        if answer == 'p':
                            playback(wav)
                        elif answer in ('y', 'r', 'q'):
                            break
                    if answer == 'q':
                        return
                    record['accepted'] = answer == 'y'
                    record['review'] = 'user confirmed clear word once' if answer == 'y' else 'user requested retake'
                    sidecar.write_text(json.dumps(record, indent=2) + '\n')
                    if answer == 'y':
                        accepted.append(wav.name)
                        break
        print('\nBatch complete. Tell me done; we will inspect these before the next step.')
    except (KeyboardInterrupt, EOFError):
        print('\nStopped; all recorded attempts are preserved.')
    finally:
        (folder / 'session_summary.json').write_text(json.dumps({
            'session': session, 'split': args.split, 'purpose': 'reviewed batch, not a complete dataset',
            'expected_clips': len(PLAN), 'accepted_clips': len(accepted), 'accepted_wavs': accepted,
        }, indent=2) + '\n')
        print('Accepted clips:', len(accepted), '| Folder:', folder)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit(f'Collection stopped: {exc}')
