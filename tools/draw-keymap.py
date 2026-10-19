"""Draws every layer of config/cygnus.keymap into one PNG (docs/keymap.png).

    nix run .#draw-keymap -- [keymap [output.png]]

The layers, their keys, which key holds which layer, and the layer combos are
all read from the keymap itself, so the picture cannot drift from the
firmware. Only the key legends (how a keycode is spelled on a keycap) live
here. Needs pycairo and the "Noto Sans" font (arrows are drawn, not typed).

Adapted from https://github.com/zvakanaka/zmk-config (tools/draw-keymap.py).
"""
import math
import os
import re
import sys

import cairo

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CONFIG = os.path.join(REPO, "config")
KEYBOARDS = {  # keymap -> (title, output)
    "cygnus": ("Dactyl Cygnus 4×6", os.path.join(REPO, "docs", "keymap.png")),
}

# The physical layout the firmware (and ZMK Studio) uses
LAYOUT = os.path.join(REPO, "boards", "shields", "cygnus", "cygnus-layout.dtsi")

# --------------------------------------------------------------------------
# Parsing the keymap
# --------------------------------------------------------------------------


def read_with_includes(path, seen=None):
    """The file's text with its #include "..." lines replaced by the included
    file (the <...> includes are ZMK's own and are left out), comments removed."""
    seen = seen if seen is not None else set()
    path = os.path.realpath(path)
    if path in seen:
        return ""
    seen.add(path)
    out = []
    for line in open(path).read().splitlines():
        line = re.sub(r"//.*", "", line)
        m = re.match(r'\s*#include\s+"([^"]+)"', line)
        if m:
            out.append(read_with_includes(os.path.join(os.path.dirname(path), m.group(1)), seen))
        elif re.match(r"\s*#include\s+<", line):
            continue
        else:
            out.append(line)
    return "\n".join(out)


def expand_macros(text):
    """Expands the object-like #define macros in `text`, so a layer number or
    a row of keys can be a macro."""
    macros, kept = {}, []
    for line in text.splitlines():
        m = re.match(r"\s*#define\s+(\w+)(?:\s+(.*))?$", line)
        if m:
            macros[m.group(1)] = (m.group(2) or "").strip()
        else:
            kept.append(line)
    text = "\n".join(kept)
    pattern = re.compile(r"\b(" + "|".join(sorted(map(re.escape, macros), key=len, reverse=True)) + r")\b") if macros else None
    for _ in range(10):  # macros use other macros
        if not pattern:
            break
        new = pattern.sub(lambda m: macros[m.group(1)], text)
        if new == text:
            break
        text = new
    return text


def read_layout(path):
    """The keys of the physical layout in `path`, in key-position order, as
    (x, y, w, h, rotation in degrees, pivot x, pivot y) in hundredths of a key."""
    keys = []
    for m in re.finditer(r"<&key_physical_attrs([^>]*)>", read_with_includes(path)):
        w, h, x, y, rot, rx, ry = (int(n.strip("()")) for n in m.group(1).split())
        keys.append((x, y, w, h, rot / 100, rx, ry))
    return keys


def parse_behaviors(text):
    """The keymap's own hold-taps and macros, as (hold_taps, macros):
    hold_taps = {name: behavior its hold binds ("kp" or "mo")} and macros =
    {name: display-name}."""
    hold_taps, macros = {}, {}
    for name, body in re.findall(r"(\w+)\s*:\s*[\w-]+\s*\{([^{}]*)\}", text):
        if '"zmk,behavior-hold-tap"' in body:
            hold_taps[name] = re.search(r"bindings\s*=\s*<&(\w+)>", body).group(1)
        elif '"zmk,behavior-macro"' in body:
            m = re.search(r'display-name\s*=\s*"([^"]+)"', body)
            if m:
                macros[name] = m.group(1)
    return hold_taps, macros


def parse_keymap(path):
    """Returns (layers, combos, hold_taps, macros): layers = [(display name,
    [binding ...]), ...] where a binding is a list (its behavior without the
    &, then its arguments), combos = [([positions], "mo" or "tog", layer
    number)] for the combos that switch layers, and hold_taps and macros are
    as parse_behaviors returns them."""
    text = expand_macros(read_with_includes(path))
    layers = []
    for m in re.finditer(r'(\w+)\s*\{\s*display-name\s*=\s*"([^"]+)";.*?bindings\s*=\s*<(.*?)>;', text, re.S):
        bindings = [b.split() for b in m.group(3).split("&") if b.strip()]
        layers.append((m.group(2), bindings))
    combos = []
    combos_node = re.search(r'compatible\s*=\s*"zmk,combos";(.*?)\n    \};', text, re.S)
    for body in re.findall(r"\w+\s*\{([^{}]*)\}", combos_node.group(1) if combos_node else ""):
        b = re.search(r"bindings\s*=\s*<&(mo|tog)\s+(\d+)>", body)
        p = re.search(r"key-positions\s*=\s*<([^>]*)>", body)
        if b and p:
            combos.append(([int(n) for n in p.group(1).split()], b.group(1), int(b.group(2))))
    return (layers, combos, *parse_behaviors(text))


# --------------------------------------------------------------------------
# Legends. kind picks the colour; main is the big text, shifted a small one
# above it, hold a small one below it.
# --------------------------------------------------------------------------

LETTERS = {c: c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
KEYS_LEGEND = {
    **{f"N{i}": (str(i), "number") for i in range(10)},
    **{f"F{i}": (f"F{i}", "function") for i in range(1, 13)},
    "MINUS": ("-", "symbol"), "EQUAL": ("=", "symbol"), "GRAVE": ("`", "symbol"),
    "SEMI": (";", "symbol"), "LBKT": ("[", "symbol"), "RBKT": ("]", "symbol"),
    "BSLH": ("\\", "symbol"), "SQT": ("'", "symbol"), "COMMA": (",", "symbol"),
    "DOT": (".", "symbol"), "SLASH": ("/", "symbol"),
    "ESC": ("Esc", "edit"), "SPACE": ("Space", "edit"), "TAB": ("Tab", "edit"),
    "ENTER": ("Enter", "edit"), "BSPC": ("Bksp", "edit"), "DEL": ("Del", "edit"),
    "PSCRN": ("PrtSc", "edit"),
    "LCTRL": ("Ctrl", "edit"), "RCTRL": ("Ctrl", "edit"), "LSHFT": ("Shift", "edit"), "RSHFT": ("Shift", "edit"),
    "LALT": ("Alt", "edit"), "RALT": ("Alt", "edit"), "LGUI": ("Gui", "edit"), "RGUI": ("Gui", "edit"),
    "HOME": ("Home", "nav"), "END": ("End", "nav"), "PG_UP": ("PgUp", "nav"), "PG_DN": ("PgDn", "nav"),
    "LEFT": ("←", "nav"), "DOWN": ("↓", "nav"), "UP": ("↑", "nav"), "RIGHT": ("→", "nav"),
    "C_PREV": ("Prev", "media"), "C_STOP": ("Stop", "media"), "C_PP": ("Play", "media"),
    "C_NEXT": ("Next", "media"), "C_BRI_DN": ("Bri −", "media"), "C_BRI_UP": ("Bri +", "media"),
    "C_VOL_DN": ("Vol −", "media"), "C_VOL_UP": ("Vol +", "media"),
}
SHIFTED = {
    "N1": "!", "N2": "@", "N3": "#", "N4": "$", "N5": "%", "N6": "^", "N7": "&", "N8": "*",
    "N9": "(", "N0": ")", "MINUS": "_", "EQUAL": "+", "GRAVE": "~", "SEMI": ":", "LBKT": "{",
    "RBKT": "}", "BSLH": "|", "SQT": '"', "COMMA": "<", "DOT": ">", "SLASH": "?",
}
MODS = {"LCTRL": "Ctrl", "RCTRL": "Ctrl", "LSHFT": "Shift", "RSHFT": "Shift",
        "LALT": "Alt", "RALT": "Alt", "LGUI": "Gui", "RGUI": "Gui"}
MOUSE = {"LCLK": "L-Click", "MCLK": "M-Click", "RCLK": "R-Click",
         "MOVE_UP": "Ms ↑", "MOVE_DOWN": "Ms ↓", "MOVE_LEFT": "Ms ←", "MOVE_RIGHT": "Ms →"}
# &name HOLD TAP -> what the hold binds; draw() adds the keymap's own hold-taps
HOLD_TAPS = {"mt": "kp", "lt": "mo"}

# ZMK's other spellings of the codes above, and the already-shifted symbols
ALIASES = {
    "LEFT_CONTROL": "LCTRL", "RIGHT_CONTROL": "RCTRL", "LEFT_SHIFT": "LSHFT", "RIGHT_SHIFT": "RSHFT",
    "LEFT_ALT": "LALT", "RIGHT_ALT": "RALT", "LEFT_GUI": "LGUI", "RIGHT_GUI": "RGUI",
    "BACKSPACE": "BSPC", "BACKSLASH": "BSLH", "FSLH": "SLASH", "RET": "ENTER", "RETURN": "ENTER",
    "DELETE": "DEL", "ESCAPE": "ESC", "SINGLE_QUOTE": "SQT", "APOS": "SQT", "SEMICOLON": "SEMI",
    "PERIOD": "DOT", "LEFT_BRACKET": "LBKT", "RIGHT_BRACKET": "RBKT",
}
KEYS_LEGEND.update({
    "EXCLAMATION": ("!", "symbol"), "EXCL": ("!", "symbol"), "AT_SIGN": ("@", "symbol"), "AT": ("@", "symbol"),
    "POUND": ("#", "symbol"), "HASH": ("#", "symbol"), "DOLLAR": ("$", "symbol"), "DLLR": ("$", "symbol"),
    "PERCENT": ("%", "symbol"), "PRCNT": ("%", "symbol"), "CARET": ("^", "symbol"),
    "AMPERSAND": ("&", "symbol"), "AMPS": ("&", "symbol"), "ASTERISK": ("*", "symbol"), "ASTRK": ("*", "symbol"),
    "LEFT_PARENTHESIS": ("(", "symbol"), "LPAR": ("(", "symbol"),
    "RIGHT_PARENTHESIS": (")", "symbol"), "RPAR": (")", "symbol"),
    "UNDERSCORE": ("_", "symbol"), "UNDER": ("_", "symbol"), "PLUS": ("+", "symbol"),
    "TILDE": ("~", "symbol"), "COLON": (":", "symbol"), "DOUBLE_QUOTES": ('"', "symbol"), "DQT": ('"', "symbol"),
    "LESS_THAN": ("<", "symbol"), "LT": ("<", "symbol"), "GREATER_THAN": (">", "symbol"), "GT": (">", "symbol"),
    "LEFT_BRACE": ("{", "symbol"), "LBRC": ("{", "symbol"), "RIGHT_BRACE": ("}", "symbol"), "RBRC": ("}", "symbol"),
    "PIPE": ("|", "symbol"), "QUESTION": ("?", "symbol"), "QMARK": ("?", "symbol"),
})
MACROS = {}  # the keymap's macros, drawn as their display-name; filled in by draw()


def legend(code):
    """(main, kind, shifted) for a ZMK key code."""
    code = ALIASES.get(code, code)
    if code in LETTERS:
        return code, "letter", None
    if code in KEYS_LEGEND:
        main, kind = KEYS_LEGEND[code]
        return main, kind, SHIFTED.get(code)
    return code, "edit", None


def describe(binding, layer_names):
    """A binding -> dict(main, kind, shifted, hold, hold_kind, layer) where
    layer is the layer this key switches to, if any."""
    name, args = binding[0], binding[1:]
    key = dict(main="", kind="none", shifted=None, hold=None, hold_kind=None, layer=None)
    if name == "trans":
        key["kind"] = "trans"
    elif name == "none":
        key["kind"] = "none"
    elif name == "kp":
        key["main"], key["kind"], key["shifted"] = legend(args[0])
    elif name in HOLD_TAPS:
        key["main"], key["kind"], key["shifted"] = legend(args[1])
        if HOLD_TAPS[name] == "mo":
            key["hold"], key["hold_kind"] = layer_names[args[0]], "layer"
            key["layer"] = args[0]
        else:
            mod = ALIASES.get(args[0], args[0])
            key["hold"], key["hold_kind"] = MODS.get(mod, mod), "mod"
    elif name == "mkp":
        key["main"], key["kind"] = MOUSE[args[0]], "mouse"
    elif name == "mmv":
        key["main"], key["kind"] = MOUSE[args[0]], "mouse"
    elif name == "bt":
        key["main"] = "BT " + args[1] if args[0] == "BT_SEL" else "BT CLR"
        key["kind"] = "system"
    elif name == "bootloader":
        key["main"], key["kind"] = "BOOT", "boot"
    elif name == "sys_reset":
        key["main"], key["kind"] = "Reset", "boot"
    elif name == "caps_word":
        key["main"], key["kind"] = "Caps Word", "edit"
    elif name == "studio_unlock":
        key["main"], key["kind"] = "Studio", "system"
    elif name in MACROS:
        key["main"], key["kind"] = MACROS[name], "symbol"
    elif name == "out":
        key["main"], key["kind"] = "USB/BT", "system"
    else:
        key["main"], key["kind"] = name.upper(), "edit"
    return key


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

FONT = "Noto Sans"

UNIT = 90.0          # pixels per key
SCALE = 2            # supersampling: the PNG is SCALE x the logical size
PAD = 56
LAYER_HEAD = 78
LAYER_GAP = 34
HEADER_H = 270
FOOTER_H = 26
KEYS = []
BOARD_W = BOARD_H = 0  # set per keyboard by use_layout()


def use_layout(keys):
    """Selects the physical layout to draw and sizes the board to fit it
    (rotated keys included)."""
    global KEYS, BOARD_W, BOARD_H
    KEYS = keys
    xs, ys = [], []
    for x, y, w, h, rot, rx, ry in keys:
        a = math.radians(rot)
        for cx, cy in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
            dx, dy = cx - rx, cy - ry
            xs.append(rx + dx * math.cos(a) - dy * math.sin(a) if rot else cx)
            ys.append(ry + dx * math.sin(a) + dy * math.cos(a) if rot else cy)
    s = UNIT / 100
    BOARD_W = max(xs) * s
    BOARD_H = max(ys) * s + 0.1 * UNIT


INK = (0.13, 0.15, 0.19)
MUTED = (0.47, 0.50, 0.56)
BG = (0.965, 0.972, 0.98)
CARD = (1, 1, 1)
RULE = (0.86, 0.88, 0.91)

# fill, edge, text per kind
KINDS = {
    "letter": ((1.0, 1.0, 1.0), (0.78, 0.82, 0.87), INK, "Letters"),
    "number": ((0.87, 0.93, 1.0), (0.55, 0.72, 0.95), (0.08, 0.27, 0.58), "Numbers"),
    "symbol": ((0.93, 0.90, 1.0), (0.69, 0.62, 0.93), (0.30, 0.20, 0.62), "Punctuation"),
    "function": ((0.86, 0.96, 0.91), (0.46, 0.76, 0.62), (0.07, 0.38, 0.24), "Function keys"),
    "edit": ((0.93, 0.94, 0.96), (0.68, 0.72, 0.78), INK, "Edit keys"),
    "nav": ((1.0, 0.96, 0.66), (0.80, 0.70, 0.12), (0.43, 0.34, 0.0), "Navigation"),
    "mouse": ((0.99, 0.69, 0.36), (0.86, 0.46, 0.08), (0.36, 0.16, 0.0), "Mouse"),
    "media": ((0.98, 0.83, 0.93), (0.86, 0.50, 0.72), (0.50, 0.10, 0.34), "Media"),
    "system": ((0.27, 0.33, 0.44), (0.16, 0.21, 0.30), (1.0, 1.0, 1.0), "Bluetooth, Studio"),  # dark slate: far from the pastel blue of numbers
    "boot": ((0.82, 0.20, 0.20), (0.60, 0.10, 0.10), (1.0, 1.0, 1.0), "Bootloader, reset"),
}
MOD_PILL = ((0.80, 0.90, 0.99), (0.07, 0.30, 0.58))
LAYER_PILL = ((0.43, 0.29, 0.80), (1, 1, 1))
HELD = ((0.43, 0.29, 0.80), (0.33, 0.20, 0.70), (1, 1, 1))


class Canvas:
    def __init__(self, ctx):
        self.c = ctx

    def font(self, size, bold=False):
        self.c.select_font_face(FONT, cairo.FONT_SLANT_NORMAL,
                                cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
        self.c.set_font_size(size)

    def text(self, x, y, s, size, color, bold=False, align="center", max_w=None):
        """Draws s with its baseline at y; shrinks to fit max_w."""
        c = self.c
        self.font(size, bold)
        w = c.text_extents(s).x_advance
        if max_w and w > max_w:
            size *= max_w / w
            self.font(size, bold)
            w = c.text_extents(s).x_advance
        c.set_source_rgb(*color)
        c.move_to(x - (w / 2 if align == "center" else w if align == "right" else 0), y)
        c.show_text(s)
        return w

    def rrect(self, x, y, w, h, r):
        c = self.c
        c.new_sub_path()
        c.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        c.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        c.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        c.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        c.close_path()

    def box(self, x, y, w, h, r, fill=None, edge=None, width=1.5, dash=None):
        c = self.c
        self.rrect(x, y, w, h, r)
        if fill:
            c.set_source_rgb(*fill)
            c.fill_preserve() if edge else c.fill()
        if edge:
            c.set_source_rgb(*edge)
            c.set_line_width(width)
            if dash:
                c.set_dash(dash)
            c.stroke()
            c.set_dash([])
        c.new_path()


ARROWS = {"←": 180, "↑": -90, "→": 0, "↓": 90}  # direction in degrees


def draw_arrow(c, cx, cy, size, direction, color):
    """A bold arrow centred on (cx, cy), drawn as a path (no font has to
    supply the glyph)."""
    c.save()
    c.translate(cx, cy)
    c.rotate(math.radians(ARROWS[direction]))
    half, head = size / 2, size * 0.42
    c.set_source_rgb(*color)
    c.set_line_width(size * 0.15)
    c.set_line_cap(cairo.LINE_CAP_ROUND)
    c.set_line_join(cairo.LINE_JOIN_ROUND)
    c.move_to(-half, 0)
    c.line_to(half, 0)
    c.move_to(half - head, -head)
    c.line_to(half, 0)
    c.line_to(half - head, head)
    c.stroke()
    c.restore()


def draw_triangle(c, cx, cy, size, color):
    """The outlined down-pointing triangle marking a key that passes through."""
    c.set_source_rgb(*color)
    c.set_line_width(size * 0.14)
    c.set_line_join(cairo.LINE_JOIN_ROUND)
    c.move_to(cx - size / 2, cy - size * 0.38)
    c.line_to(cx + size / 2, cy - size * 0.38)
    c.line_to(cx, cy + size * 0.42)
    c.close_path()
    c.stroke()


def draw_legend_text(cv, cx, baseline, label, size, color, max_w):
    """A key's main legend: text, an arrow, or "Ms" followed by an arrow."""
    if label in ARROWS:
        draw_arrow(cv.c, cx, baseline - size * 0.36, size * 0.95, label, color)
    elif label.startswith("Ms ") and label[3:] in ARROWS:
        cv.font(size, True)
        tw = cv.c.text_extents("Ms").x_advance
        gap, asz = size * 0.3, size * 0.7
        total = tw + gap + asz
        x0 = cx - total / 2
        cv.text(x0, baseline, "Ms", size, color, True, align="left")
        draw_arrow(cv.c, x0 + tw + gap + asz / 2, baseline - size * 0.36, asz, label[3:], color)
    else:
        cv.text(cx, baseline, label, size, color, True, max_w=max_w)


def key_geometry(i, ox, oy):
    """(x, y, w, h, angle_rad, pivot_x, pivot_y) of key i in pixels, offset by (ox, oy)."""
    x, y, w, h, rot, rx, ry = KEYS[i]
    s = UNIT / 100
    return (ox + x * s, oy + y * s, w * s, h * s, math.radians(rot), ox + rx * s, oy + ry * s)


def draw_key(cv, i, ox, oy, key, held):
    c = cv.c
    x, y, w, h, ang, px, py = key_geometry(i, ox, oy)
    gap = 4.5
    x, y, w, h = x + gap, y + gap, w - 2 * gap, h - 2 * gap
    c.save()
    if ang:
        c.translate(px, py)
        c.rotate(ang)
        c.translate(-px, -py)
    kind = key["kind"]
    cx = x + w / 2
    if held:
        fill, edge, ink = HELD
        cv.box(x, y, w, h, 9, fill, edge, 2)
        cv.text(cx, y + h / 2 + 7, held, 17, ink, True, max_w=w - 10)
        c.restore()
        return
    if kind == "trans":
        cv.box(x, y, w, h, 9, None, (0.80, 0.83, 0.87), 1.4, dash=[4, 4])
        # upright, even on the angled thumb keys
        c.save()
        c.translate(cx, y + h / 2)
        c.rotate(-ang)
        draw_triangle(c, 0, 0, 14, (0.74, 0.77, 0.82))
        c.restore()
        c.restore()
        return
    if kind == "none":
        cv.box(x, y, w, h, 9, (0.95, 0.955, 0.965), (0.90, 0.91, 0.93), 1.2)
        c.restore()
        return
    fill, edge, ink, _ = KINDS[kind]
    cv.box(x, y, w, h, 9, fill, edge, 1.6)
    main = key["main"]
    big = 28 if len(main) == 1 else 20
    if key["shifted"] and len(main) == 1 and not main.isalpha():
        # a symbol with its shifted partner: partner above, key below
        cv.text(cx, y + 24, key["shifted"], 18, MUTED, False, max_w=w - 12)
        cv.text(cx, y + h / 2 + 12, main, 28, ink, True, max_w=w - 12)
    else:
        dy = 4 if key["hold"] else 10
        draw_legend_text(cv, cx, y + h / 2 + dy, main, 30 if main in ARROWS else big, ink, w - 12)
    if key["hold"]:
        pill, pink = MOD_PILL if key["hold_kind"] == "mod" else LAYER_PILL
        ph = 19
        py_ = y + h - ph - 6
        cv.c.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cv.c.set_font_size(13)
        tw = min(cv.c.text_extents(key["hold"]).x_advance, w - 16)
        cv.box(cx - tw / 2 - 7, py_, tw + 14, ph, ph / 2, pill)
        cv.text(cx, py_ + 14, key["hold"], 13, pink, True, max_w=w - 16)
    c.restore()


def key_center(i, ox, oy):
    x, y, w, h, ang, px, py = key_geometry(i, ox, oy)
    cx, cy = x + w / 2, y + h / 2
    dx, dy = cx - px, cy - py
    return (px + dx * math.cos(ang) - dy * math.sin(ang), py + dx * math.sin(ang) + dy * math.cos(ang))


def spoken(label):
    """A key legend written out for a sentence."""
    return {"Bksp": "Backspace"}.get(label, label)


def keys_together(base, positions, layer_names):
    """ "Shift + Z", or "both Shift" when the keys have the same legend."""
    names = [spoken(describe(base[p], layer_names)["main"]) for p in sorted(positions)]
    return f"both {names[0]}" if len(set(names)) == 1 else " + ".join(names)


def how_to_reach(index, base, layer_names, combos):
    """(subtitle, held positions, label on the held keys) for layer `index`."""
    if index == 0:
        return "Default layer. Top of each key: tap. Bottom: hold.", [], None
    taps = [p for p, b in enumerate(base) if describe(b, layer_names)["layer"] == str(index)]
    if taps:
        return "Hold " + spoken(describe(base[taps[0]], layer_names)["main"]), taps, "held"
    held = [c for c in combos if c[1] == "mo" and c[2] == index]
    if held:
        how = "Hold " + " together, or ".join(keys_together(base, c[0], layer_names) for c in held) + " together"
        return how, [p for c in held for p in c[0]], "held"
    toggles = [c for c in combos if c[1] == "tog" and c[2] == index]
    if toggles:
        return "Press " + keys_together(base, toggles[0][0], layer_names) + " together to toggle on and off", toggles[0][0], "toggle"
    return "", [], None


def draw_layer(cv, index, name, bindings, layer_names, base, combos, ox, oy, width):
    card_h = LAYER_HEAD + BOARD_H + 24
    cv.box(PAD, oy, width - 2 * PAD, card_h, 18, CARD, RULE, 1.5)
    # title
    cv.text(PAD + 30, oy + 52, name.upper(), 34, INK, True, align="left")
    tw = cv.c.text_extents(name.upper()).x_advance
    how, held, held_label = how_to_reach(index, base, layer_names, combos)
    cv.text(PAD + 30 + tw + 22, oy + 50, how, 20, MUTED, False, align="left")

    bx, by = ox, oy + LAYER_HEAD
    for i, b in enumerate(bindings):
        k = describe(b, layer_names)
        draw_key(cv, i, bx, by, k, held=held_label if i in held else None)


def draw_legend(cv, right, top, shown_kinds):
    """The colour key, in the top-right corner."""
    c = cv.c
    cols = 3
    rows = math.ceil(len(shown_kinds) / cols)
    cw, rh = 172, 27
    w = cols * cw + 34
    h = 52 + rows * rh + 70
    x0 = right - w
    cv.box(x0, top, w, h, 14, CARD, RULE, 1.5)
    cv.text(x0 + 18, top + 31, "KEY COLORS", 14, MUTED, True, align="left")
    for n, kind in enumerate(shown_kinds):
        fill, edge, ink, label = KINDS[kind]
        cx = x0 + 18 + (n % cols) * cw
        cy = top + 46 + (n // cols) * rh
        cv.box(cx, cy, 22, 18, 5, fill, edge, 1.4)
        cv.text(cx + 32, cy + 14, label, 15, INK, False, align="left")
    y = top + 46 + rows * rh + 10
    # how to read a key
    cv.box(x0 + 18, y, 22, 18, 9, MOD_PILL[0])
    cv.text(x0 + 50, y + 14, "hold: modifier", 14, INK, False, align="left")
    cv.box(x0 + 18 + cw, y, 22, 18, 9, LAYER_PILL[0])
    cv.text(x0 + 50 + cw, y + 14, "hold: layer", 14, INK, False, align="left")
    y += 25
    cv.box(x0 + 18, y, 22, 18, 5, None, (0.80, 0.83, 0.87), 1.4, dash=[3, 3])
    draw_triangle(c, x0 + 29, y + 9, 8, (0.62, 0.66, 0.72))
    cv.text(x0 + 50, y + 14, "same as Base", 14, INK, False, align="left")
    cv.box(x0 + 18 + cw, y, 22, 18, 5, *HELD[:2])
    cv.text(x0 + 50 + cw, y + 14, "key you hold / press", 14, INK, False, align="left")
    return w, h


def draw(keymap, title, out):
    layers, combos, hold_taps, macros = parse_keymap(keymap)
    HOLD_TAPS.update(hold_taps)
    MACROS.update(macros)
    n_keys = len(layers[0][1])
    keys = read_layout(LAYOUT)
    if len(keys) != n_keys:
        sys.exit(f"{keymap}: {n_keys} keys, but {os.path.relpath(LAYOUT, REPO)} has {len(keys)}")
    use_layout(keys)
    layer_names = {str(i): name for i, (name, _) in enumerate(layers)}
    base = layers[0][1]

    width = int(BOARD_W + 2 * PAD + 2 * 30)
    layer_h = LAYER_HEAD + BOARD_H + 24
    height = int(HEADER_H + len(layers) * (layer_h + LAYER_GAP) + FOOTER_H)

    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, width * SCALE, height * SCALE)
    ctx = cairo.Context(surf)
    ctx.scale(SCALE, SCALE)
    ctx.set_antialias(cairo.ANTIALIAS_BEST)
    fo = cairo.FontOptions()
    fo.set_antialias(cairo.ANTIALIAS_GRAY)
    fo.set_hint_style(cairo.HINT_STYLE_NONE)
    fo.set_hint_metrics(cairo.HINT_METRICS_OFF)
    ctx.set_font_options(fo)
    ctx.set_source_rgb(*BG)
    ctx.paint()
    cv = Canvas(ctx)

    # header: title at the left, colour key in the top-right corner
    cv.text(PAD, 78, title, 46, INK, True, align="left")
    rel = os.path.relpath(keymap, REPO)
    cv.text(PAD, 112, f"Layers of {rel} · {n_keys} keys, tap and hold", 20, MUTED, False, align="left")
    kinds = []
    for _, bs in layers:
        for b in bs:
            k = describe(b, layer_names)["kind"]
            if k in KINDS and k not in kinds:
                kinds.append(k)
    kinds.sort(key=list(KINDS).index)
    draw_legend(cv, width - PAD, 24, kinds)

    ox = (width - BOARD_W) / 2
    y = HEADER_H
    for i, (name, bindings) in enumerate(layers):
        draw_layer(cv, i, name, bindings, layer_names, base, combos, ox, y, width)
        y += layer_h + LAYER_GAP

    os.makedirs(os.path.dirname(out), exist_ok=True)
    surf.write_to_png(out)
    print(f"wrote {out} ({width * SCALE}x{height * SCALE})")


def main():
    if len(sys.argv) > 1:
        keymap = sys.argv[1]
        name = os.path.splitext(os.path.basename(keymap))[0]
        title, out = KEYBOARDS.get(name, (name, os.path.splitext(keymap)[0] + ".png"))
        draw(keymap, title, sys.argv[2] if len(sys.argv) > 2 else out)
    else:
        for name, (title, out) in KEYBOARDS.items():
            draw(os.path.join(CONFIG, name + ".keymap"), title, out)


if __name__ == "__main__":
    main()
