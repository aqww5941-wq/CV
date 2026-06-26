import asyncio
import sys
import os

VOICE = "zh-CN-XiaoxiaoNeural"

TEXTS = {
    "welcome": "{}，欢迎光临！",
    "goodbye": "{}，明天见！",
}


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

    template = TEXTS.get(tts_type, "{}")
    text = template.format(name)

    asyncio.run(_generate(text, output_path))
