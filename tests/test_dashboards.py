"""The two dashboard versions (English + Persian) are built from one template; these tests keep them in sync."""
import importlib.util
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("build_dashboards", os.path.join(ROOT, "scripts", "build_dashboards.py"))
bd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bd)


@pytest.fixture(scope="module")
def inputs():
    with open(os.path.join(bd.SRC, "template.html"), encoding="utf-8") as f:
        template = f.read()
    with open(os.path.join(bd.DASH, "data", "dashboard_data.js"), encoding="utf-8") as f:
        data_js = f.read()
    return template, data_js, bd.load("en"), bd.load("fa")


def test_en_and_fa_have_identical_keys(inputs):
    _, _, en, fa = inputs
    assert set(bd.flat_keys(en)) == set(bd.flat_keys(fa))


def test_placeholders_match_between_languages(inputs):
    _, _, en, fa = inputs
    fe, ff = bd.flat_keys(en), bd.flat_keys(fa)
    for k in fe:
        assert bd.placeholders(fe[k]) == bd.placeholders(ff[k]), k


def test_validation_passes_on_current_data(inputs):
    template, data_js, en, fa = inputs
    bd.validate(en, fa, template, data_js)  # raises SystemExit on any problem


def test_every_scorecard_kpi_has_label_and_definition(inputs):
    _, data_js, en, _ = inputs
    payload = json.loads(data_js[data_js.index("{"): data_js.rindex("}") + 1])
    keys = [it["key"] for g in payload["scorecard"]["groups"] for it in g["items"]]
    assert len(keys) >= 30
    for k in keys:
        assert f"kpi_{k}" in en and f"def_{k}" in en


def test_persian_strings_are_translated(inputs):
    _, _, en, fa = inputs
    fe, ff = bd.flat_keys(en), bd.flat_keys(fa)
    persian = re.compile(r"[؀-ۿ]")
    untranslated = [k for k, v in ff.items() if not persian.search(v) and v == fe[k] and re.search(r"[A-Za-z]{4,}", v)
                    and not k.startswith(("meta_font", "names.", "def_", "kpi_"))]
    assert not untranslated, untranslated


def test_rendered_pages_are_complete_and_linked(inputs):
    template, _, en, fa = inputs
    page_en, page_fa = bd.render(template, "en", en), bd.render(template, "fa", fa)
    assert 'dir="ltr"' in page_en and 'dir="rtl"' in page_fa
    assert 'href="fa/index.html"' in page_en and 'href="../index.html"' in page_fa
    assert 'src="data/dashboard_data.js"' in page_en and 'src="../data/dashboard_data.js"' in page_fa
    assert "Vazirmatn" in page_fa and "Vazirmatn" not in page_en
    for page in (page_en, page_fa):
        assert not re.findall(r"\{\{[^}]+\}\}", page)
