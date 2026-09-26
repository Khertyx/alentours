# Alentours

Que faire autour de vous : événements, patrimoine, musées et balades dans un rayon de 20 km, avec l'histoire de chaque lieu, un parcours du jour et des filtres par groupe (seul, couple, famille, enfants, ados, amis, situation de handicap).

Un service [Khertyx](https://www.khertyx.com). Site statique, gratuit à héberger, sans cookie ni traceur.

## Structure

| Fichier | Rôle |
|---|---|
| `page.html` | L'application complète (HTML, CSS, JavaScript) |
| `build_site.py` | Génère `dist/` : accueil, 54 pages communes, mentions légales, sitemap, robots, CNAME |
| `communes.json` | Liste des communes (nom, latitude, longitude, département) |
| `fonts/`, `assets/` | Polices hébergées ici (aucun appel à Google) et images |
| `.github/workflows/deploy.yml` | Publication automatique sur GitHub Pages, rafraîchie chaque nuit |
| `wordpress/page-alentours.html` | Bloc à coller dans WordPress pour intégrer Alentours à khertyx.com |

## Mise en ligne

### 1. GitHub Pages
1. Dépôt > **Settings > Pages > Build and deployment > Source : GitHub Actions**.
2. Onglet **Actions > Publier Alentours > Run workflow**. Le premier déploiement prend environ 5 minutes.

### 2. Domaine alentours.khertyx.com (IONOS)
1. IONOS > **Domaines et SSL > khertyx.com > DNS > Ajouter un enregistrement**.
2. Type **CNAME**, nom d'hôte `alentours`, pointe vers `khertyx.github.io`, TTL 1 heure.
3. GitHub > **Settings > Pages > Custom domain** : `alentours.khertyx.com`, puis cochez **Enforce HTTPS** (disponible après la vérification DNS, quelques minutes).

Le fichier `CNAME` est généré à chaque déploiement.

### 3. Intégration dans khertyx.com (WordPress)
- Créez une page « Alentours », ajoutez un bloc **HTML personnalisé** et collez `wordpress/page-alentours.html`.
- Ajoutez la page au menu. Pour le référencement, le lien principal doit pointer vers `https://alentours.khertyx.com/`.

### 4. Référencement
- Google Search Console et Bing Webmaster : ajoutez `https://alentours.khertyx.com` et envoyez `https://alentours.khertyx.com/sitemap.xml`.
- Publiez chaque semaine une page « Que faire ce week-end à [ville] » sur Facebook, Instagram et LinkedIn, avec le lien de la page commune correspondante.

## Utilisation locale
```bash
SITE_URL=http://localhost:8000 python3 build_site.py
cd dist && python3 -m http.server 8000
```

## Ajouter une commune
Ajoutez `["Nom", latitude, longitude, "Département"]` dans `communes.json`, puis relancez le workflow (ou poussez sur `main`).

## Sources de données
OpenAgenda (via OpenDataSoft), OpenStreetMap (Overpass, Nominatim), API Adresse data.gouv.fr, Wikipédia et Wikidata, Open-Meteo. Toutes gratuites et sans clé. Détails dans la page `mentions-legales`.

## Licences
Polices Cormorant Garamond et Hanken Grotesk : SIL Open Font License 1.1 (via Fontsource). Données : licences citées ci-dessus.
