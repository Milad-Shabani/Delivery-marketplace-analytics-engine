"""Build the two dashboard versions (English + Persian/RTL) from one template.

    python scripts/build_dashboards.py

Inputs
    src/dashboard/template.html      layout, CSS and chart code (language-neutral)
    src/dashboard/i18n/en.json       English strings
    src/dashboard/i18n/fa.json       Persian strings
    dashboard/data/dashboard_data.js  data payload (python scripts/build_dashboard_data.py)

Outputs (served by GitHub Pages from the dashboard/ folder)
    dashboard/index.html             English  -> <pages-url>/
    dashboard/fa/index.html          Persian  -> <pages-url>/fa/
    outputs/dashboard/               verbatim copy of dashboard/ (portfolio snapshot)

The build fails loudly if the two language files do not have exactly the same keys,
if a string uses different {placeholders} in the two languages, or if the template
or the data payload needs a string that is missing.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "dashboard")
DASH = os.path.join(ROOT, "dashboard")
OUT_DASH = os.path.join(ROOT, "outputs", "dashboard")

FONT_BASE = "https://cdn.jsdelivr.net/npm/vazirmatn@33.0.3/misc/Farsi-Digits/fonts/webfonts/Vazirmatn-FD-{w}.woff2"
FONT_WEIGHTS = {400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold"}

LANGS = {
    "en": {"dir": "ltr", "out": os.path.join(DASH, "index.html"), "asset_prefix": ""},
    "fa": {"dir": "rtl", "out": os.path.join(DASH, "fa", "index.html"), "asset_prefix": "../"},
}


def load(lang: str) -> dict:
    with open(os.path.join(SRC, "i18n", f"{lang}.json"), encoding="utf-8") as f:
        return json.load(f)


def flat_keys(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flat_keys(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


def placeholders(s: str) -> set:
    return set(re.findall(r"\{(\w+)\}", s))


def validate(en: dict, fa: dict, template: str, data_js: str) -> None:
    errors = []
    fe, ff = flat_keys(en), flat_keys(fa)
    for k in sorted(set(fe) - set(ff)):
        errors.append(f"missing in fa.json: {k}")
    for k in sorted(set(ff) - set(fe)):
        errors.append(f"missing in en.json: {k}")
    for k in sorted(set(fe) & set(ff)):
        if not isinstance(fe[k], str) or not isinstance(ff[k], str):
            errors.append(f"non-string value: {k}")
            continue
        if not fe[k].strip() or not ff[k].strip():
            errors.append(f"empty string: {k}")
        if placeholders(fe[k]) != placeholders(ff[k]):
            errors.append(f"placeholder mismatch in {k}: {sorted(placeholders(fe[k]))} vs {sorted(placeholders(ff[k]))}")

    # every {{t.key}} and every T.key used by the template must exist
    for k in set(re.findall(r"\{\{t\.(\w+)\}\}", template)) | set(re.findall(r"\bT\.([A-Za-z_]\w*)", template)):
        if k not in en:
            errors.append(f"template uses a missing string: {k}")

    # every KPI in the scorecard needs a label and a definition, every group a title
    payload = json.loads(data_js[data_js.index("{"): data_js.rindex("}") + 1])
    for g in payload["scorecard"]["groups"]:
        if f"grp_{g['key']}" not in en:
            errors.append(f"missing group title: grp_{g['key']}")
        for it in g["items"]:
            for pre in ("kpi_", "def_"):
                if pre + it["key"] not in en:
                    errors.append(f"missing KPI string: {pre}{it['key']}")

    # every category value that is displayed through nm() needs a translation
    names = en["names"]
    seen = []
    seen += payload["cities"]["names"] + payload["segments"]["names"] + payload["channels"]["names"]
    seen += payload["drivers"]["labels"] + list(payload["forecast"]["metrics"].keys())
    seen += [r["model"] for rows in payload["forecast"]["validation"].values() for r in rows]
    ue, ops = payload["unit_econ"], payload["ops"]
    seen += ue["by_cuisine"]["names"] + ue["by_tier"]["names"] + ue["by_payment"]["names"]
    seen += ops["vehicle"]["names"] + ops["delay_rating"]["buckets"] + ops["cancel_reasons"]["names"]
    seen += payload["customers_ext"]["segment_profile"]["names"] + payload["marketing"]["channels"]
    seen += ["Subscribed", "Not Subscribed"]
    for lab in payload["optimization"]["cells"]["labels"]:
        seen += lab.split(" / ")
    for s in sorted(set(seen)):
        if s not in names:
            errors.append(f"missing name translation: {s!r}")
    for q in set(payload["restaurants"]["quadrant_labels"]):
        if q.split(":")[0] not in en["quad"]:
            errors.append(f"missing quadrant translation: {q.split(':')[0]!r}")
    if payload["plan"]["verdict"] not in en["verdicts"]:
        errors.append("missing verdict translation for the current strategic-plan verdict")

    if errors:
        print("i18n validation failed:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        raise SystemExit(1)


def font_css(lang: str) -> str:
    if lang != "fa":
        return ""
    faces = "\n".join(
        f'  @font-face{{font-family:"VazirFD";font-weight:{w};font-style:normal;font-display:swap;'
        f'src:url("{FONT_BASE.format(w=name)}") format("woff2");}}'
        for w, name in FONT_WEIGHTS.items()
    )
    return ("  /* Vazirmatn FD: Latin digits in text and charts are drawn as Persian digits */\n" + faces + "\n")


GOOGLE_FONTS = ("https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700..800"
                "&family=Instrument+Sans:wght@400..700&display=swap")


def font_links(lang: str) -> str:
    """<head> tags that load the page fonts (English: Google Fonts; Persian: Vazirmatn FD via @font-face)."""
    if lang == "fa":
        return ('<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>\n'
                f'<link rel="preload" as="font" type="font/woff2" crossorigin href="{FONT_BASE.format(w="Regular")}">\n'
                f'<link rel="preload" as="font" type="font/woff2" crossorigin href="{FONT_BASE.format(w="ExtraBold")}">')
    return ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            f'<link rel="stylesheet" href="{GOOGLE_FONTS}">')


def lang_switch(lang: str) -> str:
    if lang == "en":
        return '<span lang="en">English</span><a href="fa/index.html" hreflang="fa" lang="fa">فارسی</a>'
    return '<a href="../index.html" hreflang="en" lang="en">English</a><span lang="fa">فارسی</span>'


def foot_lang(lang: str) -> str:
    if lang == "en":
        return 'Also available in <a href="fa/index.html" hreflang="fa" lang="fa">فارسی (Persian)</a>'
    return 'این داشبورد به زبان انگلیسی هم موجود است: <a href="../index.html" hreflang="en" lang="en">English version</a>'


def render(template: str, lang: str, strings: dict) -> str:
    cfg = LANGS[lang]
    html = template

    # simple, attribute-safe substitution of {{t.key}}
    html = re.sub(r"\{\{t\.(\w+)\}\}", lambda m: _escape(strings[m.group(1)], html, m), html)
    html = html.replace("{{font_css}}", font_css(lang))
    html = html.replace("{{font_links}}", font_links(lang))
    html = html.replace("{{lang_switch}}", lang_switch(lang))
    html = html.replace("{{foot_lang}}", foot_lang(lang))
    html = html.replace("{{asset_prefix}}", cfg["asset_prefix"])
    html = html.replace("{{dir}}", cfg["dir"]).replace("{{lang}}", lang)
    i18n = json.dumps(strings, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("{{i18n_json}}", i18n)
    left = re.findall(r"\{\{[^}]+\}\}", html)
    if left:
        raise SystemExit(f"unresolved placeholders in {lang}: {sorted(set(left))}")
    return html


def _escape(value: str, html: str, m: re.Match) -> str:
    """Escape quotes when the placeholder sits inside an HTML attribute; keep markup elsewhere."""
    before = html[max(0, m.start() - 200): m.start()]
    in_tag = before.rfind("<") > before.rfind(">")
    return value.replace('"', "&quot;") if in_tag else value


def main() -> None:
    with open(os.path.join(SRC, "template.html"), encoding="utf-8") as f:
        template = f.read()
    with open(os.path.join(DASH, "data", "dashboard_data.js"), encoding="utf-8") as f:
        data_js = f.read()
    en, fa = load("en"), load("fa")
    validate(en, fa, template, data_js)

    for lang, strings in (("en", en), ("fa", fa)):
        out = LANGS[lang]["out"]
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(render(template, lang, strings))
        print(f"wrote {os.path.relpath(out, ROOT)}  ({os.path.getsize(out) / 1024:.0f} KB)")

    # portfolio snapshot: outputs/dashboard mirrors dashboard/
    if os.path.isdir(OUT_DASH):
        shutil.rmtree(OUT_DASH)
    shutil.copytree(DASH, OUT_DASH)
    print("synced outputs/dashboard/")


if __name__ == "__main__":
    main()
