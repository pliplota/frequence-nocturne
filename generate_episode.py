#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fréquence Nocturne — générateur d'épisode quotidien.

Pipeline :
  1. Génère le texte de l'épisode (Gemini API, clé dans GEMINI_API_KEY)
  2. Synthèse vocale gratuite (Edge TTS, voix fr-FR-HenriNeural)
  3. Mixage voix + musique d'ambiance (ffmpeg)
  4. Mise à jour du flux RSS lu par Spotify

Usage : python generate_episode.py
"""

import asyncio
import datetime as dt
import html
import json
import os
import random
import re
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(ROOT, "docs")
EPISODES_DIR = os.path.join(DOCS, "episodes")
EPISODES_JSON = os.path.join(DOCS, "episodes.json")
MUSIC = os.path.join(ROOT, "music", "ambiance.mp3")
GENERIQUE_INTRO = os.path.join(ROOT, "music", "generique_intro.mp3")
GENERIQUE_OUTRO = os.path.join(ROOT, "music", "generique_outro.mp3")

CONFIG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))

# ---------------------------------------------------------------------------
# 1. Génération du texte de l'épisode
# ---------------------------------------------------------------------------

THEMES = [
    "une présence ressentie dans une maison ordinaire",
    "un phénomène lumineux inexpliqué observé de nuit",
    "des bruits récurrents sans source identifiable",
    "une silhouette entrevue puis disparue",
    "un objet déplacé sans explication",
    "une coïncidence troublante liée à un proche décédé",
    "une expérience étrange sur une route de nuit",
    "un rêve prémonitoire vérifié le lendemain",
    "une sensation d'être observé dans un lieu isolé",
    "un appareil électronique au comportement inexplicable",
    "une voix entendue alors que la personne était seule",
    "un animal réagissant à quelque chose d'invisible",
    "une odeur inexpliquée associée à un souvenir",
    "un lieu de travail la nuit (usine, entrepôt, hôpital, gare)",
    "une expérience vécue pendant l'enfance et jamais oubliée",
    "une horloge, montre ou heure récurrente troublante",
    "une photo sur laquelle apparaît un détail inexpliqué",
    "un phénomène vécu simultanément par deux personnes",
]


NUM_WORDS = {1: "un", 2: "deux", 3: "trois", 4: "quatre", 5: "cinq"}


def build_prompt(past_titles):
    n = CONFIG.get("num_testimonies", 2)
    themes = random.sample(THEMES, n)
    avoid = "\n".join(f"- {t}" for t in past_titles[-12:]) or "(aucun)"

    structure = [
        f'1. INTRO : le présentateur dit exactement cette phrase rituelle :\n'
        f'   "{CONFIG["intro_ritual"]}"\n'
        f'   puis il se présente ("Bonsoir, ici {CONFIG["presenter_name"]}…"), annonce brièvement '
        f'les {NUM_WORDS.get(n, n)} témoignages du soir (sans divulgâcher), de façon variée à chaque épisode.'
    ]
    step = 2
    for i, theme in enumerate(themes, start=1):
        structure.append(f"{step}. TÉMOIGNAGE {i} : thème imposé : {theme}. Environ 550-700 mots.")
        step += 1
        if i < n:
            structure.append(f"{step}. Transition + commentaire sobre du présentateur.")
        else:
            structure.append(f"{step}. Bref commentaire.")
        step += 1
    structure.append(
        f'{step}. OUTRO : le présentateur conclut avec exactement ce texte rituel :\n'
        f'   "{CONFIG["outro_ritual"]}"'
    )
    structure_text = "\n".join(structure)

    return f"""Tu écris le script d'un épisode du podcast français "{CONFIG['show_name']}".

CONCEPT : {CONFIG['presenter_name']}, la cinquantaine, ancien journaliste de nuit, voix grave et posée,
lit à l'antenne les témoignages paranormaux que des auditeurs lui envoient par mail.
Ton : radio de nuit, calme, sobre, jamais sensationnaliste. Il ne tranche jamais :
il lit, il laisse le doute exister.

RÈGLES D'ÉCRITURE (très important) :
- Les témoignages doivent sembler RÉELS et CRÉDIBLES. Pas de fantômes qui parlent,
  pas de monstres, pas de scénario de film. Des choses banales et troublantes.
- Détails concrets : une heure précise, un lieu plausible en France (ville moyenne,
  campagne, périphérie), un contexte ordinaire (travail, insomnie, trajet).
- Le témoin doute de lui-même ("je ne sais toujours pas ce que j'ai vu",
  "il y a sûrement une explication, mais…").
- AUCUNE résolution. L'histoire reste ouverte.
- Chaque témoignage est signé d'un prénom + initiale + département
  (ex : "Nathalie R., dans l'Ain"). Prénoms français courants variés.
- Style oral : phrases courtes, respirations, langage parlé naturel.
- Le présentateur fait une courte transition entre chaque témoignage,
  et un très bref commentaire sobre après chacun (2-3 phrases max).

STRUCTURE DE L'ÉPISODE :
{structure_text}

Titres d'épisodes déjà utilisés (NE PAS répéter les mêmes situations) :
{avoid}

RÉPONDS UNIQUEMENT avec un objet JSON valide, sans balises markdown, au format :
{{
  "title": "titre court et intrigant de l'épisode (sans numéro)",
  "description": "description de l'épisode en 2 phrases pour Spotify",
  "script": "le texte INTÉGRAL de l'épisode, prêt à être lu à voix haute, sans didascalies, sans indications entre crochets, sans noms de sections"
}}"""


def call_gemini(prompt):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("ERREUR : variable d'environnement GEMINI_API_KEY absente.")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent?key=" + api_key
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 1.0, "maxOutputTokens": 8192},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])


# ---------------------------------------------------------------------------
# 2. Synthèse vocale (Edge TTS — gratuit)
# ---------------------------------------------------------------------------

async def synthesize(text, out_path):
    import edge_tts

    communicate = edge_tts.Communicate(
        text,
        voice=CONFIG["voice"],
        rate=CONFIG.get("voice_rate", "-8%"),
        pitch=CONFIG.get("voice_pitch", "-4Hz"),
    )
    await communicate.save(out_path)


# ---------------------------------------------------------------------------
# 3. Mixage ffmpeg : musique d'ambiance en fond + fondu d'entrée/sortie
# ---------------------------------------------------------------------------

def probe_duration(path):
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ]
    )
    return float(out.strip())


def mix(voice_path, out_path):
    have_music = os.path.isfile(MUSIC)
    if not have_music:
        print("AVERTISSEMENT : music/ambiance.mp3 introuvable — épisode publié sans musique de fond.")
    have_intro = os.path.isfile(GENERIQUE_INTRO)
    have_outro = os.path.isfile(GENERIQUE_OUTRO)

    voice_dur = probe_duration(voice_path)
    lead_in = 5.0          # musique seule avant la voix
    tail = 6.0             # musique seule après la voix
    total = lead_in + voice_dur + tail
    vol = CONFIG.get("music_volume", 0.16)

    cmd = ["ffmpeg", "-y", "-i", voice_path]
    idx = 1  # 0 = voix
    if have_music:
        cmd += ["-stream_loop", "-1", "-i", MUSIC]
        music_idx, idx = idx, idx + 1
    if have_intro:
        cmd += ["-i", GENERIQUE_INTRO]
        intro_idx, idx = idx, idx + 1
    if have_outro:
        cmd += ["-i", GENERIQUE_OUTRO]
        outro_idx, idx = idx, idx + 1

    filters = []
    if have_music:
        filters.append(f"[0:a]adelay={int(lead_in*1000)}|{int(lead_in*1000)},apad=pad_dur={tail}[v]")
        filters.append(f"[{music_idx}:a]volume={vol}[m]")
        filters.append("[v][m]amix=inputs=2:duration=first:dropout_transition=4[bedraw]")
    else:
        filters.append(f"[0:a]adelay={int(lead_in*1000)}|{int(lead_in*1000)},apad=pad_dur={tail}[bedraw]")
    filters.append(
        f"[bedraw]afade=t=in:st=0:d=2,afade=t=out:st={total-5:.2f}:d=5,"
        f"aformat=sample_rates=44100:channel_layouts=stereo[bed]"
    )

    parts = []
    if have_intro:
        filters.append(f"[{intro_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo[gi]")
        parts.append("[gi]")
    parts.append("[bed]")
    if have_outro:
        filters.append(f"[{outro_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo[go]")
        parts.append("[go]")

    if len(parts) > 1:
        filters.append("".join(parts) + f"concat=n={len(parts)}:v=0:a=1[out]")
        final = "[out]"
    else:
        final = "[bed]"

    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", final,
        "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100",
        out_path,
    ]
    subprocess.check_call(cmd)


# ---------------------------------------------------------------------------
# 4. Flux RSS
# ---------------------------------------------------------------------------

def esc(s):
    return html.escape(s, quote=True)


def rfc2822(date):
    return date.strftime("%a, %d %b %Y %H:%M:%S +0000")


def write_feed(episodes):
    cfg = CONFIG
    base = cfg["base_url"].rstrip("/")
    items = []
    for ep in episodes[-cfg.get("keep_last_episodes_in_feed", 100):][::-1]:
        pub = dt.datetime.fromisoformat(ep["date"])
        items.append(f"""    <item>
      <title>{esc(ep['title'])}</title>
      <description>{esc(ep['description'])}</description>
      <pubDate>{rfc2822(pub)}</pubDate>
      <guid isPermaLink="false">{esc(ep['guid'])}</guid>
      <enclosure url="{base}/episodes/{ep['file']}" length="{ep['bytes']}" type="audio/mpeg"/>
      <itunes:duration>{ep['duration']}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
      <itunes:episodeType>full</itunes:episodeType>
    </item>""")
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{esc(cfg['show_name'])}</title>
    <description>{esc(cfg['show_description'])}</description>
    <link>{base}/</link>
    <language>{cfg['language']}</language>
    <atom:link href="{base}/feed.xml" rel="self" type="application/rss+xml"/>
    <itunes:author>{esc(cfg['author'])}</itunes:author>
    <itunes:owner>
      <itunes:name>{esc(cfg['author'])}</itunes:name>
      <itunes:email>{esc(cfg['contact_email'])}</itunes:email>
    </itunes:owner>
    <itunes:image href="{base}/cover.jpg"/>
    <itunes:category text="{esc(cfg['category'])}"/>
    <itunes:explicit>false</itunes:explicit>
{chr(10).join(items)}
  </channel>
</rss>
"""
    with open(os.path.join(DOCS, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(feed)


def hhmmss(seconds):
    s = int(round(seconds))
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(EPISODES_DIR, exist_ok=True)
    episodes = []
    if os.path.isfile(EPISODES_JSON):
        episodes = json.load(open(EPISODES_JSON, encoding="utf-8"))

    today = dt.datetime.now(dt.timezone.utc)
    stamp = today.strftime("%Y-%m-%d")
    if any(ep["file"].startswith(stamp) for ep in episodes):
        print(f"Épisode du {stamp} déjà généré — rien à faire.")
        return

    print("1/4  Génération du texte (Gemini)…")
    past_titles = [ep["title"] for ep in episodes]
    ep_data = call_gemini(build_prompt(past_titles))
    script = ep_data["script"].strip()
    print(f"     Titre : {ep_data['title']}  ({len(script.split())} mots)")

    print("2/4  Synthèse vocale (Edge TTS)…")
    voice_path = os.path.join(ROOT, "voice_tmp.mp3")
    asyncio.run(synthesize(script, voice_path))

    print("3/4  Mixage avec la musique d'ambiance (ffmpeg)…")
    filename = f"{stamp}.mp3"
    out_path = os.path.join(EPISODES_DIR, filename)
    mix(voice_path, out_path)
    os.remove(voice_path)

    duration = probe_duration(out_path)
    num = len(episodes) + 1
    episodes.append(
        {
            "title": f"#{num} — {ep_data['title']}",
            "description": ep_data["description"],
            "date": today.isoformat(),
            "file": filename,
            "bytes": os.path.getsize(out_path),
            "duration": hhmmss(duration),
            "guid": f"frequence-nocturne-{stamp}",
        }
    )

    print("4/4  Mise à jour du flux RSS…")
    with open(EPISODES_JSON, "w", encoding="utf-8") as f:
        json.dump(episodes, f, ensure_ascii=False, indent=2)
    write_feed(episodes)
    print(f"Terminé : épisode #{num}, {hhmmss(duration)}, {filename}")


if __name__ == "__main__":
    main()
