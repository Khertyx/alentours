"""Sonde : lieux DATAtourisme (placeOfInterest) — types, champs, volumes. Aucune clé affichée."""
import json, os, urllib.request, urllib.parse
KEY = os.environ['DATATOURISME_KEY']
def get(path, **q):
    url = 'https://api.datatourisme.fr/v1/' + path + ('?' + urllib.parse.urlencode(q) if q else '')
    req = urllib.request.Request(url, headers={'X-API-Key': KEY, 'User-Agent': 'Alentours/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e: return {'err': e.code, 'body': e.read().decode()[:300]}
def shape(o, d=0):
    if d > 6: return '…'
    if isinstance(o, dict): return {k: shape(v, d+1) for k, v in list(o.items())[:30]}
    if isinstance(o, list): return [shape(o[0], d+1)] if o else []
    return str(o)[:70]
t = get('thesaurus/PointOfInterestClass')
txt = json.dumps(t, ensure_ascii=False)
print('THESAURUS', len(txt)); print(txt[:6000])
d = get('placeOfInterest', geo_distance='47.9,-1.7,20km', page_size=100)
objs = d.get('objects', [])
print('PLACES 20km Plechatel total', (d.get('meta') or {}).get('total'))
from collections import Counter
c = Counter()
for o in objs:
    for ty in o.get('type', []): c[ty] += 1
print('TYPES', c.most_common(60))
for o in objs[:40]:
    print('-', json.dumps(o.get('label'), ensure_ascii=False)[:60], o.get('type'))
full = get('placeOfInterest', geo_distance='47.9,-1.7,20km', page_size=3, fields='uuid,label,type,isLocatedAt,hasMainRepresentation,offers,reducedMobilityAccess,hasFeature,hasTheme,hasDescription,openingHoursSpecification,isAccessibleForFree,hasBeenCreatedBy')
for o in full.get('objects', [])[:2]:
    print('FULL', json.dumps(shape(o), ensure_ascii=False)[:5000])
print('RAW MAINREP', json.dumps([o.get('hasMainRepresentation') for o in full.get('objects', [])], ensure_ascii=False)[:2500])
for f in ['type[in]=CulturalSite,NaturalHeritage,ParkAndGarden,Museum,Castle,Church,ReligiousSite,RemarkableBuilding,PointOfView,ArcheologicalSite']:
    x = get('placeOfInterest', page_size=1, filters=f + ' AND isLocatedAt.address.hasAddressCity.isPartOfDepartment.insee[eq]=35')
    print('FILTRE', f, x.get('meta') or x)
x = get('placeOfInterest', page_size=1, filters='isLocatedAt.address.hasAddressCity.isPartOfDepartment.insee[eq]=35'); print('DEPT35 all', x.get('meta'))
ev = get('entertainmentAndEvent', geo_distance='48.11,-1.68,10km', page_size=5, fields='uuid,label,hasMainRepresentation')
print('EV MAINREP', json.dumps([o.get('hasMainRepresentation') for o in ev.get('objects', [])], ensure_ascii=False)[:2000])
