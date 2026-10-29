# Формы M3E: порт shapes.js с rooni.dev. Все формы сэмплятся в N радиусов по кругу,
# поэтому любые две можно морфить друг в друга одной SMIL-анимацией атрибута d.
import math

N = 180
TAU = math.pi * 2


def _norm(x, y):
    l = math.hypot(x, y) or 1
    return x / l, y / l


def _rounded(verts):
    n = len(verts)
    corners = []
    for i, (vx, vy, vr) in enumerate(verts):
        px, py, _ = verts[(i - 1) % n]
        qx, qy, _ = verts[(i + 1) % n]
        u1 = _norm(px - vx, py - vy)
        u2 = _norm(qx - vx, qy - vy)
        cos = min(1, max(-1, u1[0] * u2[0] + u1[1] * u2[1]))
        alpha = math.acos(cos)
        d = vr / math.tan(alpha / 2) if vr > 0 and 1e-3 < alpha < math.pi - 1e-3 else 0
        corners.append((vx, vy, u1, u2, alpha, d))

    f = [1.0] * n
    for i in range(n):
        j = (i + 1) % n
        length = math.hypot(verts[j][0] - verts[i][0], verts[j][1] - verts[i][1])
        total = corners[i][5] + corners[j][5]
        if total > length and total > 0:
            k = length / total
            f[i] = min(f[i], k)
            f[j] = min(f[j], k)

    pts = []
    for i, (vx, vy, u1, u2, alpha, d) in enumerate(corners):
        d *= f[i]
        if d < 1e-6:
            pts.append((vx, vy))
            continue
        r = d * math.tan(alpha / 2)
        A = (vx + u1[0] * d, vy + u1[1] * d)
        B = (vx + u2[0] * d, vy + u2[1] * d)
        k = 4 / 3 * math.tan((math.pi - alpha) / 4) * r
        c1 = (A[0] - u1[0] * k, A[1] - u1[1] * k)
        c2 = (B[0] - u2[0] * k, B[1] - u2[1] * k)
        for s in range(15):
            t = s / 14
            m = 1 - t
            pts.append((
                m ** 3 * A[0] + 3 * m * m * t * c1[0] + 3 * m * t * t * c2[0] + t ** 3 * B[0],
                m ** 3 * A[1] + 3 * m * m * t * c1[1] + 3 * m * t * t * c2[1] + t ** 3 * B[1],
            ))
    return pts


def _star(num, inner, rounding, rot_deg=0):
    rot = math.radians(rot_deg)
    out = []
    for i in range(num * 2):
        a = rot + i * math.pi / num
        rad = 1 if i % 2 == 0 else inner
        out.append((rad * math.cos(a), rad * math.sin(a), rounding))
    return out


def _custom(base, reps, mirror):
    rel = [(x - 0.5, y - 0.5, r) for x, y, r in base]

    def rotate(p, a):
        return (p[0] * math.cos(a) - p[1] * math.sin(a), p[0] * math.sin(a) + p[1] * math.cos(a), p[2])

    out = []
    if not mirror:
        for k in range(reps):
            out += [rotate(p, k * TAU / reps) for p in rel]
        return out
    s = math.pi / reps
    axis = math.atan2(rel[0][1], rel[0][0]) + s
    for k in range(reps * 2):
        if k % 2 == 0:
            out += [rotate(p, k * s) for p in rel]
        else:
            for p in reversed(rel):
                th = math.atan2(p[1], p[0])
                rad = math.hypot(p[0], p[1])
                m = 2 * axis - th
                out.append(rotate((rad * math.cos(m), rad * math.sin(m), p[2]), (k - 1) * s))
    return out


DEFS = {
    "circle": lambda: [(math.cos(i * TAU / 64), math.sin(i * TAU / 64), 0) for i in range(64)],
    "sunny": lambda: _star(8, 0.8, 0.15),
    "cookie7": lambda: _star(7, 0.75, 0.5, -90),
    "cookie9": lambda: _star(9, 0.8, 0.5, -90),
    "cookie12": lambda: _star(12, 0.8, 0.5, -90),
    "cookie4": lambda: _custom([(1.237, 1.236, 0.258), (0.5, 0.918, 0.233)], 4, False),
    "cookie6": lambda: _custom([(0.723, 0.884, 0.394), (0.5, 1.099, 0.398)], 6, False),
    "clover4": lambda: _custom([(0.5, 0.074, 0), (0.725, -0.099, 0.476)], 4, True),
    "clover8": lambda: _custom([(0.5, 0.036, 0), (0.758, -0.101, 0.209)], 8, False),
    "burst": lambda: _custom([(0.5, -0.006, 0.006), (0.592, 0.158, 0.006)], 12, False),
    "softburst": lambda: _custom([(0.193, 0.277, 0.053), (0.176, 0.055, 0.053)], 10, False),
    "flower": lambda: _custom([(0.37, 0.187, 0), (0.416, 0.049, 0.381), (0.479, 0.001, 0.095)], 8, True),
}

_cache = {}


def radii(name):
    if name in _cache:
        return _cache[name]
    poly = _rounded(DEFS[name]())
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    r = []
    for k in range(N):
        dx, dy = math.cos(k * TAU / N), math.sin(k * TAU / N)
        best = 0
        for i in range(len(poly)):
            A, B = poly[i], poly[(i + 1) % len(poly)]
            ax, ay = A[0] - cx, A[1] - cy
            ex, ey = B[0] - A[0], B[1] - A[1]
            den = dx * ey - dy * ex
            if abs(den) < 1e-12:
                continue
            t = (ax * ey - ay * ex) / den
            u = (ax * dy - ay * dx) / den
            if t > 0 and -1e-9 <= u <= 1 + 1e-9 and t > best:
                best = t
        r.append(best)
    top = max(r)
    _cache[name] = [v / top * 0.5 for v in r]
    return _cache[name]


def blend(a, b, t, x, y, size, phi=0.0):
    # Промежуточная форма между a и b: t > 1 даёт перелёт как у пружины
    ra, rb = radii(a), radii(b)
    out = []
    for k in range(N):
        rk = ra[k] + (rb[k] - ra[k]) * t
        ang = k * TAU / N + phi
        out.append(f"{'L' if k else 'M'}{x + size * (0.5 + rk * math.cos(ang)):.2f} "
                   f"{y + size * (0.5 + rk * math.sin(ang)):.2f}")
    return "".join(out) + "Z"
