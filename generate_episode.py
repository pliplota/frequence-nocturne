#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fréquence Nocturne — générateur d'épisode quotidien.

Pipeline :
  1. Génère le texte de l'épisode (Gemini API, clé dans GEMINI_API_KEY)
  2. Synthèse vocale (Gemini TTS, même clé GEMINI_API_KEY)
  3. Mixage voix + musique d'ambiance (ffmpeg)
  4. Mise à jour du flux RSS lu par Spotify

Usage : python generate_episode.py
"""

import base64
import datetime as dt
import html
import http.client
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave

# Erreurs réseau/connexion (pas une vraie réponse HTTP d'erreur : timeout,
# DNS, connexion coupée par le serveur avant d'avoir répondu...) — toujours
# transitoires par nature, toujours à réessayer plutôt qu'à traiter comme
# fatales.
NETWORK_ERRORS = (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError)

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


def _request_gemini_text(prompt, api_key):
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent?key=" + api_key
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 1.0,
                "maxOutputTokens": 16384,
                # Pas besoin de raisonnement invisible pour de l'écriture
                # créative — désactivé pour laisser tout le budget de tokens
                # au texte visible (une réponse tronquée par MAX_TOKENS
                # produit un JSON invalide en plein milieu d'une chaîne).
                "thinkingConfig": {"thinkingBudget": 0},
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "title": {"type": "STRING"},
                        "description": {"type": "STRING"},
                        "script": {"type": "STRING"},
                    },
                    "required": ["title", "description", "script"],
                },
            },
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        # Ce même genre d'erreur transitoire (429/503...) qui frappait la
        # partie TTS peut tout aussi bien arriver ici — call_gemini() n'avait
        # jusqu'ici aucune gestion d'erreur du tout et plantait immédiatement.
        body_text = e.read().decode("utf-8", errors="replace")
        if e.code == 429 and "per_day" in body_text:
            sys.exit(
                "ERREUR : quota quotidien Gemini (texte) épuisé — réessaie "
                "plus tard :\n" + body_text[:1500]
            )
        if e.code in RETRYABLE_HTTP_CODES:
            raise RetryableError(f"HTTP {e.code} : {body_text[:500]}")
        sys.exit(f"ERREUR HTTP {e.code} de l'API Gemini (texte) :\n" + body_text[:2000])
    except NETWORK_ERRORS as e:
        raise RetryableError(f"{type(e).__name__} : {e}")

    candidate = data["candidates"][0]
    if candidate.get("finishReason") == "MAX_TOKENS":
        sys.exit(
            "ERREUR : réponse Gemini tronquée (maxOutputTokens atteint) — "
            "augmente maxOutputTokens dans _request_gemini_text()."
        )
    text = candidate["content"]["parts"][0]["text"]
    return json.loads(text)


def call_gemini(prompt):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("ERREUR : variable d'environnement GEMINI_API_KEY absente.")
    return _with_retries(lambda: _request_gemini_text(prompt, api_key), "Gemini (texte)")


def clean_script(text):
    """Retire les résidus de mise en forme Markdown (astérisques, etc.) que
    Gemini ajoute parfois malgré la consigne — sans ça la voix les lit à
    voix haute ("astérisque")."""
    return re.sub(r"\*+", "", text)


# ---------------------------------------------------------------------------
# 2. Synthèse vocale (Gemini TTS — voix native, contrôlée par prompt)
# ---------------------------------------------------------------------------

def chunk_text(text, max_chars=1500):
    """Découpe le texte en morceaux, sans couper au milieu d'une phrase.
    gemini-3.1-flash-tts-preview a un quota très restreint (10 req/min,
    100 req/jour au moment où c'est écrit) — la génération phrase par
    phrase (~240 requêtes/épisode) l'épuise en un seul épisode. Ce
    réglage vise ~8-10 morceaux par épisode complet, un compromis entre
    limiter la dérive de ton et rester dans un budget de requêtes
    soutenable pour deux créneaux quotidiens + des tests manuels. Même
    logique côté coût pour un fournisseur payant comme OpenAI : moins de
    requêtes, moins de risque de reproduire une explosion du nombre
    d'appels (voir MAX_TTS_CHUNKS plus bas)."""
    sentences = re.split(r"(?<=[.!?…])\s+", text.strip())
    chunks = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _pcm_to_wav_bytes(pcm_bytes, sample_rate=24000, channels=1, sample_width=2):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


class RetryableError(Exception):
    """Échec probablement transitoire (finishReason != STOP avec contenu
    vide, ou erreur HTTP temporaire côté serveur) — vaut le coup de
    réessayer avant d'abandonner."""


RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


def _with_retries(request_fn, label, max_attempts=5):
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return request_fn()
        except RetryableError as e:
            last_error = e
            if attempt < max_attempts:
                wait = 10 * attempt  # 10s, 20s, 30s...
                print(f"     (tentative {attempt}/{max_attempts} échouée : {e} — nouvel essai dans {wait}s)")
                time.sleep(wait)
    sys.exit(f"ERREUR : {label} a échoué {max_attempts} fois de suite : {last_error}")


def _request_tts_gemini(text, api_key):
    style = CONFIG.get(
        "tts_style_prompt",
        "Lis ce texte à voix haute d'un ton calme, posé et mesuré, comme un "
        "présentateur de radio de nuit, avec de courtes pauses naturelles "
        "aux points de suspension et aux tirets d'incise :",
    )
    model = CONFIG.get("tts_model", "gemini-2.5-flash-preview-tts")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": f"{style} {text}"}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                # Basse température = moins de dérive créative loin de la
                # consigne de style (jamais essayé jusqu'ici — la voix
                # dérivait vers le chuchotement malgré plusieurs formulations
                # de prompt différentes).
                "temperature": CONFIG.get("tts_temperature", 0.3),
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": CONFIG.get("voice", "Charon")
                        }
                    }
                },
            },
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        # Affiche le corps de la réponse d'erreur (urllib ne le montre pas
        # par défaut) pour diagnostiquer directement au lieu de deviner à
        # l'aveugle depuis une simple capture d'écran.
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 429 and "per_day" in body:
            # Quota QUOTIDIEN épuisé (pas juste la limite par minute) :
            # le message donne un délai de réessai en heures, ça ne sert
            # à rien d'insister dans ce run.
            sys.exit(
                "ERREUR : quota quotidien Gemini TTS épuisé — réessaie plus "
                "tard (le message d'erreur indique dans combien de temps) :\n"
                + body[:1500]
            )
        if e.code in RETRYABLE_HTTP_CODES:
            # Erreur serveur temporaire (surcharge, rate limit...) : vaut
            # le coup de réessayer plutôt qu'abandonner direct.
            raise RetryableError(f"HTTP {e.code} : {body[:500]}")
        sys.exit(f"ERREUR HTTP {e.code} de l'API Gemini TTS :\n" + body[:2000])
    except NETWORK_ERRORS as e:
        raise RetryableError(f"{type(e).__name__} : {e}")

    candidate = (data.get("candidates") or [{}])[0]
    finish_reason = candidate.get("finishReason")
    try:
        part = candidate["content"]["parts"][0]["inlineData"]
        audio_b64 = part["data"]
        mime_type = part.get("mimeType", "")
    except (KeyError, IndexError, TypeError):
        if finish_reason and finish_reason != "STOP":
            # Glitch connu du modèle preview sur les générations longues :
            # candidatesTokenCount non nul mais content vide, finishReason
            # "OTHER" — transitoire dans les cas observés, vaut le coup
            # de réessayer plutôt que d'abandonner direct.
            raise RetryableError(
                f"finishReason={finish_reason}, content vide : "
                + json.dumps(data, ensure_ascii=False)[:500]
            )
        sys.exit(
            "ERREUR : réponse Gemini TTS inattendue, structure reçue :\n"
            + json.dumps(data, ensure_ascii=False)[:2000]
        )
    return audio_b64, mime_type


def synthesize_chunk_gemini(text, api_key, out_path):
    audio_b64, mime_type = _with_retries(
        lambda: _request_tts_gemini(text, api_key), "Gemini TTS"
    )
    raw = base64.b64decode(audio_b64)
    if not raw.startswith(b"RIFF"):
        rate_match = re.search(r"rate=(\d+)", mime_type)
        sample_rate = int(rate_match.group(1)) if rate_match else 24000
        raw = _pcm_to_wav_bytes(raw, sample_rate=sample_rate)
    with open(out_path, "wb") as f:
        f.write(raw)


def _request_tts_elevenlabs(text, api_key):
    voice_id = CONFIG.get("elevenlabs_voice_id", "pNInz6obpgDQGcFmaJgB")
    model_id = CONFIG.get("elevenlabs_model", "eleven_multilingual_v2")
    voice_settings = CONFIG.get(
        "elevenlabs_voice_settings",
        {"stability": 0.6, "similarity_boost": 0.75, "speed": 0.92},
    )
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    body = json.dumps(
        {"text": text, "model_id": model_id, "voice_settings": voice_settings}
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "xi-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        if e.code in RETRYABLE_HTTP_CODES:
            raise RetryableError(f"HTTP {e.code} : {body_text[:500]}")
        sys.exit(f"ERREUR HTTP {e.code} de l'API ElevenLabs :\n" + body_text[:2000])
    except NETWORK_ERRORS as e:
        raise RetryableError(f"{type(e).__name__} : {e}")


def synthesize_chunk_elevenlabs(text, api_key, out_path):
    audio_bytes = _with_retries(
        lambda: _request_tts_elevenlabs(text, api_key), "ElevenLabs"
    )
    with open(out_path, "wb") as f:
        f.write(audio_bytes)


def _request_tts_openai(text, api_key):
    model = CONFIG.get("openai_tts_model", "gpt-4o-mini-tts")
    voice = CONFIG.get("openai_voice", "onyx")
    instructions = CONFIG.get(
        "openai_voice_instructions",
        "Voix grave et posée de présentateur radio de nuit. Volume et débit "
        "constants du début à la fin, jamais de chuchotement ni de baisse "
        "de volume, même sur les passages les plus intimistes.",
    )
    url = "https://api.openai.com/v1/audio/speech"
    payload = {"model": model, "voice": voice, "input": text, "response_format": "mp3"}
    # tts-1 / tts-1-hd ne comprennent pas "instructions" (spécifique à
    # gpt-4o-mini-tts) — ne l'envoyer que pour ce modèle.
    if model == "gpt-4o-mini-tts" and instructions:
        payload["instructions"] = instructions
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        if e.code in RETRYABLE_HTTP_CODES:
            raise RetryableError(f"HTTP {e.code} : {body_text[:500]}")
        sys.exit(f"ERREUR HTTP {e.code} de l'API OpenAI TTS :\n" + body_text[:2000])
    except NETWORK_ERRORS as e:
        raise RetryableError(f"{type(e).__name__} : {e}")


def synthesize_chunk_openai(text, api_key, out_path):
    audio_bytes = _with_retries(
        lambda: _request_tts_openai(text, api_key), "OpenAI TTS"
    )
    with open(out_path, "wb") as f:
        f.write(audio_bytes)


def _concat_with_crossfade(part_paths, out_path, crossfade_duration=0.12):
    """Assemble les morceaux avec un court fondu enchaîné à chaque jointure
    plutôt qu'une coupure nette — atténue la perception des changements de
    ton/énergie entre deux générations indépendantes du modèle."""
    if len(part_paths) == 1:
        subprocess.check_call(
            [
                "ffmpeg", "-y", "-i", part_paths[0],
                "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", out_path,
            ]
        )
        return

    cmd = ["ffmpeg", "-y"]
    for p in part_paths:
        cmd += ["-i", p]

    filters = []
    for i in range(len(part_paths)):
        # Format uniforme avant le fondu : les morceaux peuvent différer
        # légèrement de sample rate/canaux selon la réponse de l'API.
        filters.append(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[n{i}]")
    prev_label = "n0"
    for i in range(1, len(part_paths)):
        out_label = f"cf{i}" if i < len(part_paths) - 1 else "mixout"
        filters.append(
            f"[{prev_label}][n{i}]acrossfade=d={crossfade_duration}:c1=tri:c2=tri[{out_label}]"
        )
        prev_label = out_label

    # Avec beaucoup de morceaux (génération phrase par phrase), le graphe de
    # filtres est trop long pour tenir en argument de ligne de commande —
    # on le passe par fichier (-filter_complex_script) pour rester dans les
    # limites du système, quel que soit le nombre de morceaux.
    script_path = os.path.join(os.path.dirname(part_paths[0]), "_filter_complex.txt")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(";".join(filters))

    cmd += [
        "-filter_complex_script", script_path,
        "-map", "[mixout]",
        "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100",
        out_path,
    ]
    subprocess.check_call(cmd)


# Chien de garde anti-explosion de requêtes : un épisode normal tient en
# ~8-10 morceaux. Si un futur changement de réglage (max_chars trop petit,
# régression du découpage...) en produit brutalement beaucoup plus — comme
# le découpage phrase par phrase qui avait généré ~240 requêtes et épuisé
# le quota Gemini en un seul épisode — on préfère échouer bruyamment AVANT
# d'appeler l'API plutôt que de cramer un budget de requêtes (quota ou,
# pire, crédits payants OpenAI/ElevenLabs) sans s'en rendre compte.
MAX_TTS_CHUNKS = 20


def synthesize(text, out_path):
    provider = CONFIG.get("tts_provider", "gemini")
    if provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            sys.exit("ERREUR : variable d'environnement GEMINI_API_KEY absente.")
        synth_fn, ext, max_chars = synthesize_chunk_gemini, "wav", 1500
        # Respecte la limite de 10 requêtes/minute du modèle preview
        # (7s de marge entre appels -> ~8,5 req/min). ElevenLabs et OpenAI
        # n'ont pas ce genre de quota restrictif, donc pas de pause pour
        # ces fournisseurs.
        pace_seconds = 7
    elif provider == "elevenlabs":
        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            sys.exit("ERREUR : variable d'environnement ELEVENLABS_API_KEY absente.")
        synth_fn, ext, max_chars = synthesize_chunk_elevenlabs, "mp3", 1500
        pace_seconds = 0
    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            sys.exit("ERREUR : variable d'environnement OPENAI_API_KEY absente.")
        # Fournisseur payant à l'usage (pas de raison de tenir au ton comme
        # pour Gemini) : des morceaux plus larges (proche de la limite de
        # 4096 caractères de l'API) veulent dire moins de requêtes, donc
        # moins de risque de coût, pour le même texte total.
        synth_fn, ext, max_chars = synthesize_chunk_openai, "mp3", 3800
        pace_seconds = 0
    else:
        sys.exit(
            f"ERREUR : tts_provider inconnu dans config.json : {provider!r} "
            "(attendu 'gemini', 'elevenlabs' ou 'openai')."
        )

    chunks = chunk_text(text, max_chars=max_chars)
    if len(chunks) > MAX_TTS_CHUNKS:
        sys.exit(
            f"ERREUR : découpage en {len(chunks)} morceaux pour la synthèse "
            f"{provider} — au-delà du plafond de sécurité ({MAX_TTS_CHUNKS}). "
            "Aucune requête envoyée. Vérifie chunk_text()/max_chars avant de "
            "relancer : c'est probablement une régression du découpage, pas "
            "un texte légitimement 20x plus long que d'habitude."
        )
    print(f"     ({len(chunks)} requête(s) {provider})")

    tmp_dir = tempfile.mkdtemp(prefix="tts_")
    try:
        part_paths = []
        for i, chunk in enumerate(chunks):
            if i > 0 and pace_seconds:
                time.sleep(pace_seconds)
            part_path = os.path.join(tmp_dir, f"part_{i:03d}.{ext}")
            synth_fn(chunk, api_key, part_path)
            part_paths.append(part_path)
        _concat_with_crossfade(part_paths, out_path)
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

    # dynaudnorm lisse les écarts de volume de la voix (utile tant que la
    # synthèse dérive parfois vers un ton plus doux/chuchoté en cours de
    # génération) — remonte les passages trop bas plutôt que d'appliquer
    # un simple gain fixe.
    voice_filter = "dynaudnorm=f=200:g=15:m=20"

    filters = []
    if have_music:
        filters.append(
            f"[0:a]{voice_filter},adelay={int(lead_in*1000)}|{int(lead_in*1000)},apad=pad_dur={tail}[v]"
        )
        filters.append(f"[{music_idx}:a]volume={vol}[m]")
        filters.append("[v][m]amix=inputs=2:duration=first:dropout_transition=4[bedraw]")
    else:
        filters.append(
            f"[0:a]{voice_filter},adelay={int(lead_in*1000)}|{int(lead_in*1000)},apad=pad_dur={tail}[bedraw]"
        )
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

    print(f"2/4  Synthèse vocale ({CONFIG.get('tts_provider', 'gemini')})…")
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
