#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fréquence Nocturne — générateur d'épisode quotidien.

Pipeline :
  1. Génère le texte de l'épisode (Gemini API, clé dans GEMINI_API_KEY)
  2. Synthèse vocale (Google Cloud Text-to-Speech, clé dans GOOGLE_TTS_API_KEY)
  3. Mixage voix + musique d'ambiance (ffmpeg)
  4. Mise à jour du flux RSS lu par Spotify

Usage : python generate_episode.py
"""

import base64
import datetime as dt
import html
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(ROOT, "docs")
EPISODES_DIR = os.path.join(DOCS, "episodes")
EPISODES_JSON = os.path.join(DOCS, "episodes.json")
MUSIC = os.path.join(ROOT, "music", "ambiance.mp3")
GENERIQUE_INTRO = os.path.join(ROOT, "music", "generique_intro.mp3")
GENERIQUE_OUTRO = os.path.join(ROOT, "music", "generique_outro.mp3")

CONFIG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))

# Correspondance entre l'expression cron déclenchée (github.event.schedule)
# et le suffixe de fichier du créneau. Le créneau du matin n'a pas d'entrée
# ici : il garde le nom de fichier "brut" {stamp}.mp3 pour rester compatible
# avec les épisodes déjà publiés avant l'ajout du créneau du soir.
SCHEDULE_SLOTS = {
    "30 16 * * *": "soir",
}

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
- Le champ "script" est lu tel quel par une voix de synthèse : AUCUN
  astérisque, dièse, tiret de liste ou autre symbole de mise en forme
  Markdown dedans, uniquement du texte brut.

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


def clean_script(text):
    """Retire les résidus de mise en forme Markdown (astérisques, etc.) que
    Gemini ajoute parfois malgré la consigne — sans ça la voix les lit à
    voix haute ("astérisque")."""
    return re.sub(r"\*+", "", text)


# ---------------------------------------------------------------------------
# 2. Synthèse vocale (Google Cloud Text-to-Speech)
# ---------------------------------------------------------------------------

def to_ssml(text):
    """Ajoute de courtes pauses aux endroits où le texte marque déjà une
    hésitation (points de suspension, tirets d'incise) plutôt que partout."""
    escaped = html.escape(text, quote=False)
    escaped = escaped.replace("…", '…<break time="450ms"/>')
    escaped = escaped.replace(" — ", ' <break time="300ms"/>— ')
    return f"<speak>{escaped}</speak>"


def _ssml_bytes(text):
    return len(to_ssml(text).encode("utf-8"))


def chunk_text(text, max_bytes=4800):
    """Découpe le texte en morceaux dont la version SSML (après ajout des
    balises <break> par to_ssml) reste sous la limite de 5000 octets par
    requête de l'API Google TTS, sans couper au milieu d'une phrase. Un
    texte très dense en points de suspension/tirets peut voir sa taille
    largement augmenter une fois converti en SSML, d'où la mesure sur le
    texte transformé plutôt que sur le texte brut."""
    sentences = re.split(r"(?<=[.!?…])\s+", text.strip())
    chunks = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if _ssml_bytes(candidate) <= max_bytes:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if _ssml_bytes(sentence) <= max_bytes:
            current = sentence
        else:
            # Phrase seule déjà trop longue une fois convertie en SSML :
            # repli en dernier recours, découpage mot par mot.
            current = ""
            for word in sentence.split():
                # Un seul "mot" déjà trop long (cas irréaliste pour du texte
                # généré, mais on ferme la faille) : découpage caractère par
                # caractère.
                if _ssml_bytes(word) > max_bytes:
                    if current:
                        chunks.append(current)
                        current = ""
                    piece = ""
                    for ch in word:
                        if piece and _ssml_bytes(piece + ch) > max_bytes:
                            chunks.append(piece)
                            piece = ch
                        else:
                            piece += ch
                    current = piece
                    continue
                piece = f"{current} {word}".strip() if current else word
                if current and _ssml_bytes(piece) > max_bytes:
                    chunks.append(current)
                    current = word
                else:
                    current = piece
    if current:
        chunks.append(current)
    return chunks


def synthesize_chunk(text, api_key, out_path):
    voice_name = CONFIG.get("voice", "fr-FR-Neural2-G")
    audio_config = {
        "audioEncoding": "LINEAR16",
        "speakingRate": CONFIG.get("voice_rate", 0.92),
    }
    if "Studio" not in voice_name:
        # Les voix Studio de Google ne supportent pas le réglage de pitch
        # (ni via SSML ni via audioConfig) — on ne l'envoie que pour les
        # autres familles de voix (Neural2, Wavenet, etc.).
        audio_config["pitch"] = CONFIG.get("voice_pitch", -2.0)

    url = "https://texttospeech.googleapis.com/v1/text:synthesize?key=" + api_key
    body = json.dumps(
        {
            "input": {"ssml": to_ssml(text)},
            "voice": {
                "languageCode": CONFIG.get("language_code", "fr-FR"),
                "name": voice_name,
            },
            "audioConfig": audio_config,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(data["audioContent"]))


def synthesize(text, out_path):
    api_key = os.environ.get("GOOGLE_TTS_API_KEY")
    if not api_key:
        sys.exit("ERREUR : variable d'environnement GOOGLE_TTS_API_KEY absente.")

    tmp_dir = tempfile.mkdtemp(prefix="tts_")
    try:
        list_path = os.path.join(tmp_dir, "list.txt")
        with open(list_path, "w", encoding="utf-8") as list_file:
            for i, chunk in enumerate(chunk_text(text)):
                part_path = os.path.join(tmp_dir, f"part_{i:03d}.wav")
                synthesize_chunk(chunk, api_key, part_path)
                list_file.write(f"file '{part_path}'\n")
        subprocess.check_call(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", out_path,
            ]
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


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
    existing_today = [ep for ep in episodes if ep["file"].startswith(stamp)]
    existing_files_today = {ep["file"] for ep in existing_today}

    trigger = os.environ.get("TRIGGER_EVENT", "schedule")
    if trigger == "schedule":
        # Le créneau du matin garde le nom "brut" (compatibilité avec les
        # épisodes déjà publiés) ; les créneaux suivants ajoutent un suffixe.
        cron_slot = SCHEDULE_SLOTS.get(os.environ.get("CRON_SCHEDULE", ""))
        filename = f"{stamp}-{cron_slot}.mp3" if cron_slot else f"{stamp}.mp3"
        if filename in existing_files_today:
            print(f"Épisode du {stamp} ({cron_slot or 'matin'}) déjà généré — rien à faire.")
            return
    else:
        # Déclenchement manuel : toujours générer, en évitant toute collision
        # de nom avec un épisode déjà publié ce jour-là (matin, soir ou manuel).
        if f"{stamp}.mp3" not in existing_files_today:
            filename = f"{stamp}.mp3"
        else:
            n = 2
            while f"{stamp}-{n}.mp3" in existing_files_today:
                n += 1
            filename = f"{stamp}-{n}.mp3"
    slug = os.path.splitext(filename)[0]

    print("1/4  Génération du texte (Gemini)…")
    past_titles = [ep["title"] for ep in episodes]
    ep_data = call_gemini(build_prompt(past_titles))
    script = clean_script(ep_data["script"].strip())
    print(f"     Titre : {ep_data['title']}  ({len(script.split())} mots)")

    print("2/4  Synthèse vocale (Google Cloud TTS)…")
    voice_path = os.path.join(ROOT, "voice_tmp.mp3")
    synthesize(script, voice_path)

    print("3/4  Mixage avec la musique d'ambiance (ffmpeg)…")
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
            "guid": f"frequence-nocturne-{slug}",
        }
    )

    print("4/4  Mise à jour du flux RSS…")
    with open(EPISODES_JSON, "w", encoding="utf-8") as f:
        json.dump(episodes, f, ensure_ascii=False, indent=2)
    write_feed(episodes)
    print(f"Terminé : épisode #{num}, {hhmmss(duration)}, {filename}")


if __name__ == "__main__":
    main()
