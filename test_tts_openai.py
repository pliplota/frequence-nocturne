#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test rapide et pas cher de la voix OpenAI TTS, sans passer par un épisode
complet (donc sans en payer le coût). Réutilise directement les fonctions
de generate_episode.py (même modèle, même voix) pour tester exactement ce
qui sera utilisé en production. Génère DEUX fichiers séparés — présentateur
et histoire ont des instructions de ton différentes depuis la segmentation
du 2026-07-24, donc les tester ensemble en un seul appel ne reflète plus le
pipeline réel.

Usage :
  set OPENAI_API_KEY=sk-...        (PowerShell : $env:OPENAI_API_KEY = "sk-...")
  python test_tts_openai.py
  python test_tts_openai.py cedar                       (même test, avec une autre voix)
  python test_tts_openai.py "Un autre texte de test à lire."   (uniquement le segment histoire)
"""

import os
import sys

import generate_episode as ge

KNOWN_VOICES = {
    "alloy", "ash", "ballad", "coral", "echo", "fable",
    "nova", "onyx", "sage", "shimmer", "verse", "marin", "cedar",
}

PRESENTATEUR_TEXT = (
    f"{ge.CONFIG['intro_ritual']} "
    f"Bonsoir, ici {ge.CONFIG['presenter_name']}. Ce soir, comme toutes les nuits, "
    "j'ai reçu vos témoignages. En voici un premier, qui m'a été envoyé par "
    "Sophie, dans les Vosges."
)

HISTOIRE_TEXT = (
    "Je me suis réveillée vers trois heures du matin, sans raison. La "
    "maison était silencieuse. Et puis j'ai entendu, très distinctement, "
    "des pas dans le couloir. Lents. Réguliers. Je vis seule. Je n'ai "
    "jamais retrouvé d'explication."
)


def synth(label, text, style, suffix):
    print(f"\n--- {label} ---")
    print(f"Texte : {text}")
    print(f"Style : {style[:100]}..." if style else "Style : (aucun, défaut config)")
    out_path = os.path.join(ge.ROOT, f"test_voice_openai_{suffix}.mp3")
    ge.synthesize_chunk_openai(text, os.environ["OPENAI_API_KEY"], out_path, style=style)
    print(f"OK -> {out_path}")


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("ERREUR : variable d'environnement OPENAI_API_KEY absente.")

    args = sys.argv[1:]
    if len(args) == 1 and args[0].lower() in KNOWN_VOICES:
        # Override juste pour ce run — ne touche pas config.json.
        ge.CONFIG["openai_voice"] = args[0].lower()
        args = []

    model = ge.CONFIG.get("openai_tts_model", "gpt-4o-mini-tts")
    voice = ge.CONFIG.get("openai_voice", "onyx")
    print(f"Modèle : {model}  |  Voix : {voice}")

    if args:
        # Texte personnalisé : testé uniquement avec le style "histoire"
        # (c'est celui qu'on cherche à rendre plus expressif).
        text = " ".join(args)
        synth("histoire (texte personnalisé)", text, ge._style_for_segment("openai", "histoire"), f"custom_{voice}")
        return

    # Suffixe avec le nom de la voix pour pouvoir garder plusieurs essais
    # côte à côte (comparer onyx vs cedar sans que l'un écrase l'autre).
    synth("presentateur", PRESENTATEUR_TEXT, ge._style_for_segment("openai", "presentateur"), f"presentateur_{voice}")
    synth("histoire", HISTOIRE_TEXT, ge._style_for_segment("openai", "histoire"), f"histoire_{voice}")


if __name__ == "__main__":
    main()
