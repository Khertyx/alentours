#!/usr/bin/env python3
"""Génère le site Alentours (accueil, une page par commune, mentions légales, sitemap, robots, CNAME).

Usage local :  SITE_URL=https://alentours.khertyx.com python3 build_site.py
Résultat    :  dossier dist/ (publié par GitHub Pages via .github/workflows/deploy.yml)

Aucune dépendance externe. Une source de données qui échoue est ignorée : la page reste valide.
REUSE=1 réutilise les aperçus déjà générés (aucun appel réseau)."""
import json, os, re, shutil, sys, time, html, unicodedata, urllib.request, urllib.parse, urllib.error, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.environ.get('SITE_URL', 'https://alentours.khertyx.com').rstrip('/')
BASE = urllib.parse.urlparse(SITE).path.rstrip('/')          # '' pour un domaine, '/alentours' pour github.io/alentours
HOST = urllib.parse.urlparse(SITE).netloc
OUT = os.path.join(HERE, 'dist')
UA = {'User-Agent': 'Alentours-build/1.0 (contact@khertyx.com)'}
E = html.escape

# ------------------------------------------------------------------ utilitaires
def slug(s):
    s = unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')

def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    for essai in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as err:
            if err.code == 429 and essai < 2:
                time.sleep(4 * (essai + 1)); continue
            raise

def weekend():
    d = datetime.datetime.utcnow() + datetime.timedelta(hours=2)
    dow = d.weekday()
    if dow == 5: s = d.date(); e = s + datetime.timedelta(days=1)
    elif dow == 6: s = e = d.date()
    else: s = d.date() + datetime.timedelta(days=5 - dow); e = s + datetime.timedelta(days=1)
    return s, e

# ------------------------------------------------------------------ données d'aperçu (SEO)
def events(lat, lon, s, e):
    base = 'https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/evenements-publics-openagenda/records?'
    q = urllib.parse.urlencode({
        'where': f"within_distance(location_coordinates, geom'POINT({lon} {lat})', 20km) and firstdate_begin <= date'{e}' and lastdate_end >= date'{s}'",
        'limit': 40, 'order_by': 'firstdate_begin desc',
        'select': 'title_fr,firstdate_begin,lastdate_end,location_name,location_city,daterange_fr,canonicalurl'})
    out, seen = [], set()
    for r in get(base + q).get('results', []):
        k = (r.get('title_fr') or '').lower()
        if not k or k in seen: continue
        seen.add(k)
        try: span = (datetime.datetime.fromisoformat(r['lastdate_end']) - datetime.datetime.fromisoformat(r['firstdate_begin'])).days
        except Exception: span = 999
        out.append((span, r))
    out.sort(key=lambda x: x[0])
    return [r for _, r in out[:8]]

HER = re.compile(r'ch[aâ]teau|[ée]glise|chapelle|abbaye|manoir|mus[ée]e|cath[ée]drale|\bfort\b|phare|moulin|ruines?|jardin|calvaire|prieur[ée]|basilique|menhir|dolmen|alignements|couvent|monast[èe]re|palais|remparts|donjon|bastide|m[ée]galith', re.I)
def heritage(lat, lon):
    q = urllib.parse.urlencode({'action': 'query', 'format': 'json', 'generator': 'geosearch', 'ggscoord': f'{lat}|{lon}', 'ggsradius': 10000, 'ggslimit': 50, 'prop': 'coordinates'})
    pages = get('https://fr.wikipedia.org/w/api.php?' + q).get('query', {}).get('pages', {})
    return [p['title'] for p in pages.values() if HER.search(p['title'])][:8]

def prerender(name, dept, ev, her, s, e):
    parts = [f'<div class="empty" style="text-align:left"><h3>Que faire à {E(name)} ({E(dept)}) ?</h3>']
    parts.append(f'<p>Alentours réunit les événements, les balades et le patrimoine dans un rayon de 20 km autour de {E(name)}. Aperçu pour le week-end du {s.strftime("%d/%m")} au {e.strftime("%d/%m/%Y")}. Les résultats complets se chargent dans un instant.</p>')
    if ev: parts.append('<h4>Événements à ne pas manquer</h4><ul>' + ''.join(f'<li>{E(r["title_fr"])} ({E(r.get("daterange_fr") or "")}, {E(r.get("location_city") or "")})</li>' for r in ev) + '</ul>')
    if her: parts.append(f'<h4>Patrimoine à découvrir autour de {E(name)}</h4><ul>' + ''.join(f'<li>{E(t)}</li>' for t in her) + '</ul>')
    parts.append('</div>')
    return ''.join(parts)

def jsonld(name, url, ev):
    items = [{'@type': 'ListItem', 'position': i, 'item': {'@type': 'Event', 'name': r['title_fr'], 'startDate': r.get('firstdate_begin'), 'endDate': r.get('lastdate_end'),
             'location': {'@type': 'Place', 'name': r.get('location_name') or name, 'address': r.get('location_city') or name},
             **({'url': r['canonicalurl']} if r.get('canonicalurl') else {})}} for i, r in enumerate(ev, 1)]
    data = [{'@context': 'https://schema.org', '@type': 'WebPage', 'name': f'Que faire à {name} ce week-end ?', 'url': url, 'inLanguage': 'fr',
             'publisher': {'@type': 'Organization', 'name': 'Khertyx', 'url': 'https://www.khertyx.com'}}]
    if items: data.append({'@context': 'https://schema.org', '@type': 'ItemList', 'itemListElement': items})
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + '</script>'

# ------------------------------------------------------------------ gabarits
FONTS_CSS = ('@font-face{font-family:"Cormorant Garamond";font-style:normal;font-weight:300 700;font-display:swap;src:url(%(b)s/fonts/cormorant-garamond-latin-wght-normal.woff2) format("woff2")}'
             '@font-face{font-family:"Cormorant Garamond";font-style:italic;font-weight:300 700;font-display:swap;src:url(%(b)s/fonts/cormorant-garamond-latin-wght-italic.woff2) format("woff2")}'
             '@font-face{font-family:"Hanken Grotesk";font-style:normal;font-weight:100 900;font-display:swap;src:url(%(b)s/fonts/hanken-grotesk-latin-wght-normal.woff2) format("woff2")}') % {'b': BASE}

def head(title, desc, url, extra=''):
    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<title>{E(title)}</title><meta name="description" content="{E(desc)}"><link rel="canonical" href="{url}">'
            f'<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}"><meta property="og:type" content="website">'
            f'<meta property="og:locale" content="fr_FR"><meta property="og:url" content="{url}"><meta property="og:image" content="{SITE}/assets/og.png">'
            f'<meta name="twitter:card" content="summary_large_image"><meta name="theme-color" content="#2c6b56">'
            f'<link rel="icon" type="image/svg+xml" href="{BASE}/assets/favicon.svg"><link rel="manifest" href="{BASE}/manifest.webmanifest">'
            f'<link rel="preload" href="{BASE}/fonts/cormorant-garamond-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>'
            f'<script>window.ALENTOURS_BASE={json.dumps(BASE)};</script>'
            f'{extra}<style>{FONTS_CSS}body{{margin:0}}img{{max-width:100%}}[hidden]{{display:none!important}}</style></head><body>')

LEGAL = '''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Confidentialité et mentions légales | Alentours</title><meta name="description" content="Mentions légales et politique de confidentialité d'Alentours, un service Khertyx. Aucune donnée personnelle collectée, aucun cookie.">
<link rel="canonical" href="%(site)s/mentions-legales/"><link rel="icon" type="image/svg+xml" href="%(base)s/assets/favicon.svg"><meta name="theme-color" content="#2c6b56">
<style>%(fonts)s
:root{--bg:#f8f7f2;--ink:#1e352b;--muted:#5b6a62;--gold:#7a5c22;--line:#e4e0d3;--acc:#2c6b56}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.65 "Hanken Grotesk",system-ui,sans-serif}
main{max-width:760px;margin:0 auto;padding:40px 20px 70px}
h1{font:600 clamp(2.4rem,6vw,3.4rem)/1 "Cormorant Garamond",Georgia,serif;margin:0 0 6px}
h2{font:600 1.7rem/1.1 "Cormorant Garamond",Georgia,serif;margin:36px 0 8px;padding-top:18px;border-top:1px solid var(--line)}
a{color:var(--acc)}p,li{max-width:66ch}small{color:var(--muted)}
.back{display:inline-block;margin-bottom:22px;font-weight:600;text-decoration:none}
table{border-collapse:collapse;width:100%%;font-size:.95rem}td,th{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
.wrap-t{overflow-x:auto}
</style></head><body><main>
<a class="back" href="%(base)s/">← Retour à Alentours</a>
<h1>Confidentialité et mentions légales</h1><small>Dernière mise à jour : %(date)s</small>

<h2>En bref</h2>
<p>Alentours ne crée pas de compte, n'utilise aucun cookie et ne collecte aucune donnée personnelle sur ses propres serveurs. Vos choix (favoris, groupe, âge des enfants, besoin d'accessibilité) restent dans votre navigateur. Votre position n'est utilisée que si vous cliquez sur « Ma position », et uniquement pour interroger les sources de données ci-dessous.</p>

<h2>Sources de données interrogées depuis votre navigateur</h2>
<p>Pour afficher les résultats, votre navigateur contacte directement les services ci-dessous. Ils reçoivent, comme pour toute page web, votre adresse IP et la requête envoyée (coordonnées du lieu recherché). Alentours ne reçoit aucune de ces informations.</p>
<div class="wrap-t"><table><thead><tr><th>Service</th><th>Usage</th></tr></thead><tbody>
<tr><td>OpenAgenda, via OpenDataSoft</td><td>Événements publics</td></tr>
<tr><td>OpenStreetMap (Overpass, Nominatim)</td><td>Lieux, accessibilité, recherche d'adresse</td></tr>
<tr><td>API Adresse (data.gouv.fr)</td><td>Recherche de communes et d'adresses</td></tr>
<tr><td>Wikipédia et Wikidata (Wikimedia)</td><td>Histoire des lieux, photos, repères</td></tr>
<tr><td>Open-Meteo</td><td>Prévisions météo</td></tr>
<tr><td>DATAtourisme (fichiers servis par ce site)</td><td>Événements des offices de tourisme, mis à jour chaque nuit</td></tr>
</tbody></table></div>
<p>Les polices de caractères sont hébergées sur ce site : aucun appel à Google Fonts.</p>

<h2>Stockage local</h2>
<p>Vos favoris et préférences sont enregistrés dans le stockage local de votre navigateur (localStorage). Ils ne quittent pas votre appareil et disparaissent si vous effacez les données du site.</p>

<h2>Vos droits</h2>
<p>Aucune donnée personnelle n'étant conservée par l'éditeur, il n'y a rien à consulter, rectifier ou supprimer côté Alentours. Pour toute question sur la protection des données, écrivez à <a href="mailto:contact@khertyx.com">contact@khertyx.com</a>. Vous pouvez aussi saisir la CNIL (cnil.fr).</p>

<h2>Éditeur</h2>
<p><strong>Khertyx</strong>, entreprise individuelle (micro-entreprise) de Yannick Lejoly<br>
SIRET 503 289 670 00039<br>
Pléchâtel (35470), Ille-et-Vilaine, France<br>
<a href="mailto:contact@khertyx.com">contact@khertyx.com</a> · +33 6 01 85 09 87<br>
Directeur de la publication : Yannick Lejoly<br>
Site de l'agence : <a href="https://www.khertyx.com">www.khertyx.com</a></p>

<h2>Hébergement</h2>
<p>GitHub, Inc., 88 Colin P. Kelly Jr. Street, San Francisco, CA 94107, États-Unis (GitHub Pages).</p>

<h2>Contenus et licences</h2>
<p>Événements : licence ouverte des agendas publiés sur OpenAgenda, et DATAtourisme (Licence Ouverte Etalab, source et date de mise à jour indiquées sur chaque fiche). Lieux : © contributeurs OpenStreetMap, licence ODbL. Textes et images Wikipédia : licence CC BY-SA, avec lien vers l'article source sur chaque fiche. Polices Cormorant Garamond et Hanken Grotesk : SIL Open Font License.</p>

<h2>Exactitude des informations</h2>
<p>Les horaires, tarifs et informations d'accessibilité viennent des organisateurs et de contributeurs bénévoles. Ils peuvent être incomplets ou avoir changé : vérifiez-les auprès du lieu avant de vous déplacer, en particulier pour un besoin d'accessibilité. Les textes rédigés par l'assistant sont signalés et à vérifier.</p>
</main></body></html>'''

NOTFOUND = '''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Page introuvable | Alentours</title><meta name="robots" content="noindex">
<style>%(fonts)s body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f8f7f2;color:#1e352b;font:17px/1.6 "Hanken Grotesk",system-ui,sans-serif;text-align:center;padding:20px}
h1{font:600 clamp(2.6rem,8vw,4.4rem)/1 "Cormorant Garamond",Georgia,serif;margin:0 0 10px}a{display:inline-block;margin-top:14px;background:#2c6b56;color:#fff;padding:12px 24px;border-radius:14px;text-decoration:none;font-weight:700}</style></head>
<body><main><h1>Ce chemin n'existe pas</h1><p>La page demandée est introuvable, mais il y a plein de sorties autour de vous.</p><a href="%(base)s/">Retour à Alentours</a></main></body></html>'''

MANIFEST = {'name': 'Alentours', 'short_name': 'Alentours', 'description': 'Que faire autour de vous : événements, patrimoine et balades dans un rayon de 20 km.',
            'lang': 'fr', 'start_url': BASE + '/', 'scope': BASE + '/', 'display': 'standalone', 'background_color': '#f8f7f2', 'theme_color': '#2c6b56',
            'icons': [{'src': BASE + '/assets/favicon.svg', 'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any'}]}

# ------------------------------------------------------------------ construction
def main():
    frag = open(os.path.join(HERE, 'page.html'), encoding='utf-8').read()
    frag = re.sub(r'<title>.*?</title>\s*', '', frag, count=1)
    frag = re.sub(r'<link rel="(?:preconnect|stylesheet)"[^>]*(?:fonts\.googleapis|fonts\.gstatic)[^>]*>\s*', '', frag)
    assert 'fonts.googleapis' not in frag, 'Le lien Google Fonts doit être retiré (RGPD).'
    # pied de page : confidentialité + crédit Khertyx
    frag = frag.replace('Vérifiez horaires et tarifs auprès de l’organisateur.</div></footer>',
        f'Vérifiez horaires et tarifs auprès de l’organisateur.<br><a href="{BASE}/mentions-legales/">Confidentialité et mentions légales</a> · Une réalisation <a href="https://www.khertyx.com">Khertyx</a>, agence d’automatisation et d’IA en Bretagne.</div></footer>', 1)
    communes = json.load(open(os.path.join(HERE, 'communes.json'), encoding='utf-8'))
    if os.environ.get('REUSE') != '1' and os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True)
    for d in ('fonts', 'assets'):
        shutil.copytree(os.path.join(HERE, d), os.path.join(OUT, d), dirs_exist_ok=True)
    # Événements DATAtourisme (si la clé est disponible dans le secret DATATOURISME_KEY)
    sys.path.insert(0, os.path.join(HERE, 'tools'))
    try:
        import fetch_datatourisme
        fetch_datatourisme.run(OUT)
    except Exception as x:
        print('DATAtourisme KO', type(x).__name__, str(x)[:200])
    s, e = weekend()
    urls = [SITE + '/', SITE + '/mentions-legales/']

    def nav(prefix):
        return ('<nav class="wrap" aria-label="Autres communes" style="padding-block:20px"><h4 class="lbl">Que faire ailleurs ?</h4><div class="chips">' +
                ''.join(f'<a class="chip" style="text-decoration:none;color:inherit" href="{prefix}{slug(c[0])}/">{E(c[0])}</a>' for c in communes) + '</div></nav>')

    def write(path, content):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f: f.write(content)

    idx = frag.replace('<footer>', nav(BASE + '/commune/') + '<footer>', 1)
    site_ld = ('<script type="application/ld+json">' + json.dumps({'@context': 'https://schema.org', '@type': 'WebApplication', 'name': 'Alentours', 'url': SITE + '/', 'applicationCategory': 'TravelApplication',
               'inLanguage': 'fr', 'description': "Événements, patrimoine et balades dans un rayon de 20 km.", 'offers': {'@type': 'Offer', 'price': '0', 'priceCurrency': 'EUR'},
               'publisher': {'@type': 'Organization', 'name': 'Khertyx', 'url': 'https://www.khertyx.com'}}, ensure_ascii=False) + '</script>')
    write(os.path.join(OUT, 'index.html'), head('Alentours, que faire autour de vous ?', "Événements, balades, musées et patrimoine dans un rayon de 20 km, aujourd'hui ou ce week-end. Gratuit, sans inscription, sans cookie.", SITE + '/', site_ld) + idx + '</body></html>')

    for name, lat, lon, dept in communes:
        sl = slug(name); url = f'{SITE}/commune/{sl}/'
        old = os.path.join(OUT, 'commune', sl, 'index.html')
        reuse = None
        if os.environ.get('REUSE') == '1' and os.path.exists(old):
            prev = open(old, encoding='utf-8').read()
            m1 = re.search(r'<div id="intro">(.*?)</div>\s*</main>', prev, re.S)
            m2 = re.search(r'<script type="application/ld\+json">.*?</script>', prev, re.S)
            reuse = (m1.group(1) if m1 else prerender(name, dept, [], [], s, e), m2.group(0) if m2 else jsonld(name, url, []))
        ev, her = [], []
        if not reuse:
            try: ev = events(lat, lon, s, e)
            except Exception as x: print('événements KO', name, x)
            try: her = heritage(lat, lon)
            except Exception as x: print('patrimoine KO', name, x)
            time.sleep(1.0)
        pg = frag.replace('<h1 id="h1">Que faire <em>autour de vous</em> ?</h1>', f'<h1 id="h1">Que faire <em>à {E(name)}</em> et alentours ?</h1>', 1)
        pg = pg.replace('<div id="intro"></div>', '<div id="intro">' + (reuse[0] if reuse else prerender(name, dept, ev, her, s, e)) + '</div>', 1)
        pg = pg.replace('<footer>', nav('../') + '<footer>', 1)
        preset = '<script>window.ALENTOURS_PRESET=' + json.dumps({'name': name, 'lat': lat, 'lon': lon, 'ctx': dept, 'when': 'weekend'}, ensure_ascii=False) + ';</script>'
        title = f'Que faire à {name} ce week-end ? Sorties, patrimoine, balades'
        desc = f'Événements, balades et patrimoine à {name} et dans un rayon de 20 km. Programme du week-end, histoire des lieux et parcours du jour.'
        write(old, head(title, desc, url, reuse[1] if reuse else jsonld(name, url, ev)) + preset + pg + '</body></html>')
        urls.append(url); print('ok', name, len(ev), 'événements', len(her), 'sites')

    write(os.path.join(OUT, 'mentions-legales', 'index.html'), LEGAL % {'site': SITE, 'base': BASE, 'fonts': FONTS_CSS.replace('%', '%%'), 'date': datetime.date.today().strftime('%d/%m/%Y')})
    write(os.path.join(OUT, '404.html'), NOTFOUND % {'fonts': FONTS_CSS.replace('%', '%%'), 'base': BASE})
    write(os.path.join(OUT, 'manifest.webmanifest'), json.dumps(MANIFEST, ensure_ascii=False, indent=2))
    write(os.path.join(OUT, '.nojekyll'), '')
    if not HOST.endswith('github.io'):
        write(os.path.join(OUT, 'CNAME'), HOST + '\n')      # domaine personnalisé GitHub Pages
    lm = datetime.date.today().isoformat()
    write(os.path.join(OUT, 'sitemap.xml'), '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(f'<url><loc>{u}</loc><lastmod>{lm}</lastmod></url>' for u in urls) + '</urlset>')
    write(os.path.join(OUT, 'robots.txt'), f'User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n')
    print(len(urls), 'pages dans', OUT, '| SITE_URL =', SITE)

if __name__ == '__main__':
    main()
