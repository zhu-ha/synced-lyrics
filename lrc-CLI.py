#!/usr/bin/env python3

import os
import re
import sys
import time
import math
import signal
import subprocess
import shlex
from shutil import which

TIMESTAMP_RE = re.compile(r'\[(\d+):([0-5]?\d(?:\.\d+)?)\]')


def parse_lrc(lrc_path):
    entries = []
    try:
        with open(lrc_path, 'r', encoding='utf-8') as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                timestamps = TIMESTAMP_RE.findall(line)
                if not timestamps:
                    continue
                text = TIMESTAMP_RE.sub('', line).strip()
                if not text:
                    continue
                for m in timestamps:
                    minutes = int(m[0])
                    seconds = float(m[1])
                    total = minutes * 60 + seconds
                    entries.append((total, text))
    except FileNotFoundError:
        print(f"Error: .lrc file not found at: {lrc_path}")
        sys.exit(2)
    except Exception as e:
        print(f"Error reading .lrc file: {e}")
        sys.exit(2)

    entries.sort(key=lambda x: x[0])
    return entries


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def center_display(text):
    try:
        terminal_width, terminal_height = os.get_terminal_size()
    except OSError:
        terminal_width, terminal_height = 80, 24

    lines = text.splitlines()
    max_width = max((len(l) for l in lines), default=0)
    horizontal_padding = max((terminal_width - max_width) // 2, 0)
    vertical_padding = max((terminal_height - len(lines)) // 2, 0)

    print("\n" * vertical_padding, end="")
    for line in lines:
        print(" " * horizontal_padding + line)


def build_player_cmd(player, audio_path):
    player = (player or 'play').strip()
    # Build command lists for known players
    if player == 'ffplay':
        return ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', audio_path]
    elif player == 'mpv':
        return ['mpv', '--no-video', '--really-quiet', audio_path]
    elif player == 'afplay':
        return ['afplay', audio_path]
    elif player == 'cvlc':
        return ['cvlc', '--play-and-exit', '--no-video', audio_path]
    elif player == 'vlc':
        return ['vlc', '--intf', 'dummy', '--play-and-exit', '--no-video', audio_path]
    elif player == 'mplayer':
        return ['mplayer', '-really-quiet', '-nosound', audio_path] if False else ['mplayer', '-really-quiet', '-vo', 'null', audio_path]
    else:
        # default to sox 'play'
        return ['play', audio_path]


def detect_player(preferred=None):
    """
    Auto-detect an available player from a list of common players.
    preferred: optional list or tuple of player names in order to prefer.
    Returns the name of the first available player, or None if none found.
    """
    candidates = (
        (preferred if isinstance(preferred, (list, tuple)) else None)
        or ['mpv', 'ffplay', 'afplay', 'cvlc', 'vlc', 'mplayer', 'play']
    )

    for p in candidates:
        if which(p):
            return p
    return None


def play_audio(player_cmd):
    try:
        p = subprocess.Popen(player_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return p
    except FileNotFoundError:
        print(f"Error: audio player not found: {player_cmd[0]}")
        return None
    except Exception as e:
        print(f"Error launching audio player: {e}")
        return None


def display_loop(lyrics_entries):
    if not lyrics_entries:
        print("No lyrics to display.")
        return

    start_time = time.time()
    first_ts = lyrics_entries[0][0]

    while True:
        elapsed = time.time() - start_time
        remaining = first_ts - elapsed
        if remaining <= 0:
            break
        clear_screen()
        countdown_number = str(math.ceil(remaining))
        center_display(countdown_number)
        time.sleep(0.1)

    for timestamp, text in lyrics_entries:
        while True:
            elapsed = time.time() - start_time
            if elapsed >= timestamp:
                break
            time.sleep(0.05)
        clear_screen()
        center_display(text)

    time.sleep(0.5)


def prompt_file_path(prompt_msg):
    while True:
        raw = input(prompt_msg)
        if raw is None:
            raw = ''
        raw = raw.strip()
        if raw == '':
            print("Path cannot be empty. Please try again.")
            continue

        candidates = []

        candidates.append(raw)
        candidates.append(raw.strip('"').strip("'"))
        candidates.append(raw.replace('\\ ', ' '))

        try:
            tokens = shlex.split(raw)
        except Exception:
            tokens = []

        if tokens:
            candidates.append(' '.join(tokens))
            candidates.append(tokens[0])

        seen = set()
        filtered = []
        for c in candidates:
            if c is None:
                continue
            cc = c.strip()
            if cc == '':
                continue
            if cc not in seen:
                seen.add(cc)
                filtered.append(cc)

        found = False
        for candidate in filtered:
            p = candidate
            if (p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'")):
                p = p[1:-1]

            p = os.path.expanduser(os.path.expandvars(p))

            if p == '':
                continue

            if os.path.isfile(p):
                return p

        print(f"File not found. Tried these forms:")
        for c in filtered:
            print(f"  {c}")
        print("Please re-enter the path.")
        continue


def prompt_loop_count():
    while True:
        v = input("How many times to play? (default 1, enter 0 for infinite loop): ").strip()
        if v == '':
            return 1
        try:
            n = int(v)
            if n < 0:
                print("Please enter 0 for infinite or a positive integer.")
                continue
            if n == 0:
                return None
            return n
        except ValueError:
            print("Invalid number. Please enter an integer (e.g., 1, 2, 0).")


def sigint_handler_factory(current_proc_container):
    def handler(signum, frame):
        p = current_proc_container.get('proc')
        if p and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
        print("\nInterrupted. Exiting.")
        sys.exit(1)
    return handler


def main():
    print("synced-lyrics interactive\n")

    audio_path = prompt_file_path("Enter audio file path (drag file here or type path): ")
    lrc_path = prompt_file_path("Enter .lrc file path (drag file here or type path): ")

    lyrics = parse_lrc(lrc_path)
    loop_count = prompt_loop_count()

    # Auto-detect an available player instead of prompting the user
    player_choice = detect_player()
    if player_choice:
        print(f"Using audio player: {player_choice}")
    else:
        print("Warning: No known audio player detected in PATH. Will attempt to use 'play' (sox) and may fail.")
        player_choice = 'play'

    player_cmd_template = build_player_cmd(player_choice, audio_path)

    if which(player_cmd_template[0]) is None:
        print(f"Warning: player '{player_cmd_template[0]}' not found in PATH. The script will attempt to run it, but it may fail.")

    current_proc = {'proc': None}
    signal.signal(signal.SIGINT, sigint_handler_factory(current_proc))

    try:
        while True:
            player_cmd = build_player_cmd(player_choice, audio_path)

            audio_proc = play_audio(player_cmd)
            current_proc['proc'] = audio_proc

            display_loop(lyrics)

            if audio_proc and audio_proc.poll() is None:
                try:
                    audio_proc.wait()
                except KeyboardInterrupt:
                    signal.raise_signal(signal.SIGINT)

            current_proc['proc'] = None

            if loop_count is None:
                continue
            else:
                loop_count -= 1
                if loop_count <= 0:
                    break

    except KeyboardInterrupt:
        p = current_proc.get('proc')
        if p and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
        print("\nExiting.")
        sys.exit(1)


if __name__ == "__main__":
    main()
