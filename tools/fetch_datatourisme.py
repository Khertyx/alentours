#!/usr/bin/env python3
"""Récupère de DATAtourisme (licence Etalab), rangés par département :
- les événements à venir : <out>/data/events/<dept>.json + index.json
- les lieux de visite référencés par les offices de tourisme : <out>/data/places/<dept>.json + index.json
  (sites culturels, patrimoine, musées, parcs, points de vue… : des lieux ouverts au public, vérifiés par les offices).
  Les lieux changent peu : une partie des départements est rafraîchie à chaque passage, le reste est repris du site en ligne.
La clé API est lue dans DATATOURISME_KEY (secret GitHub) et n'est jamais écrite ni affichée.
Quota API : 1000 requêtes/heure. Le script s'arrête proprement à MAX_REQ requêtes.
"""
import json, os, re, sys, time, datetime, threading, urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

API = 'https://api.datatourisme.fr/v1/entertainmentAndEvent'
API_P = 'https://api.datatourisme.fr/v1/placeOfInterest'
MAX_REQ = int(os.environ.get('DT_MAX_REQ', '900'))          # total des requêtes de ce passage (quota 1000/h)
PLACES_REQ = int(os.environ.get('DT_PLACES_REQ', '150'))    # part réservée aux lieux
PTYPES = ['CulturalSite', 'NaturalHeritage', 'ParkAndGarden', 'Park', 'Museum', 'InterpretationCentre', 'Castle', 'Church', 'ReligiousSite',
          'RemarkableBuilding', 'PointOfView', 'ArcheologicalSite', 'Abbey', 'Basilica', 'ZooAnimalPark', 'ThemePark', 'TeachingFarm']
PFIELDS = 'uuid,label,type,isLocatedAt,hasDescription,hasContact,hasBeenCreatedBy,offers,lastUpdate'
HORIZON = int(os.environ.get('DT_HORIZON_DAYS', '60'))
FIRST = ['35', '22', '29', '56', '44', '53', '50', '49', '14', '61', '72', '85', '37', '75', '69', '13', '33', '31', '06', '67', '59', '74']
DEPTS = FIRST + [d for d in [f'{i:02d}' for i in range(1, 96) if i != 20] + ['2A', '2B', '971', '972', '973', '974', '976'] if d not in FIRST]
BUDGET_S = int(os.environ.get('DT_BUDGET_SECONDS', '1080'))   # 18 min maximum
WORKERS = int(os.environ.get('DT_WORKERS', '6'))
PREV = os.environ.get('SITE_URL', '').rstrip('/')              # site en ligne : données de la veille en secours
lock = threading.Lock()
FIELDS = 'uuid,label,takesPlaceAt,offers,isLocatedAt,hasDescription,hasMainRepresentation,hasBeenCreatedBy,hasContact,lastUpdate'
IMG = re.compile(r'^https?://\S+\.(?:jpe?g|png|webp|gif)(?:\?\S*)?$', re.I)
nreq = 0

def get(params, key, api=API):
    global nreq
    if time.time() > DEADLINE: raise TimeoutError('budget')
    url = api + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'X-API-Key': key, 'User-Agent': 'Alentours/1.0 (contact@khertyx.com)'})
    for essai in range(4):
        with lock: nreq += 1
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and essai < 3:
                time.sleep(5 * (essai + 1)); continue
            raise
        except urllib.error.URLError:
            if essai < 3: time.sleep(5); continue
            raise

def fr(v):
    """Texte français d'un champ multilingue ({'@fr': ...} ou liste)."""
    if isinstance(v, list): v = v[0] if v else None
    if isinstance(v, dict): v = v.get('@fr') or v.get('@en') or next(iter(v.values()), '')
    if isinstance(v, list): v = v[0] if v else ''
    return (v or '').strip() if isinstance(v, str) else ''

def first(v):
    return (v[0] if v else {}) if isinstance(v, list) else (v or {})

URLRX = re.compile(r'^https?://\S+$')
def find_image(o, key=''):
    """Première image trouvée : URL finissant par une extension d'image, sinon URL rangée sous une clé « locator »/« url »."""
    best = _find(o, strict=True)
    return best or _find(o, strict=False)
def _find(o, strict, key=''):
    if isinstance(o, str):
        if IMG.match(o): return o
        if not strict and URLRX.match(o) and re.search(r'locator|url|file', key, re.I) and not re.search(r'licen|creativecommons|rights', o, re.I): return o
        return ''
    if isinstance(o, dict):
        for k, v in o.items():
            r = _find(v, strict, k)
            if r: return r
    if isinstance(o, list):
        for v in o:
            r = _find(v, strict, key)
            if r: return r
    return ''
def compact(o):
    loc = first(o.get('isLocatedAt'))
    geo = loc.get('geo') or {}
    try: lat, lon = float(geo.get('latitude')), float(geo.get('longitude'))
    except (TypeError, ValueError):
        gp = loc.get('geoPoint') or {}
        try: lat, lon = float(gp.get('lat')), float(gp.get('lon'))
        except (TypeError, ValueError): return None
    addr = first(loc.get('address'))
    city = addr.get('addressLocality') or fr((addr.get('hasAddressCity') or {}).get('label'))
    dates = [(d.get('startDate') or '', d.get('endDate') or d.get('startDate') or '', d.get('startTime') or '') for d in (o.get('takesPlaceAt') or []) if d.get('startDate')]
    if not dates: return None
    dates.sort()
    desc = re.sub(r'\s+', ' ', fr(first(o.get('hasDescription')).get('shortDescription')) or fr(first(o.get('hasDescription')).get('description')))
    price = fr(first(o.get('offers')).get('textPriceSpecification'))
    contact = first(o.get('hasContact'))
    home = contact.get('homepage')
    home = (home[0] if isinstance(home, list) and home else home) or ''
    return {
        'id': o.get('uuid'), 't': fr(o.get('label')), 'd': desc[:260],
        'dt': [[s, e, h[:5]] for s, e, h in dates[:40]],
        'la': round(lat, 5), 'lo': round(lon, 5), 'c': city,
        'p': price[:120], 'i': find_image(o.get('hasMainRepresentation')),
        'u': home if isinstance(home, str) and home.startswith('http') else '',
        'by': (o.get('hasBeenCreatedBy') or {}).get('legalName', ''), 'm': (o.get('lastUpdate') or '')[:10],
    }

DEADLINE = 0

def fetch_dept(dep, key, today, until):
    flt = (f'takesPlaceAt.endDate[gte]={today} AND takesPlaceAt.startDate[lte]={until} '
           f'AND isLocatedAt.address.hasAddressCity.isPartOfDepartment.insee[eq]={dep}')
    items, page, pages = [], 1, 1
    while page <= pages:
        if nreq >= MAX_REQ: raise TimeoutError('quota')
        d = get({'filters': flt, 'fields': FIELDS, 'page_size': 100, 'page': page, 'lang': 'fr'}, key)
        pages = (d.get('meta') or {}).get('total_pages') or 1
        for o in d.get('objects') or []:
            c = compact(o)
            if c and c['t']: items.append(c)
        page += 1
    return dedupe(items)

def dedupe(items):
    """Fusionne les fiches identiques (même titre, même lieu) saisies plusieurs fois : dates réunies."""
    out = {}
    for x in items:
        k = (re.sub(r'[^a-z0-9]', '', x['t'].lower())[:50], round(x['la'], 2), round(x['lo'], 2))
        if k in out:
            o = out[k]
            o['dt'] = sorted({tuple(d) for d in o['dt'] + x['dt']})[:40]
            o['dt'] = [list(d) for d in o['dt']]
            for f in ('i', 'u', 'd', 'p'):
                if not o.get(f) and x.get(f): o[f] = x[f]
        else:
            out[k] = x
    return list(out.values())

def previous(dep, kind='events'):
    if not PREV: return None
    try:
        with urllib.request.urlopen(urllib.request.Request(f'{PREV}/data/{kind}/{dep}.json', headers={'User-Agent': 'Alentours'}), timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

# ---------- Lieux de visite ----------
def ptypes(o):
    out = []
    for t in o.get('type') or []:
        t = str(t).split(':')[-1].split('/')[-1].split('#')[-1]
        if t in PTYPES and t not in out: out.append(t)
    return out

def compact_place(o):
    loc = first(o.get('isLocatedAt'))
    geo = loc.get('geo') or {}
    try: lat, lon = float(geo.get('latitude')), float(geo.get('longitude'))
    except (TypeError, ValueError): return None
    addr = first(loc.get('address'))
    city = addr.get('addressLocality') or fr((addr.get('hasAddressCity') or {}).get('label'))
    hd = first(o.get('hasDescription'))
    desc = re.sub(r'\s+', ' ', fr(hd.get('shortDescription')) or fr(hd.get('description')))
    contact = first(o.get('hasContact'))
    home = contact.get('homepage')
    home = (home[0] if isinstance(home, list) and home else home) or ''
    t = fr(o.get('label'))
    if not t: return None
    return {'id': o.get('uuid'), 't': t, 'k': ptypes(o), 'la': round(lat, 5), 'lo': round(lon, 5), 'c': city, 'd': desc[:240],
            'p': fr(first(o.get('offers')).get('textPriceSpecification'))[:100],
            'u': home if isinstance(home, str) and home.startswith('http') else '',
            'by': (o.get('hasBeenCreatedBy') or {}).get('legalName', ''), 'm': (o.get('lastUpdate') or '')[:10]}

def pnorm(t):
    t = re.sub(r"[^a-z0-9 ]", ' ', t.lower().translate(str.maketrans('àâäéèêëîïôöùûüç', 'aaaeeeeiioouuuc')))
    return ' '.join(w for w in t.split() if w not in {'le', 'la', 'les', 'de', 'du', 'des', 'd', 'l', 'et', 'a', 'au', 'aux', 'en'})

def dedupe_places(items):
    """Même lieu saisi par deux offices : même nom (sans articles) à moins de 300 m -> une seule fiche, la plus complète."""
    out = []
    for x in sorted(items, key=lambda x: -(len(x['d']) + (40 if x['u'] else 0))):
        n = pnorm(x['t'])
        if any(abs(o['la'] - x['la']) < .003 and abs(o['lo'] - x['lo']) < .004 and (pnorm(o['t']) == n or pnorm(o['t']) in n or n in pnorm(o['t'])) for o in out):
            continue
        out.append(x)
    return out

def fetch_places_dept(dep, key, budget):
    flt = f'type[in]={",".join(PTYPES)} AND isLocatedAt.address.hasAddressCity.isPartOfDepartment.insee[eq]={dep}'
    items, page, pages = [], 1, 1
    while page <= pages:
        with lock:
            if budget['left'] <= 0: raise TimeoutError('quota lieux')
            budget['left'] -= 1
        d = get({'filters': flt, 'fields': PFIELDS, 'page_size': 100, 'page': page, 'lang': 'fr'}, key, API_P)
        pages = (d.get('meta') or {}).get('total_pages') or 1
        for o in d.get('objects') or []:
            c = compact_place(o)
            if c: items.append(c)
        page += 1
    return dedupe_places(items)

def run_places(out_dir, key, today):
    dest = os.path.join(out_dir, 'data', 'places'); os.makedirs(dest, exist_ok=True)
    prev = {}
    try:
        with urllib.request.urlopen(urllib.request.Request(f'{PREV}/data/places/index.json', headers={'User-Agent': 'Alentours'}), timeout=20) as r:
            prev = json.loads(r.read().decode()).get('depts', {})
    except Exception:
        pass
    # Ordre : départements jamais récupérés (Bretagne d'abord), puis les plus anciens
    missing = [d for d in DEPTS if d not in prev]
    stale = sorted([d for d in DEPTS if d in prev], key=lambda d: prev[d].get('u', ''))
    order = missing + stale
    budget = {'left': PLACES_REQ}
    results, fresh = {}, set()
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(fetch_places_dept, d, key, budget): d for d in order}
        for f in as_completed(futs):
            dep = futs[f]
            try:
                results[dep] = f.result(); fresh.add(dep)
            except Exception:
                pass
    reused = 0
    for dep in DEPTS:
        if dep in results or dep not in prev: continue
        old = previous(dep, 'places')
        if old is not None: results[dep] = old; reused += 1
    index = {'updated': today.isoformat(), 'source': 'DATAtourisme (Licence Ouverte Etalab)', 'depts': {}}
    total = 0
    for dep, items in results.items():
        if not items: continue
        with open(os.path.join(dest, f'{dep}.json'), 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, separators=(',', ':'))
        lats = [x['la'] for x in items]; lons = [x['lo'] for x in items]
        index['depts'][dep] = {'n': len(items), 'b': [min(lats), min(lons), max(lats), max(lons)],
                               'u': today.isoformat() if dep in fresh else prev.get(dep, {}).get('u', '')}
        total += len(items)
    with open(os.path.join(dest, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, separators=(',', ':'))
    print(f'DATAtourisme lieux : {total} lieux, {len(index["depts"])} départements ({len(fresh)} rafraîchis, {reused} repris), {PLACES_REQ - budget["left"]} requêtes', flush=True)

def run(out_dir):
    global DEADLINE
    key = os.environ.get('DATATOURISME_KEY', '').strip()
    if not key:
        print('DATAtourisme : pas de clé, étape ignorée', flush=True); return
    DEADLINE = time.time() + BUDGET_S
    today = (datetime.datetime.utcnow() + datetime.timedelta(hours=2)).date()
    until = today + datetime.timedelta(days=HORIZON)
    try:
        run_places(out_dir, key, today)
    except Exception as e:
        print('DATAtourisme lieux : échec', type(e).__name__, str(e)[:120], flush=True)
    dest = os.path.join(out_dir, 'data', 'events'); os.makedirs(dest, exist_ok=True)
    index = {'updated': today.isoformat(), 'horizon': until.isoformat(), 'source': 'DATAtourisme (Licence Ouverte Etalab)', 'depts': {}}
    # Ordre : Bretagne et grandes villes, puis les départements absents hier, puis les autres (tout le pays couvert en 2 nuits)
    order = list(DEPTS)
    try:
        with urllib.request.urlopen(urllib.request.Request(f'{PREV}/data/events/index.json', headers={'User-Agent': 'Alentours'}), timeout=20) as r:
            had = set(json.loads(r.read().decode()).get('depts', {}))
        missing = [d for d in DEPTS if d not in FIRST and d not in had]
        order = FIRST + missing + [d for d in DEPTS if d not in FIRST and d not in missing]
    except Exception:
        pass
    results, fresh, reused = {}, 0, 0
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(fetch_dept, d, key, today, until): d for d in order}
        for f in as_completed(futs):
            dep = futs[f]
            try:
                results[dep] = f.result(); fresh += 1
            except Exception as e:
                old = previous(dep)
                if old is not None:
                    results[dep] = [x for x in old if any((dd[1] or dd[0]) >= today.isoformat() for dd in x.get('dt', []))]; reused += 1
                print('Département', dep, ':', type(e).__name__, str(e)[:80], '| secours veille' if old is not None else '', flush=True)
    total = 0
    for dep, items in results.items():
        if not items: continue
        with open(os.path.join(dest, f'{dep}.json'), 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, separators=(',', ':'))
        lats = [x['la'] for x in items]; lons = [x['lo'] for x in items]
        index['depts'][dep] = {'n': len(items), 'b': [min(lats), min(lons), max(lats), max(lons)]}
        total += len(items)
    with open(os.path.join(dest, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, separators=(',', ':'))
    print(f'DATAtourisme : {total} événements, {len(index["depts"])} départements ({fresh} à jour, {reused} repris de la veille), {nreq} requêtes', flush=True)

if __name__ == '__main__':
    run(sys.argv[1] if len(sys.argv) > 1 else 'dist')
