"""Clean obsolete TTS cache files for the current Edge TTS voice settings."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CACHE_DIR, TTS_CACHE_DIR, TTS_VOICE_BY_MODEL
from core.tts_texts import TTS_TEXTS
from core.voice_system import EdgeTTSClient, TTSAudioCache, TTSRequest


def build_active_keys() -> set[str]:
    cache = TTSAudioCache()
    client = EdgeTTSClient()
    keys: set[str] = set()

    for voice in set(TTS_VOICE_BY_MODEL.values()):
        for event_type, templates in TTS_TEXTS.items():
            for template in templates:
                for name in ("访客", "{}"):
                    text = template.format(name)
                    request = TTSRequest(event_type=event_type, text=text, name=name, voice=voice)
                    keys.add(cache.key_for(request, client.build_cache_material(request)))

    return keys


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean obsolete TTS cache files.")
    parser.add_argument("--delete", action="store_true", help="delete files instead of dry-run")
    parser.add_argument(
        "--quarantine",
        action="store_true",
        help="move obsolete files to cache/tts_obsolete instead of deleting",
    )
    args = parser.parse_args()

    tts_dir = Path(TTS_CACHE_DIR)
    if not tts_dir.exists():
        print(f"TTS cache directory not found: {tts_dir}")
        return 0

    active_keys = build_active_keys()
    obsolete_files = [
        path
        for path in tts_dir.glob("*.mp3")
        if path.stem not in active_keys
    ]
    legacy_files = list(Path(CACHE_DIR).glob("tts_*.mp3"))

    print(f"active key count: {len(active_keys)}")
    print(f"obsolete hashed files: {len(obsolete_files)}")
    print(f"legacy root tts files: {len(legacy_files)}")

    if not args.delete and not args.quarantine:
        for path in obsolete_files[:20]:
            print(f"obsolete: {path}")
        for path in legacy_files:
            print(f"legacy:   {path}")
        print("dry-run only. Use --quarantine or --delete to clean.")
        return 0

    if args.quarantine:
        target_dir = Path(CACHE_DIR) / "tts_obsolete"
        target_dir.mkdir(parents=True, exist_ok=True)
        for path in obsolete_files + legacy_files:
            shutil.move(str(path), str(target_dir / path.name))
        print(f"moved {len(obsolete_files) + len(legacy_files)} files to {target_dir}")
        return 0

    for path in obsolete_files + legacy_files:
        path.unlink(missing_ok=True)
    print(f"deleted {len(obsolete_files) + len(legacy_files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

