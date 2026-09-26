"""Sonde DATAtourisme : affiche la structure réelle des événements (aucune clé affichée)."""
import json, os, urllib.request, urllib.parse, datetime
KEY = os.environ['DATATOURISME_KEY']
BASE = 'https://api.datatourisme.fr/v1/'
def get(path, **q):
    url = BASE + path + '?' + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={'X-API-Key': KEY, 'User-Agent': 'Alentours/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:600]
def shape(o, d=0, maxd=5):
    if d > maxd: return '…'
    if isinstance(o, dict): return {k: shape(v, d+1, maxd) for k, v in list(o.items())[:40]}
    if isinstance(o, list): return [shape(o[0], d+1, maxd)] if o else []
    return type(o).__name__ + ':' + str(o)[:60]
today = datetime.date.today().isoformat()
print('== défaut, 20 km Rennes')
st, d = get('entertainmentAndEvent', geo_distance='48.1173,-1.6778,20km', page_size=2)
print(st, json.dumps(d.get('meta') if isinstance(d, dict) else d, ensure_ascii=False))
if isinstance(d, dict) and d.get('objects'):
    print(json.dumps(shape(d['objects'][0]), ensure_ascii=False, indent=1)[:9000])
print('== tous champs')
st, d = get('entertainmentAndEvent', geo_distance='48.1173,-1.6778,20km', page_size=1, fields='uuid,label,type,takesPlaceAt,offers,isLocatedAt,hasTheme,hasAudience,hasFeature,hasMainRepresentation,hasBeenCreatedBy,hasDescription,hasContact,reducedMobilityAccess,isAccessibleForFree')
print(st)
if isinstance(d, dict) and d.get('objects'):
    print(json.dumps(shape(d['objects'][0], maxd=7), ensure_ascii=False, indent=1)[:12000])
else: print(d)
for f in ['takesPlaceAt.endDate[gte]=' + today, 'takesPlaceAt.startDate[gte]=' + today]:
    st, d = get('entertainmentAndEvent', geo_distance='48.1173,-1.6778,20km', page_size=1, filters=f)
    print('== filtre', f, st, (d.get('meta') if isinstance(d, dict) else d))
st, d = get('entertainmentAndEvent', page_size=1, filters='isLocatedAt.address.hasAddressCity.isPartOfDepartment.insee[eq]=35')
print('== dept 35', st, d.get('meta') if isinstance(d, dict) else d)
st, d = get('entertainmentAndEvent', page_size=1)
print('== France', st, d.get('meta') if isinstance(d, dict) else d)
