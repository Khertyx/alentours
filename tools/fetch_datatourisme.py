#!/usr/bin/env python3
"""Récupère les événements à venir de DATAtourisme (licence Etalab) et les range par département.

Sortie : <out>/data/events/<dept>.json et <out>/data/events/index.json
La clé API est lue dans DATATOURISME_KEY (secret GitHub) et n'est jamais écrite ni affichée.
Quota API : 1000 requêtes/heure. Le script s'arrête proprement à MAX_REQ requêtes.
"""
import json, os, re, sys, time, datetime, threading, urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

API = 'https://api.datatourisme.fr/v1/entertainmentAndEvent'
MAX_REQ = int(os.environ.get('DT_MAX_REQ', '850'))
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

def get(params, key):
    global nreq
    if time.time() > DEADLINE: raise TimeoutError('budget')
    url = API + '?' + urllib.parse.urlencode(params)
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

def find_image(o):
    if isinstance(o, str): return o if IMG.match(o) else ''
    if isinstance(o, dict):
        for k, v in o.items():
            r = find_image(v)
            if r: return r
    if isinstance(o, list):
        for v in o:
            r = find_image(v)
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
    return items

def previous(dep):
    if not PREV: return None
    try:
        with urllib.request.urlopen(urllib.request.Request(f'{PREV}/data/events/{dep}.json', headers={'User-Agent': 'Alentours'}), timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

def run(out_dir):
    global DEADLINE
    key = os.environ.get('DATATOURISME_KEY', '').strip()
    if not key:
        print('DATAtourisme : pas de clé, étape ignorée', flush=True); return
    DEADLINE = time.time() + BUDGET_S
    today = (datetime.datetime.utcnow() + datetime.timedelta(hours=2)).date()
    until = today + datetime.timedelta(days=HORIZON)
    dest = os.path.join(out_dir, 'data', 'events'); os.makedirs(dest, exist_ok=True)
    index = {'updated': today.isoformat(), 'horizon': until.isoformat(), 'source': 'DATAtourisme (Licence Ouverte Etalab)', 'depts': {}}
    results, fresh, reused = {}, 0, 0
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(fetch_dept, d, key, today, until): d for d in DEPTS}
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
