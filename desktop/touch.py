"""Pure touch calibration and hit testing; no Windows API or serial effects."""
import math

TARGETS = [(28, 28), (292, 28), (28, 212), (292, 212)]
HIT_RECTS = {"previous": (10, 178, 102, 234), "play_pause": (114, 178, 206, 234),
             "next": (218, 178, 310, 234)}


def validate_calibration(coefficients):
    if not isinstance(coefficients, list) or len(coefficients) != 6:
        raise ValueError("Altı kalibrasyon katsayısı gerekli.")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in coefficients):
        raise ValueError("Geçersiz kalibrasyon katsayısı.")
    a, b, c, d, e, f = coefficients
    if abs(a*e-b*d) < 1e-5 or max(abs(a),abs(b),abs(d),abs(e)) > 2 or abs(c)>5000 or abs(f)>5000:
        raise ValueError("Kalibrasyon ölçeği geçersiz.")
    return [float(v) for v in coefficients]


def fit_calibration(raw):
    if len(raw) != 3:
        raise ValueError("Üç farklı hedef ölçümü gerekli.")
    x1,y1 = raw[0]; x2,y2 = raw[1]; x3,y3 = raw[2]
    determinant = (x2-x1)*(y3-y1)-(x3-x1)*(y2-y1)
    if abs(determinant) < 100000:
        raise ValueError("Hedefler ayırt edilemedi. Yeniden deneyin.")
    def axis(v1,v2,v3):
        a = ((v2-v1)*(y3-y1)-(v3-v1)*(y2-y1))/determinant
        b = ((x2-x1)*(v3-v1)-(x3-x1)*(v2-v1))/determinant
        return [a,b,v1-a*x1-b*y1]
    return validate_calibration(axis(28,292,28)+axis(28,28,212))


def position(coefficients, raw_x, raw_y):
    a,b,c,d,e,f = coefficients
    return a*raw_x+b*raw_y+c, d*raw_x+e*raw_y+f


def hit_test(x, y):
    if not (0 <= x < 320 and 0 <= y < 240):
        return None
    for action, (left,top,right,bottom) in HIT_RECTS.items():
        if left <= x < right and top <= y < bottom:
            return action
    return None


def verify_corner(coefficients, raw):
    x,y = position(coefficients, *raw)
    return math.hypot(x-TARGETS[3][0], y-TARGETS[3][1]) <= 18
