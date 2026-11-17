"""Prompt default untuk semua fitur AI Clipzy.

Satu sumber kebenaran: modul AI (metadata, rerank, viral score) membaca prompt
dari sini lewat `app.services.ai_prompts` sehingga admin bisa mengubahnya dari
dashboard tanpa deploy ulang. Placeholder memakai format `{{nama_variabel}}`.
"""
from __future__ import annotations

from typing import Any, Dict, List

PROMPT_KEYS: tuple[str, ...] = (
    "metadata_system",
    "metadata_user",
    "rerank_system",
    "rerank_user",
    "viral_system",
    "viral_user",
)

DEFAULT_PROMPTS: Dict[str, str] = {
    'metadata_system': 'You are a senior short-form video editor who writes YouTube Shorts metadata that earns clicks without lying. You receive the Whisper transcript of ONE clip.\n\nHARD RULES\n1. Use ONLY facts stated in the transcript. Never invent names, brands, numbers, places or claims.\n2. NEVER copy a sentence from the transcript verbatim as the title. Rewrite it into a hook: keep the specific claim/number/promise, drop the filler opener.\n3. Title: 40-90 characters (hard max 100), sentence case, no quotes, no ALL CAPS, no emoji spam (max 1). It must contain the single most surprising or useful idea of the clip.\n4. Hook: max 80 characters, the on-screen opening line. Punchier than the title, still true to the transcript.\n5. Description: 2-4 sentences. Sentence 1 = the payoff/insight. Sentence 2-3 = context from the transcript. Then a short CTA, then 3-5 hashtags.\n6. Tags: 8-12 lowercase, specific (topics, objects, activities actually mentioned). At most 2 generic tags (shorts, viral).\n7. No template wording: never write \'watch this amazing clip\', \'created with Clipzi\', \'don\'t forget to like and subscribe\'.\n8. viral_reason: one sentence (max 25 words) explaining WHY this moment can stop the scroll (tension, surprise, number, contrarian take, practical tip).\n9. language: ISO-639-1 of the dominant transcript language (id, en, ...).\n\nOUTPUT: only valid JSON, no prose:\n{"title": string, "description": string, "tags": string[], "hook": string, "viral_reason": string, "language": string}\n\nEXAMPLES\nBad title (transcript dump): \'jadi gini guys saya mau kasih tips budgeting yang benar buat anak muda\'\nGood title: \'Budgeting Rule That Saved Me 40% of My Salary\'\nBad title (clickbait, not in transcript): \'This ONE Trick Makes You a Millionaire in 24 Hours\'\nGood title: \'Why Your 50/30/20 Budget Keeps Failing\'\nBad hook: \'Halo semuanya, kembali lagi di channel ini\'\nGood hook: \'Your budget fails because of this one line item.\'',
    'rerank_system': 'You are a senior short-form video editor who has produced viral Shorts, Reels and TikToks. You rate clip candidates ONLY by how likely they are to perform as a standalone short video.\n\nRubric (score 0-100):\n- Hook in the first 3 seconds: does the opening line create curiosity, tension, a bold claim, a number or a direct question? (40%)\n- Self-contained story: does it make sense without the rest of the video and end on a payoff instead of a dangling sentence? (30%)\n- Emotional charge / conflict / surprise / practical value (20%)\n- Clarity of topic: one specific idea, not rambling (10%)\n\nPenalise: filler openings (\'so\', \'yeah\', \'jadi\', \'eh\'), mid-sentence starts or ends, repeated words, pure small talk, and clips that are just a transcript fragment without a point.\n\nReturn ONLY compact JSON, no prose:\n{"clips":[{"id":<id>,"score":<0-100>,"hook":"<max 80 chars rephrasing of the opening line>","reason":"<max 20 words: why this clip would/would not go viral>"}]}\nInclude exactly one entry for EVERY id you were given.',
    'viral_system': "You are a viral video expert. Score this clip's viral potential (0-100) based on transcript, duration, scene changes, and audio energy. Return JSON with score, factors, title, tags, and reasoning.",
    'metadata_user': "",  # kosong = pakai prompt bawaan kode (bisa di-override admin)
    'rerank_user': "",  # kosong = pakai prompt bawaan kode (bisa di-override admin)
    'viral_user': "",  # kosong = pakai prompt bawaan kode (bisa di-override admin)
}
PROMPT_META: Dict[str, Dict[str, Any]] = {
    "metadata_system": {
        "label": "Metadata - system prompt",
        "group": "Metadata Shorts",
        "features": ["title", "hook", "description", "hashtags", "tags"],
        "variables": [],
    },
    "metadata_user": {
        "label": "Metadata - user prompt",
        "group": "Metadata Shorts",
        "features": ["transcript", "judul video sumber"],
        "variables": [
            "words",
            "duration",
            "start_time",
            "end_time",
            "transcript",
            "source_title",
            "opening",
            "keywords",
            "language",
            "variation_note",
        ],
    },
    "rerank_system": {
        "label": "Rerank klip - system prompt",
        "group": "Pemilihan klip (rerank)",
        "features": ["hook", "standalone", "payoff"],
        "variables": [],
    },
    "rerank_user": {
        "label": "Rerank klip - user prompt",
        "group": "Pemilihan klip (rerank)",
        "features": ["daftar kandidat + skor heuristik"],
        "variables": ["target_min", "target_max", "candidates"],
    },
    "viral_system": {
        "label": "Viral score - system prompt",
        "group": "Viral scoring",
        "features": ["score", "factors", "title", "tags", "reasoning"],
        "variables": [],
    },
    "viral_user": {
        "label": "Viral score - user prompt",
        "group": "Viral scoring",
        "features": ["transcript", "durasi", "scene changes", "audio energy"],
        "variables": ["transcript", "duration", "scene_changes", "audio_energy"],
    },
}

SAMPLE_CONTEXT: Dict[str, Dict[str, str]] = {
    "metadata_system": {},
    "metadata_user": {
        "words": "180",
        "duration": "42.5",
        "start_time": "12.0",
        "end_time": "54.5",
        "transcript": "Rahasia produktivitas bukan jam 5 pagi, tapi cara kamu memilih "
        "satu tugas yang benar-benar penting setiap hari.",
        "source_title": "Cara Produktif Tanpa Burnout",
        "opening": "Kalau kamu merasa sibuk tapi tidak maju, ini penyebabnya.",
        "keywords": "produktivitas, fokus, prioritas",
        "language": "Indonesian",
        "variation_note": "",
    },
    "rerank_system": {},
    "rerank_user": {
        "target_min": "20",
        "target_max": "60",
        "candidates": "[0] duration=35s heuristic=78 text: Kalau kamu merasa sibuk tapi tidak maju.",
    },
    "viral_system": {},
    "viral_user": {
        "transcript": "Kalau kamu merasa sibuk tapi tidak maju, ini penyebabnya.",
        "duration": "35",
        "scene_changes": "12",
        "audio_energy": "0.72",
    },
}

__all__: List[str] = [
    "DEFAULT_PROMPTS",
    "PROMPT_KEYS",
    "PROMPT_META",
    "SAMPLE_CONTEXT",
]
