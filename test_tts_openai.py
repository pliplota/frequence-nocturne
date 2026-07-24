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
  python test_tts_openai.py "Un autre texte de test à lire."   (uniquement le segment histoire)
"""

import os
import sys

import generate_episode as ge

PRESENTATEUR_TEXT = (
    f"{ge.CONFIG['intro_ritual']} "
    f"Bonsoir, ici {ge.CONFIG['presenter_name']}. Ce soir, comme toutes les nuits, "
    "j'ai reçu vos témoignages. En voici un premier, qui m'a été envoyé par "
    "Sophie L., dans les Vosges."
)

HISTOIRE_TEXT = (
    "Je me suis réveillée vers trois heures du matin, sans raison. La "
    "maison était silencieuse. Et puis j'ai entendu, très distinctement, "
    "des pas dans le couloir. Lents. Réguliers. Je vis seule. Je n'ai "
    "jamais retrouvé d'explication. Sophie L., dans les Vosges."
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

    model = ge.CONFIG.get("openai_tts_model", "gpt-4o-mini-tts")
    voice = ge.CONFIG.get("openai_voice", "onyx")
    print(f"Modèle : {model}  |  Voix : {voice}")

    if len(sys.argv) > 1:
        # Texte personnalisé : testé uniquement avec le style "histoire"
        # (c'est celui qu'on cherche à rendre plus expressif).
        text = " ".join(sys.argv[1:])
        synth("histoire (texte personnalisé)", text, ge._style_for_segment("openai", "histoire"), "custom")
        return

    synth("presentateur", PRESENTATEUR_TEXT, ge._style_for_segment("openai", "presentateur"), "presentateur")
    synth("histoire", HISTOIRE_TEXT, ge._style_for_segment("openai", "histoire"), "histoire")


if __name__ == "__main__":
    main()
