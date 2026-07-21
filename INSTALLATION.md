# Fréquence Nocturne — Guide d'installation

Podcast quotidien 100 % automatique :
texte généré par Gemini → voix Gemini TTS → mixage ffmpeg → flux RSS → Spotify.
Aucun serveur chez toi : tout tourne sur GitHub Actions.

---

## 1. Créer le dépôt GitHub

1. Crée un compte sur github.com si besoin.
2. Crée un dépôt **public** nommé `frequence-nocturne`
   (public = obligatoire pour GitHub Pages gratuit et Actions illimité).
3. Téléverse tout le contenu de ce dossier dans le dépôt
   (bouton *Add file → Upload files*, glisse-dépose tout, y compris le dossier
   `.github` — si l'upload web ignore les dossiers cachés, crée le fichier
   `.github/workflows/episode-quotidien.yml` à la main via *Add file → Create new file*).

## 2. Ajouter ta clé Gemini

Cette seule clé sert à la fois pour le texte et pour la voix (Gemini TTS
utilise la même API que la génération de texte).

1. Récupère une clé gratuite sur https://aistudio.google.com/apikey
   (c'est la même que pour ton Studio Pocket).
2. Dans le dépôt : *Settings → Secrets and variables → Actions → New repository secret*.
3. Nom : `GEMINI_API_KEY` — Valeur : ta clé. Elle ne sera jamais visible.

⚠️ Le modèle vocal (`gemini-3.1-flash-tts-preview` dans `config.json`,
champ `tts_model`) est en préversion : ses conditions d'usage/tarifaires
peuvent différer de celles des modèles Gemini standard, et son
comportement (nom exact, disponibilité) peut changer sans préavis côté
Google. Vérifie ton tableau de bord AI Studio si tu as un doute sur la
facturation.

⚠️ **Quota très restreint** (constaté en pratique) : 10 requêtes/minute
et **100 requêtes/jour** pour ce modèle. Chaque épisode fait plusieurs
requêtes (`chunk_text` découpe le script en morceaux, une requête par
morceau — voir le champ `voice`/`tts_model` et la fonction `chunk_text`
dans `generate_episode.py`). Avec deux créneaux automatiques par jour,
mieux vaut garder peu de morceaux par épisode (~8-10) pour laisser de
la marge à des tests manuels ; un découpage trop fin (ex. phrase par
phrase) épuise le quota du jour en un seul épisode, avec un délai de
récupération pouvant aller jusqu'à ~24h.

## 3. Ajouter ta musique et la pochette

- Mets ta musique d'ambiance dans `music/ambiance.mp3`
  (elle sera bouclée automatiquement et mixée à ~16 % du volume, avec
  5 s d'intro musicale et un fondu de sortie).
  ⚠️ Utilise une musique libre de droits ou dont tu possèdes les droits :
  Spotify détecte et retire les épisodes contenant de la musique protégée.
- Mets la pochette de l'émission dans `docs/cover.jpg`
  (image **carrée**, entre 1400×1400 et 3000×3000 px, JPG ou PNG —
  exigence de Spotify).
- Optionnel : dépose `music/generique_intro.mp3` et
  `music/generique_outro.mp3` pour ajouter un générique (jingle) joué
  en ouverture et fermeture de chaque épisode, distinct de la musique
  d'ambiance en fond continu. Sans ces fichiers, l'épisode se limite à
  l'ambiance (comportement par défaut).

## 4. Activer GitHub Pages

*Settings → Pages → Source : « Deploy from a branch » → Branch : `main`,
dossier `/docs` → Save.*

Ton flux sera alors accessible à :
`https://TON-PSEUDO.github.io/frequence-nocturne/feed.xml`

## 5. Mettre à jour la config

Dans `config.json`, remplace la ligne `base_url` par ta vraie adresse :
`"base_url": "https://TON-PSEUDO.github.io/frequence-nocturne"`.
Tu peux aussi y changer le nom de l'émission, du présentateur, l'adresse
mail de contact, les textes rituels d'intro/outro, la voix, le volume de la
musique, etc. Pense à créer réellement l'adresse Gmail de contact pour
recevoir de vrais témoignages d'auditeurs.

## 6. Générer le premier épisode

*Onglet Actions → « Épisode quotidien » → Run workflow.*
Deux minutes plus tard, vérifie que `docs/feed.xml` et
`docs/episodes/DATE.mp3` sont apparus. Écoute l'épisode via
`https://TON-PSEUDO.github.io/frequence-nocturne/episodes/DATE.mp3`.

## 7. Déclarer le podcast sur Spotify (une seule fois)

1. Va sur https://creators.spotify.com → *Get started* →
   « J'ai déjà un podcast » → colle l'URL du flux :
   `https://TON-PSEUDO.github.io/frequence-nocturne/feed.xml`
2. Spotify vérifie la propriété en envoyant un code à l'adresse
   `itunes:email` du flux (celle de `config.json` → mets une adresse
   que tu consultes vraiment).
3. Valide. L'émission apparaît sous quelques heures.

Ensuite : **deux épisodes sont générés et poussés automatiquement chaque
jour** — un vers 5h30 (prêt pour le matin) et un vers 18h30 (prêt avant
20h00). **Spotify les récupère automatiquement**, avec le même délai de
rafraîchissement à chaque fois (la publication pile à l'heure n'est pas
garantissable à la minute près).

Le même flux RSS peut aussi être déclaré sur Apple Podcasts, Deezer,
Amazon Music, etc.

---

## Bon à savoir

- **Retard possible du cron** : GitHub lance les tâches planifiées avec
  parfois 5-30 min de retard. D'où les déclenchements à 5h30 et 18h30
  plutôt que pile à l'heure visée (7h00 et 20h00).
- **Heure d'hiver** : le cron est en UTC ; en hiver les épisodes partiront
  à 4h30 et 17h30 au lieu de 5h30 et 18h30. Aucun impact, ils seront juste
  prêts plus tôt.
- **Deux créneaux distincts** : le créneau du matin (cron `30 3 * * *`)
  produit `AAAA-MM-JJ.mp3` ; celui du soir (cron `30 16 * * *`) produit
  `AAAA-MM-JJ-soir.mp3`. Chacun ne se génère qu'une fois par jour — la
  correspondance cron → suffixe est dans `SCHEDULE_SLOTS` en haut de
  `generate_episode.py`, à ajuster si tu changes les horaires.
- **Poids du dépôt** : ~7-13 Mo par épisode, deux épisodes par jour, soit
  ~5-9 Go/an. GitHub tolère jusqu'à ~5 Go. Il faudra donc archiver les
  vieux épisodes ailleurs (archive.org) ou passer sur un hébergeur de
  podcast gratuit (le flux RSS reste le même principe) plus tôt qu'avec
  un seul épisode quotidien — probablement en cours d'année plutôt
  qu'au bout d'un an.
- **Épisode manuel** : onglet *Actions → Run workflow* à tout moment.
- **Modifier le style des histoires** : tout le "prompt" d'écriture est
  dans `generate_episode.py`, fonction `build_prompt` — les thèmes sont
  dans la liste `THEMES` en haut du fichier.
- **Changer de voix ou de ton** : `voice` dans `config.json` prend un nom
  de voix Gemini TTS (ex. `Charon`, `Puck`, `Umbriel` — teste-les sur
  https://cloud.google.com/text-to-speech, section démonstration, ou dans
  Media Studio sur la Console Google Cloud). Le débit/la tonalité ne se
  règlent plus par des paramètres numériques mais par une consigne en
  langage naturel : `tts_style_prompt` dans `config.json`.
- **Transparence** : reste dans la convention du genre (« témoignages
  envoyés par nos auditeurs ») sans affirmer qu'ils sont vérifiés. Et
  dès que de vrais auditeurs t'écriront, tu pourras mélanger vrais
  témoignages reçus et récits générés.
