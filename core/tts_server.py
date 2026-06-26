import asyncio
import random
import sys

try:
    from core.tts_texts import TTS_TEXTS, VOICE
except ModuleNotFoundError:
    from tts_texts import TTS_TEXTS, VOICE


async def _generate(text: str, output_path: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, VOICE)
    with open(output_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])


if __name__ == "__main__":
    name = sys.argv[1]
    tts_type = sys.argv[2]
    output_path = sys.argv[3]
    variant = int(sys.argv[4]) if len(sys.argv) > 4 else None

    candidates = TTS_TEXTS.get(tts_type, ["{}"])
    if variant is None:
        template = random.choice(candidates)
    else:
        template = candidates[variant % len(candidates)]
    text = template.format(name)

    asyncio.run(_generate(text, output_path))
