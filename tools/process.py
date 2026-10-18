"""Turn raw Overpass JSON (data/osm/*.json) into the compact dataset the viewer embeds.

Usage: python3 -I tools/process.py data/osm data/campus.json

Coordinates are projected to a local tangent plane centred on Hyde Park
(x = metres east, y = metres north); buildings are stored as integer decimetres,
ground, roads, rails and trees as half-metres. The Chicago address grid
(800 numbers per mile) is fitted from the centrelines of streets whose grid
numbers are known.
"""
import json, os, sys, math, re, collections
src_dir, out_p = sys.argv[1], sys.argv[2]
data_p, rels_p = os.path.join(src_dir, 'data.json'), os.path.join(src_dir, 'rels.json')
D = json.load(open(data_p)); R = json.load(open(rels_p))
rels = {e['id']: e for e in R['elements']}
els = [rels.get(e['id'], e) if e['type'] == 'relation' else e for e in D['elements']]
for e in R['elements']:
    if not any(x['type'] == 'relation' and x['id'] == e['id'] for x in D['elements']):
        els.append(e)

S, W, N, E = 41.7795, -87.6115, 41.8015, -87.5830
LAT0, LON0 = 41.7905, -87.5972
KX = 111320.0 * math.cos(math.radians(LAT0)); KN = 110574.0
def P(lat, lon): return ((lon - LON0) * KX, (lat - LAT0) * KN)
BX0, BN0 = P(S, W); BX1, BN1 = P(N, E)

def dp(pts, tol):
    if len(pts) < 3: return pts
    def rec(a, b):
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1; L = math.hypot(dx, dy) or 1e-9
        best, bi = 0, -1
        for i in range(a + 1, b):
            x, y = pts[i]
            d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / L
            if d > best: best, bi = d, i
        if best > tol: return rec(a, bi)[:-1] + rec(bi, b)
        return [pts[a], pts[b]]
    return rec(0, len(pts) - 1)

def dpring(r, tol):
    if len(r) < 4: return r
    far = max(range(len(r)), key=lambda i: (r[i][0] - r[0][0]) ** 2 + (r[i][1] - r[0][1]) ** 2)
    a = dp(r[:far + 1], tol); b = dp(r[far:] + [r[0]], tol)
    return a[:-1] + b[:-1]

def ring_from_geom(g):
    pts = [P(p['lat'], p['lon']) for p in g if p]
    if len(pts) > 1 and pts[0] == pts[-1]: pts = pts[:-1]
    return pts

def assemble(members, role):
    segs = [[(p['lat'], p['lon']) for p in m['geometry'] if p] for m in members if m.get('type') == 'way' and m.get('role', '') == role and m.get('geometry')]
    rings = []
    while segs:
        cur = segs.pop(0)
        changed = True
        while cur[0] != cur[-1] and changed:
            changed = False
            for i, s in enumerate(segs):
                if s[0] == cur[-1]: cur += s[1:]
                elif s[-1] == cur[-1]: cur += s[::-1][1:]
                elif s[-1] == cur[0]: cur = s[:-1] + cur
                elif s[0] == cur[0]: cur = s[::-1][:-1] + cur
                else: continue
                segs.pop(i); changed = True; break
        pts = [P(a, b) for a, b in cur]
        if len(pts) > 1 and pts[0] == pts[-1]: pts = pts[:-1]
        if len(pts) >= 3: rings.append(pts)
    return rings

def area(r):
    return 0.5 * sum(r[i][0] * r[(i + 1) % len(r)][1] - r[(i + 1) % len(r)][0] * r[i][1] for i in range(len(r)))

def centroid(r):
    return (sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r))

def pip(pt, ring):
    x, y = pt; ins = False; j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]; xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi: ins = not ins
        j = i
    return ins

def clip_poly(ring, x0, y0, x1, y1):
    def clip(pts, inside, inter):
        out = []
        for i in range(len(pts)):
            a, b = pts[i - 1], pts[i]
            ia, ib = inside(a), inside(b)
            if ib:
                if not ia: out.append(inter(a, b))
                out.append(b)
            elif ia: out.append(inter(a, b))
        return out
    def ix(xc):
        return lambda a, b: (xc, a[1] + (b[1] - a[1]) * (xc - a[0]) / ((b[0] - a[0]) or 1e-9))
    def iy(yc):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (yc - a[1]) / ((b[1] - a[1]) or 1e-9), yc)
    pts = ring
    for inside, inter in ((lambda p: p[0] >= x0, ix(x0)), (lambda p: p[0] <= x1, ix(x1)), (lambda p: p[1] >= y0, iy(y0)), (lambda p: p[1] <= y1, iy(y1))):
        if not pts: break
        pts = clip(pts, inside, inter)
    return pts

def flat(r, q=10):
    return [v for p in r for v in (round(p[0] * q), round(p[1] * q))]

def fnum(s):
    if s is None: return None
    m = re.match(r'\s*([0-9.]+)', str(s))
    return float(m.group(1)) if m else None

def geom_rings(e):
    if e['type'] == 'way':
        g = e.get('geometry')
        if not g: return [], []
        return [ring_from_geom(g)], []
    return assemble(e.get('members', []), 'outer'), assemble(e.get('members', []), 'inner')

# --- university boundary
uni = next(e for e in els if e['type'] == 'relation' and e['id'] == 13117436)
uni_outer = assemble(uni['members'], 'outer'); uni_inner = assemble(uni['members'], 'inner')
def in_uni(pt):
    return any(pip(pt, r) for r in uni_outer) and not any(pip(pt, r) for r in uni_inner)

# --- curated heights (metres) for named structures lacking good tags
CUR_H = {
    'Mitchell Tower': 40, 'Harper Memorial Library': 26, 'Rubenstein Forum': 50,
    'Logan Center for the Arts': 18, 'Joe and Rika Mansueto Library': 11,
    'Campus North Residential Commons': 30, 'Woodlawn Residential & Dining Commons': 36,
    'Institute for the Study of Ancient Cultures Museum': 16, 'Bond Chapel': 14,
    'Charles M. Harper Center': 22, 'Laird Bell Law Quadrangle': 16, 'Ida Noyes Hall': 17,
    'Crown Family School of Social Work, Policy, and Practice': 12, 'Frederick C. Robie House': 9,
    'Cobb Gate': 10, 'Hutchinson Commons': 18, 'Reynolds Club': 16, 'Mandel Hall': 20,
}
DEF_H = {'university': 18, 'hospital': 24, 'dormitory': 18, 'school': 12, 'church': 16, 'apartments': 14,
         'residential': 11, 'house': 9, 'detached': 9, 'semidetached_house': 9, 'terrace': 10,
         'garage': 3.5, 'garages': 3.5, 'shed': 3, 'retail': 6, 'commercial': 8, 'train_station': 6,
         'parking': 10, 'industrial': 9, 'office': 14, 'yes': 9, 'tower': 30, 'synagogue': 12, 'hotel': 30,
         'construction': 6, 'roof': 4, 'service': 4}
CAT = {'university': 'u', 'dormitory': 'd', 'hospital': 'h', 'school': 's', 'church': 'c', 'synagogue': 'c',
       'apartments': 'a', 'residential': 'r', 'house': 'r', 'detached': 'r', 'semidetached_house': 'r', 'terrace': 'r',
       'garage': 'g', 'garages': 'g', 'parking': 'g', 'retail': 'm', 'commercial': 'm', 'office': 'm', 'hotel': 'm',
       'industrial': 'i', 'train_station': 't'}

STREET_ABBR = [('South ', 'S '), ('East ', 'E '), ('North ', 'N '), ('West ', 'W '), ('Avenue', 'Ave'), ('Street', 'St'),
               ('Boulevard', 'Blvd'), ('Court', 'Ct'), ('Drive', 'Dr'), ('Place', 'Pl')]
def abbr(s):
    for a, b in STREET_ABBR: s = s.replace(a, b)
    return s

buildings = []; parts = []
addr_ns = []; addr_ew = []
for e in els:
    t = e.get('tags', {})
    isb = 'building' in t and t['building'] not in ('no',)
    ispart = 'building:part' in t and not isb
    if not (isb or ispart): continue
    if t.get('building') == 'roof': continue
    outers, inners = geom_rings(e)
    outers = [r for r in outers if len(r) >= 3]
    if not outers: continue
    lv = fnum(t.get('building:levels')); h = fnum(t.get('height')); mh = fnum(t.get('min_height'))
    minlv = fnum(t.get('building:min_level'))
    name = t.get('name')
    btype = t.get('building') or t.get('building:part')
    if h: hs = 'osm'
    elif name in CUR_H: h, hs = CUR_H[name], 'cur'
    elif lv: h, hs = lv * 3.6 + 0.6, 'lv'
    else: h, hs = DEF_H.get(btype, 9), 'def'
    if mh is None and minlv: mh = minlv * 3.6
    hn = t.get('addr:housenumber'); st = t.get('addr:street')
    for oi, o in enumerate(outers):
        if area(o) < 0: o = o[::-1]
        o = dpring(o, 0.25)
        if len(o) < 3 or abs(area(o)) < 4: continue
        holes = []
        for r in inners:
            if pip(centroid(r), o):
                if area(r) > 0: r = r[::-1]
                r = dpring(r, 0.25)
                if len(r) >= 3: holes.append(r)
        c = centroid(o)
        rec = {'id': e['id'], 'rel': e['type'] == 'relation', 'o': o, 'holes': holes, 'h': h, 'mh': mh or 0, 'hs': hs, 'lv': lv, 'name': name,
               'type': btype, 'c': c, 'part': ispart, 'addr': (hn + ' ' + abbr(st)) if hn and st else None,
               'arch': t.get('architect'), 'start': t.get('start_date'), 'op': t.get('operator', '')}
        (parts if ispart else buildings).append(rec)
    if hn and st:
        m = re.match(r'(\d+)', hn)
        if m:
            num = int(m.group(1)); c = centroid(outers[0])
            if st.startswith('South ') and 5000 <= num <= 6400: addr_ns.append((c[1], num))
            if st.startswith('East ') and 700 <= num <= 1700: addr_ew.append((c[0], num))

# parts inherit names from containing building
for p in parts:
    for b in buildings:
        if b['name'] and pip(p['c'], b['o']):
            p['name'] = p['name'] or b['name']; p['parent'] = b['id']; p['addr'] = p['addr'] or b['addr']; break

def fit(pairs):
    pairs = list(pairs)
    for _ in range(4):
        n = len(pairs); sx = sum(p[0] for p in pairs); sy = sum(p[1] for p in pairs)
        sxx = sum(p[0] ** 2 for p in pairs); sxy = sum(p[0] * p[1] for p in pairs)
        a = (n * sxy - sx * sy) / (n * sxx - sx * sx); b = (sy - a * sx) / n
        res = [abs(p[1] - (a * p[0] + b)) for p in pairs]
        lim = max(25, sorted(res)[int(len(res) * 0.85)])
        pairs = [p for p, r in zip(pairs, res) if r <= lim]
    return a, b, len(pairs)
gn = fit(addr_ns); ge = fit(addr_ew)
print('address-regression', gn, ge)
def lsq(pairs):
    n = len(pairs); sx = sum(p[0] for p in pairs); sy = sum(p[1] for p in pairs)
    sxx = sum(p[0] ** 2 for p in pairs); sxy = sum(p[0] * p[1] for p in pairs)
    a = (n * sxy - sx * sy) / (n * sxx - sx * sx); return a, (sy - a * sx) / n, n
KNOWN_E = {'South Cottage Grove Avenue': 800, 'South Drexel Avenue': 900, 'South Ellis Avenue': 1000, 'South Greenwood Avenue': 1100,
           'South Woodlawn Avenue': 1200, 'South Kimbark Avenue': 1300, 'South Dorchester Avenue': 1400, 'South Stony Island Avenue': 1600}
KNOWN_S = {'East 53rd Street': 5300, 'East 55th Street': 5500, 'East 56th Street': 5600, 'East 57th Street': 5700, 'East 58th Street': 5800,
           'East 59th Street': 5900, 'East 60th Street': 6000, 'East 61st Street': 6100, 'East 62nd Street': 6200}
_st = collections.defaultdict(list)
for e in els:
    t = e.get('tags', {})
    if e['type'] == 'way' and t.get('name') in KNOWN_E and e.get('geometry'):
        _st[t['name']] += [P(p['lat'], p['lon']) for p in e['geometry'] if 41.783 < p['lat'] < 41.796]
    if e['type'] == 'way' and t.get('name') in KNOWN_S and e.get('geometry'):
        _st[t['name']] += [P(p['lat'], p['lon']) for p in e['geometry'] if -87.606 < p['lon'] < -87.590]
pe = [(sum(p[0] for p in _st[k]) / len(_st[k]), v) for k, v in KNOWN_E.items() if _st[k]]
ps = [(sum(p[1] for p in _st[k]) / len(_st[k]), v) for k, v in KNOWN_S.items() if _st[k]]
ge = lsq(pe); gn = lsq(ps)
for x, v in pe: print('E check', v, round(ge[0] * x + ge[1]))
for y, v in ps: print('S check', v, round(gn[0] * y + gn[1]))
print('grid S fit: num = %.5f*n + %.1f (n=%d)  -> per mile %.0f' % (gn[0], gn[1], gn[2], abs(gn[0]) * 1609.34))
print('grid E fit: num = %.5f*x + %.1f (n=%d)  -> per mile %.0f' % (ge[0], ge[1], ge[2], abs(ge[0]) * 1609.34))

# university flag
for b in buildings + parts:
    u = in_uni(b['c']) or 'University of Chicago' in b['op'] or 'UChicago' in (b['name'] or '') or 'University of Chicago' in (b['name'] or '')
    if b['type'] in ('university', 'dormitory') and -1000 < b['c'][0] < 700 and -700 < b['c'][1] < 600: u = True
    if b['type'] in ('apartments', 'church', 'detached', 'house', 'synagogue') and not ('University' in b['op']): u = u and b['type'] == 'apartments' and False
    if b['name'] in ('Frederick C. Robie House', 'UChicago President\'s Mansion', 'Arthur H. Compton House', 'Quadrangle Club', 'Rockefeller Memorial Chapel', 'Faculty Apartments', 'Midway Residence Hall'): u = True
    b['u'] = bool(u)
print('buildings', len(buildings), 'parts', len(parts), 'university', sum(b['u'] for b in buildings))

# ground features
ground = []
def gcat(t):
    if t.get('natural') == 'water' or t.get('water') or t.get('leisure') == 'swimming_pool': return 'water'
    if t.get('name') == 'Midway Plaisance': return 'midway'
    if t.get('leisure') in ('pitch', 'track', 'sports_centre', 'stadium') or t.get('landuse') == 'recreation_ground': return 'pitch'
    if t.get('natural') in ('wood', 'scrub') or t.get('landuse') == 'forest': return 'wood'
    if t.get('leisure') in ('park', 'garden', 'playground', 'nature_reserve', 'dog_park') or t.get('landuse') in ('grass', 'meadow', 'village_green', 'cemetery') or t.get('natural') in ('grassland', 'heath'): return 'park'
    if t.get('natural') == 'sand' or t.get('leisure') == 'beach': return 'sand'
    return None
for e in els:
    t = e.get('tags', {})
    if 'building' in t or 'highway' in t: continue
    c = gcat(t)
    if not c: continue
    outers, inners = geom_rings(e)
    for o in outers:
        cl = clip_poly(o, BX0, BN0, BX1, BN1)
        if len(cl) < 3: continue
        cl = dpring(cl, 0.6)
        if len(cl) < 3 or abs(area(cl)) < 20: continue
        if area(cl) < 0: cl = cl[::-1]
        hs = []
        for r in inners:
            r2 = clip_poly(r, BX0, BN0, BX1, BN1)
            if len(r2) >= 3 and pip(centroid(r2), cl):
                if area(r2) > 0: r2 = r2[::-1]
                hs.append(flat(r2, 2))
        ground.append({'t': c, 'p': flat(cl, 2), 'h': hs, 'a': abs(area(cl))})
ground.sort(key=lambda g: -g['a'])
for g in ground: del g['a']
print('ground', collections.Counter(g['t'] for g in ground))

# roads
RC = {'motorway': 0, 'trunk': 0, 'primary': 0, 'secondary': 0, 'tertiary': 1, 'residential': 1, 'unclassified': 1,
      'living_street': 1, 'service': 2, 'footway': 3, 'path': 3, 'pedestrian': 3, 'cycleway': 3, 'steps': 3, 'track': 3}
roads = []; streets = collections.defaultdict(list)
def inbox(p, m=0): return BX0 - m <= p[0] <= BX1 + m and BN0 - m <= p[1] <= BN1 + m
for e in els:
    t = e.get('tags', {})
    hw = t.get('highway')
    if hw not in RC or not e.get('geometry') or e['type'] != 'way': continue
    if t.get('area') == 'yes' or t.get('footway') == 'crossing' and False: continue
    if hw == 'service' and t.get('service') in ('parking_aisle', 'drive-through'): continue
    pts = [P(p['lat'], p['lon']) for p in e['geometry']]
    pts = dp(pts, 0.4)
    # split to inside-bbox runs
    runs, cur = [], []
    for p in pts:
        if inbox(p, 30): cur.append(p)
        else:
            if len(cur) >= 2: runs.append(cur)
            cur = []
    if len(cur) >= 2: runs.append(cur)
    for r in runs:
        roads.append({'c': RC[hw], 'p': flat(r, 2)})
    if t.get('name') and RC[hw] <= 1:
        streets[t['name']].extend(pts)
print('roads', len(roads))

rail = []
for e in els:
    t = e.get('tags', {})
    if t.get('railway') in ('rail', 'light_rail', 'subway') and e.get('geometry') and t.get('service') not in ('yard', 'siding', 'spur'):
        pts = [P(p['lat'], p['lon']) for p in e['geometry']]
        pts = [p for p in pts if inbox(p, 10)]
        if len(pts) >= 2: rail.append(flat(dp(pts, 0.5), 2))
print('rail', len(rail))

trees = []
for e in els:
    t = e.get('tags', {})
    if e['type'] == 'node' and t.get('natural') == 'tree':
        x, n = P(e['lat'], e['lon']); trees += [round(x * 2), round(n * 2)]
print('trees', len(trees) // 2)

# street labels: avenues labelled at north edge of campus, streets at west
LABEL_AVE = ['South Cottage Grove Avenue', 'South Drexel Avenue', 'South Maryland Avenue', 'South Ellis Avenue', 'South University Avenue',
             'South Woodlawn Avenue', 'South Kimbark Avenue', 'South Kenwood Avenue', 'South Dorchester Avenue', 'South Blackstone Avenue',
             'South Harper Avenue', 'South Stony Island Avenue', 'South Ingleside Avenue', 'South Greenwood Avenue', 'South Lake Park Avenue']
LABEL_ST = ['East 53rd Street', 'East 54th Street', 'East 55th Street', 'East 56th Street', 'East 57th Street', 'East 58th Street', 'East 59th Street',
            'East 60th Street', 'East 61st Street', 'East 62nd Street', 'East Hyde Park Boulevard']
labels = []
anchor_n = P(41.7935, 0)[1]; anchor_x = P(0, -87.6040)[0]
for nm in LABEL_AVE:
    pts = streets.get(nm)
    if not pts: continue
    near = [p for p in pts if abs(p[1] - anchor_n) < 260]
    if not near: continue
    x = sorted(near, key=lambda p: abs(p[1] - anchor_n))[0][0]
    g = ge[0] * x + ge[1]
    labels.append({'n': abbr(nm), 'o': 'ns', 'g': int(round(g / 10) * 10), 'x': round(x, 1), 'y': round(anchor_n, 1)})
for nm in LABEL_ST:
    pts = streets.get(nm)
    if not pts: continue
    near = [p for p in pts if abs(p[0] - anchor_x) < 400]
    if not near: continue
    y = sorted(near, key=lambda p: abs(p[0] - anchor_x))[0][1]
    g = gn[0] * y + gn[1]
    labels.append({'n': abbr(nm), 'o': 'ew', 'g': int(round(g / 10) * 10), 'x': round(anchor_x, 1), 'y': round(y, 1)})
for l in labels: print('label', l)

# POIs
poi = []
for e in els:
    t = e.get('tags', {})
    if e['type'] == 'node' and t.get('name') == 'Nuclear Energy':
        x, n = P(e['lat'], e['lon']); poi.append({'k': 'cp1', 'x': round(x, 1), 'y': round(n, 1)})
x, n = P(41.7867553, -87.6076412); poi.append({'k': 'fountain', 'x': round(x, 1), 'y': round(n, 1)})

# serialize buildings
def brec(b):
    r = {'i': b['id'], 'p': flat(b['o']), 'z': round(b['h'], 1)}
    if b['holes']: r['q'] = [flat(h) for h in b['holes']]
    if b['mh']: r['m'] = round(b['mh'], 1)
    r['t'] = CAT.get(b['type'], 'y')
    if b['u']: r['u'] = 1
    if b['name']: r['n'] = b['name']
    if b['addr']: r['a'] = b['addr']
    if b['lv']: r['l'] = b['lv']
    r['s'] = b['hs']
    if b['rel']: r['r'] = 1
    if b['arch']: r['ar'] = b['arch']
    if b['start']: r['sd'] = b['start']
    if b.get('parent'): r['pa'] = b['parent']
    if b['part']: r['pt'] = 1
    return r
out = {
    'labelKnown': {abbr(k): v for k, v in list(KNOWN_E.items()) + list(KNOWN_S.items())},
    'meta': {'lat0': LAT0, 'lon0': LON0, 'kx': round(KX, 3), 'kn': KN, 'bbox': [round(BX0), round(BN0), round(BX1), round(BN1)],
             'gridS': [round(gn[0], 6), round(gn[1], 2)], 'gridE': [round(ge[0], 6), round(ge[1], 2)],
             'osm': D['osm3s']['timestamp_osm_base']},
    'b': [brec(b) for b in buildings + parts],
    'g': ground, 'r': roads, 'rail': rail, 'trees': trees, 'labels': labels, 'poi': poi,
}
s = json.dumps(out, separators=(',', ':'), ensure_ascii=False)
open(out_p, 'w').write(s)
print('json bytes', len(s))
