#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test rapide et pas cher de la voix OpenAI TTS du présentateur, sans passer
par un épisode complet (donc sans en payer le coût). Réutilise directement
les fonctions de generate_episode.py (même modèle, même voix, mêmes
instructions de ton que config.json) pour tester exactement ce qui sera
utilisé en production.

Usage :
  set OPENAI_API_KEY=sk-...        (PowerShell : $env:OPENAI_API_KEY = "sk-...")
  python test_tts_openai.py
  python test_tts_openai.py "Un autre texte de test à lire."
"""

import os
import sys

import generate_episode as ge

DEFAULT_TEXT = (
    f"{ge.CONFIG['intro_ritual']} "
    f"Bonsoir, ici {ge.CONFIG['presenter_name']}. Ce soir, comme toutes les nuits, "
    "j'ai reçu vos témoignages. En voici un premier, qui m'a été envoyé par "
    "Sophie L., dans les Vosges."
)


def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("ERREUR : variable d'environnement OPENAI_API_KEY absente.")

    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_TEXT
    model = ge.CONFIG.get("openai_tts_model", "gpt-4o-mini-tts")
    voice = ge.CONFIG.get("openai_voice", "onyx")

    print(f"Modèle  : {model}")
    print(f"Voix    : {voice}")
    print(f"Texte   : {text}")
    print(f"({len(text)} caractères — un seul appel API, coût minime)")

    out_path = os.path.join(ge.ROOT, "test_voice_openai.mp3")
    ge.synthesize_chunk_openai(text, api_key, out_path)

    print(f"\nOK -> {out_path}")


if __name__ == "__main__":
    main()
