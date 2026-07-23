#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test rapide de l'image de couverture OpenAI, sans passer par un épisode
complet. Réutilise generate_episode_image() (même modèle, même prompt de
style que config.json).

Usage :
  set OPENAI_API_KEY=sk-...        (PowerShell : $env:OPENAI_API_KEY = "sk-...")
  python test_image_openai.py
"""

import os
import sys

import generate_episode as ge

FAKE_EP_DATA = {
    "title": "L'Horloge du Voisin, le Client Absent et le Sourire Figé",
    "description": (
        "Trois témoignages troublants : des bruits mécaniques incessants, "
        "une rencontre énigmatique dans un supermarché de nuit, et une "
        "photo de famille où un détail cloche."
    ),
}


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("ERREUR : variable d'environnement OPENAI_API_KEY absente.")

    prompt = ge.build_image_prompt(FAKE_EP_DATA)
    print(f"Modèle  : {ge.CONFIG.get('openai_image_model', 'gpt-image-1')}")
    print(f"Taille  : {ge.CONFIG.get('openai_image_size', '1024x1024')}")
    print(f"Qualité : {ge.CONFIG.get('openai_image_quality', 'low')}")
    print(f"Prompt  : {prompt}\n")

    out_path = os.path.join(ge.ROOT, "test_image_openai.jpg")
    ok = ge.generate_episode_image(FAKE_EP_DATA, out_path)
    if not ok:
        sys.exit("Échec de la génération (voir avertissement ci-dessus).")

    print(f"\nOK -> {out_path}")


if __name__ == "__main__":
    main()
