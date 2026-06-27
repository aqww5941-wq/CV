import asyncio
import json
import random
import sys

try:
    from core.tts_texts import TTS_TEXTS, VOICE, VOICE_BY_MODEL
except ModuleNotFoundError:
    from tts_texts import TTS_TEXTS, VOICE, VOICE_BY_MODEL


def resolve_voice(voice_or_model: str | None = None) -> str:
    if not voice_or_model:
        return VOICE
    return VOICE_BY_MODEL.get(voice_or_model, voice_or_model)


async def _generate(text: str, output_path: str, voice: str | None = None) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, resolve_voice(voice))
    with open(output_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])


def pick_text(name: str, tts_type: str, variant: int | None = None) -> str:
    candidates = TTS_TEXTS.get(tts_type, ["{}"])
    if variant is None:
        template = random.choice(candidates)
    else:
        template = candidates[variant % len(candidates)]
    return template.format(name)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--print-manifest":
        print(json.dumps({key: len(value) for key, value in TTS_TEXTS.items()}, ensure_ascii=False))
        sys.exit(0)

    name = sys.argv[1]
    tts_type = sys.argv[2]
    output_path = sys.argv[3]
    variant = int(sys.argv[4]) if len(sys.argv) > 4 else None
    voice = sys.argv[5] if len(sys.argv) > 5 else None

    text = pick_text(name, tts_type, variant)
    if output_path == "--print-text":
        print(text)
        sys.exit(0)

    asyncio.run(_generate(text, output_path, voice))
