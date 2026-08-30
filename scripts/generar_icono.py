#!/usr/bin/env python3
"""Genera el icono de la aplicación: taller/resources/icono.png (256x256).

Motivo: coche (silueta lateral, color crema) delante de un engranaje rojo del
taller, sobre un cuadrado redondeado oscuro cálido. Se dibuja a 4x y se reduce
para que quede suavizado.

    python scripts/generar_icono.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SS = 4
BASE = 256
W = BASE * SS
C = W / 2

ROJO = (226, 48, 41, 255)
ROJO_OSC = (170, 30, 26, 255)
CREMA = (244, 233, 216, 255)
SOMBRA_RUEDA = (150, 60, 55, 255)


def _lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _mascara_cuadrado(radio):
    m = Image.new("L", (W, W), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, W - 1, W - 1], radio, fill=255)
    return m


def fondo() -> Image.Image:
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    top, bot = (48, 52, 57), (22, 23, 25)
    col = Image.new("RGBA", (1, W))
    for y in range(W):
        col.putpixel((0, y), _lerp(top, bot, y / W) + (255,))
    radio = int(0.30 * W)
    img.paste(col.resize((W, W)), (0, 0), _mascara_cuadrado(radio))

    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, W - 1], radio, outline=(255, 255, 255, 26),
                        width=max(2, SS))
    d.rounded_rectangle([SS * 3, SS * 3, W - 1 - SS * 3, W - 1 - SS * 3],
                        radio - SS * 3, outline=(0, 0, 0, 45), width=max(1, SS))
    return img


def engranaje() -> Image.Image:
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    dientes = 9
    r_raiz, r_punta = 0.345 * W, 0.425 * W
    P = 2 * math.pi / dientes
    pts = []
    for i in range(dientes):
        b = i * P - math.pi / 2
        for frac, r in ((0.00, r_raiz), (0.32, r_raiz), (0.40, r_punta),
                        (0.60, r_punta), (0.68, r_raiz), (1.00, r_raiz)):
            a = b + frac * P
            pts.append((C + r * math.cos(a), C + r * math.sin(a)))
    d.polygon(pts, fill=ROJO)
    # borde interior algo más oscuro (profundidad) y agujero central
    rh = 0.205 * W
    d.ellipse([C - rh - 0.018 * W, C - rh - 0.018 * W,
               C + rh + 0.018 * W, C + rh + 0.018 * W], fill=ROJO_OSC)
    d.ellipse([C - rh, C - rh, C + rh, C + rh], fill=(0, 0, 0, 0))
    return img


def coche(dy=-0.035) -> Image.Image:
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def Y(f):
        return (f + dy) * W

    x = lambda f: f * W  # noqa: E731
    rw = 0.092 * W
    ejes = (0.330 * W, 0.670 * W)
    y_suelo = Y(0.695)

    # cabina (trapecio)
    d.polygon([(x(0.325), Y(0.545)), (x(0.420), Y(0.400)), (x(0.585), Y(0.400)),
               (x(0.685), Y(0.545))], fill=CREMA)
    # carrocería
    d.rounded_rectangle([x(0.130), Y(0.535), x(0.870), y_suelo],
                        radius=0.055 * W, fill=CREMA)
    # ventanillas (huecas), separadas por un montante fino
    d.polygon([(x(0.360), Y(0.532)), (x(0.437), Y(0.432)), (x(0.489), Y(0.432)),
               (x(0.489), Y(0.532))], fill=(0, 0, 0, 0))
    d.polygon([(x(0.511), Y(0.532)), (x(0.511), Y(0.432)), (x(0.560), Y(0.432)),
               (x(0.640), Y(0.532))], fill=(0, 0, 0, 0))

    # pasos de rueda (huecos) y ruedas
    for cx in ejes:
        d.ellipse([cx - rw * 1.5, y_suelo - rw * 1.5, cx + rw * 1.5, y_suelo + rw * 1.5],
                  fill=(0, 0, 0, 0))
    for cx in ejes:
        d.ellipse([cx - rw, y_suelo - rw, cx + rw, y_suelo + rw], fill=CREMA)
        d.ellipse([cx - rw * 0.42, y_suelo - rw * 0.42, cx + rw * 0.42, y_suelo + rw * 0.42],
                  fill=ROJO_OSC)
    return img


def sombra(capa, desplaza, radio, alfa):
    a = capa.split()[3].point(lambda v: min(v, alfa))
    s = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    s.paste((0, 0, 0, 255), (0, 0), a)
    s = s.filter(ImageFilter.GaussianBlur(radio * SS / 4))
    out = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    out.paste(s, (int(desplaza[0] * SS / 4), int(desplaza[1] * SS / 4)))
    return out


def main() -> int:
    img = fondo()

    g = engranaje()
    img.alpha_composite(sombra(g, (5, 7), 7, 60))
    img.alpha_composite(g)

    c = coche()
    img.alpha_composite(sombra(c, (0, 10), 11, 120))
    img.alpha_composite(c)

    final = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    final.paste(img, (0, 0), _mascara_cuadrado(int(0.30 * W)))
    final = final.resize((BASE, BASE), Image.LANCZOS)

    destino = Path(__file__).resolve().parent.parent / "taller" / "resources" / "icono.png"
    final.save(destino)
    print("Escrito", destino, final.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
