# Digital Human Models

All web-runnable Live2D models live in this directory.

## Epsilon

- Entry: `Epsilon/Epsilon.model3.json`
- Current default model.
- Expressions and motions are already wired into the current avatar page.

## chitose_ja

- Entry: `chitose_ja/runtime/chitose.model3.json`
- Useful motion: `Flick[0]` maps to `chitose_handwave.motion3.json`, suitable for waving.
- Includes expressions under `runtime/expressions`.

## haru_greeter_ja

- Entry: `haru_greeter_ja/runtime/haru_greeter_t05.model3.json`
- Receptionist-style model with many motions under `runtime/motion`.
- No expression list is declared in its `model3.json`.

## haru_ja

- Entry: `haru_ja/runtime/haru.model3.json`
- Includes expressions, motions, and bundled `runtime/sounds`.
- The bundled sounds should stay disabled unless intentionally replacing system TTS.

## natori_zh-Hans

- Entry: `natori_zh-Hans/runtime/natori_pro_t06.model3.json`
- Chinese package with rich expressions under `runtime/exp`.
- Uses a 4096 texture, so it may be heavier than the other models.
