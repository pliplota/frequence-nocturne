# Fréquence Nocturne — Guide d'installation

Podcast quotidien 100 % automatique et 100 % gratuit :
texte généré par Gemini → voix Google Cloud Text-to-Speech → mixage ffmpeg → flux RSS → Spotify.
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

1. Récupère une clé gratuite sur https://aistudio.google.com/apikey
   (c'est la même que pour ton Studio Pocket).
2. Dans le dépôt : *Settings → Secrets and variables → Actions → New repository secret*.
3. Nom : `GEMINI_API_KEY` — Valeur : ta clé. Elle ne sera jamais visible.

## 2bis. Ajouter ta clé Google Cloud Text-to-Speech

La voix est synthétisée par Google Cloud TTS. Contrairement à la clé
Gemini, celle-ci nécessite un compte Google Cloud avec la facturation
activée (carte bancaire enregistrée).

- **Voix Neural2** (`fr-FR-Neural2-G`) : reste dans le palier gratuit tant
  que le podcast ne dépasse pas quelques millions de caractères par mois
  (largement suffisant pour un usage quotidien).
- **Voix Studio** (`fr-FR-Studio-D`, utilisée actuellement — plus naturelle,
  calibrée pour la narration) : **payante dès le premier caractère**, pas
  de palier gratuit. Le réglage de tonalité (`voice_pitch`) ne s'applique
  pas à cette famille de voix (limitation de l'API Google), seul le débit
  (`voice_rate`) reste ajustable.

Vérifie les tarifs actuels sur https://cloud.google.com/text-to-speech/pricing
avant d'activer — ils peuvent changer. Avec une voix Studio payante,
configure aussi une **alerte de budget** pour éviter toute mauvaise
surprise : *Billing → Budgets & alerts → Create budget* sur ton projet
Google Cloud, avec un seuil bas (quelques euros).

1. Crée un projet sur https://console.cloud.google.com, active la
   facturation, puis active l'API *Cloud Text-to-Speech*
   (*APIs & Services → Enable APIs and Services*).
2. Crée une clé API (*APIs & Services → Credentials → Create credentials →
   API key*), et restreins-la à l'API *Cloud Text-to-Speech* uniquement.
3. Dans le dépôt : *Settings → Secrets and variables → Actions → New
   repository secret*.
4. Nom : `GOOGLE_TTS_API_KEY` — Valeur : ta clé. Elle ne sera jamais visible.

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
- **Transparence** : reste dans la convention du genre (« témoignages
  envoyés par nos auditeurs ») sans affirmer qu'ils sont vérifiés. Et
  dès que de vrais auditeurs t'écriront, tu pourras mélanger vrais
  témoignages reçus et récits générés.
