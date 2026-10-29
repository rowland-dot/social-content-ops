"""Stage 6: the report an image must pass before the owner sees it, and the re-make rounds."""
from __future__ import annotations
import json, sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tmall_common as common, tmall_copy, tmall_fonts, tmall_held, tmall_layers as ly, tmall_rules

CHECKS = ["claims", "prices", "selling_points_visible", "scenes", "comparison",
          "layers_overlap", "layers_contrast", "layers_light", "layers_shadow_surface",
          "compliance_tmall_rules", "compliance_quality_gate", "thumbnail", "diagnosis_frame",
          "diagnosis_background_looked", "diagnosis_props_looked", "scene_surface_looked", "pack",
          "size_weight", "no_copying", "font_licence", "text_size", "style_lock"]
LOOKED = ["diagnosis_background_looked", "diagnosis_props_looked", "scene_surface_looked"]

NO_REMAKE = {"pack", "font_licence"}     # a new scene cannot cure these: stop and report at once (autoplan review; the text-card layout check is not a check here, the owner 2026-10-28)

def build_report(image_id: str, results: dict, not_confirmed=(), *, image_sha256: str | None = None, folder=None) -> dict:
    """image_sha256 ties the report to the exact image it describes; the pages re-fingerprint the image and refuse a mismatch.
    With a folder, a looked result's evidence must be a file that exists there, not merely a name (autoplan review)."""
    missing = [c for c in CHECKS if c not in results]
    for c in LOOKED:
        r = results.get(c)
        ok = r and r.get("evidence") and (folder is None or (Path(folder) / r["evidence"]).is_file())
        if r and not ok and c not in missing: missing.append(c)
    failed = [c for c in CHECKS if c in results and results[c]["verdict"] == "fail"]
    complete = not missing
    return {"image": image_id, "complete": complete, "missing": missing, "failed": failed, "image_sha256": image_sha256,
            "passed": complete and not failed, "results": results, "not_confirmed": list(not_confirmed)}

def run_rounds(make, fix, max_rounds: int, evaluate) -> dict:
    """Only a failure triggers a re-make. A result that is merely missing (the held quality check, a looked verdict not yet given)
    waits, so no subscription generation is spent on it; a failure no new scene can cure stops at once."""
    report = None
    for n in range(1, max_rounds + 1):
        report = evaluate(make(n))
        if report["passed"]:
            return {"status": "passed", "rounds": n, "report": report}
        if not report["failed"]:
            return {"status": "waiting", "rounds": n, "missing": report["missing"], "report": report}
        if set(report["failed"]) & NO_REMAKE or n == max_rounds:
            break
        fix(report["failed"])
    return {"status": "reported", "rounds": n, "failed": report["failed"], "missing": report["missing"], "report": report}

def copying_hits(text: str, competitor_strings: list[str]) -> list[str]:
    return [s for s in competitor_strings if s and s in text]

def selling_points_problems(selling_point_map: dict, manifests: dict) -> list[str]:
    """Each mapped claim must be set as a text block, measured inside the frame, on the image the plan assigned it to."""
    out = []
    for claim, target in selling_point_map.items():
        m = manifests.get(target)
        if not m:
            out.append(f"{claim}: its image {target} has not been made"); continue
        w, h = m["size"]
        box = lambda t: t.get("full_box") or t.get("box")         # unclipped when compose measured it
        if not any(claim in t.get("claims", []) and box(t) and box(t)[0] >= 0 and box(t)[1] >= 0
                   and box(t)[2] <= w and box(t)[3] <= h for t in m["texts"]):
            out.append(f"{claim}: not visible on {target}")
    return out

def style_problems(texts: list[dict], style_lock: dict) -> list[str]:
    """Spec stage 5: every image after the headline pick inherits its palette and type. Each text block must use the lock's font
    and a colour from its palette (autoplan review: the lock was only checked for being present)."""
    palette, out = {c.lower() for c in style_lock.get("palette", [])}, []
    for t in texts:
        if t["font"] != style_lock.get("font"): out.append(f"{t['id']}: font {t['font']} is not the style lock's {style_lock.get('font')}")
        if t["color"].lower() not in palette: out.append(f"{t['id']}: colour {t['color']} is not in the style lock's palette")
    return out

def _result(check: str, problems, note: str = "") -> dict:
    problems = [p for p in problems if p]
    return {"check": check, "verdict": "fail" if problems else "pass", "method": "measured",
            "note": "; ".join(problems) or note, "evidence": None}

def gather(folder, *, manifest, rules, sheet, selling_points, plan_problems, allowed_prices, bundle_rows,
           competitor_strings, style_lock, looked=None, quality_gate=None, held_file=tmall_held.HELD_FILE) -> dict:
    """Run every measured check on one composed image and return its report. `looked` (check -> result with evidence) and
    `quality_gate` (the result the agent writes after the held live run, which first calls
    `tmall_held.require_released("skill-quality-gate")`) are passed through; this function never makes them up."""
    if quality_gate:          # while the tool is held no real result can exist, so one handed in is refused (fails closed)
        tmall_held.require_released("skill-quality-gate", held_file)
    folder, m = Path(folder), manifest
    v = lambda path: tmall_rules.value(rules, path)
    is_main, pack = m["name"].startswith("M"), m.get("pack")     # by the plan id (M1 to M5, D1...), not by size: a wrongly sized main image must fail as a main image
    layout = json.loads((folder / m["files"]["layout"]).read_text(encoding="utf-8"))
    final, base = folder / m["files"]["final"], Image.open(folder / m["files"]["base"])
    scene = Image.open(folder / f"{m['name']}.layers" / "scene.png")
    blocks = [t for t in m["texts"] if t.get("box")]
    all_text = " ".join(t["text"] for t in m["texts"])
    found = tmall_copy.trace([{"id": t["id"], "tier": t["tier"], "text": t["text"], "claims": t.get("claims", [])} for t in m["texts"]],
                             sheet, allowed_prices, bundle_rows)
    money = [p for p in found if ": price " in p or "bundle" in p]
    max_kb = v("main_image.max_kb") if is_main else v("detail.max_kb")
    sizes = v("main_image.sizes") if is_main else [list(m["size"])]
    no_pack = ["main image has no pack layer"] if is_main else []
    usable = {i["file"] for i in sheet.get("inventory", []) if i.get("use") != "reference only"}   # the profile's real pack photos (stage 1)
    not_inventory = [f"pack photo {Path(pack['source']).name} is not a usable photo in the fact sheet's picture inventory"] \
        if pack and Path(pack["source"]).name not in usable else []
    wrong_width = [f"slice is {m['size'][0]} px wide, not {v('detail.width')}"] if not is_main and m["size"][0] != v("detail.width") else []
    fonts_bad = []
    for t in m["texts"]:
        try:
            tmall_fonts.assert_allowed(t["font"])
        except tmall_fonts.FontNotLicensed as e:
            fonts_bad.append(str(e))
    r = {
        "claims": _result("claims", [p for p in found if p not in money]),
        "prices": _result("prices", money),
        "selling_points_visible": _result("selling_points_visible", selling_points_problems(
            {c: t for c, t in selling_points.items() if t == m["name"]}, {m["name"]: m})),
        "scenes": _result("scenes", [p for p in plan_problems if "scene implies" in p]),
        "comparison": _result("comparison", [p for p in plan_problems if "competitor" in p or "number without" in p]),
        "layers_overlap": _result("layers_overlap", ([f"text '{b['text']}' overlaps the pack" for b in ly.text_over_pack(layout, pack["box"])] if pack else [])
                                  + ly.text_on_text(m["texts"]) + ly.off_frame(m["texts"], m["size"])),
        "layers_contrast": _result("layers_contrast", [ly.contrast_problem(t, base, v("layers.contrast_min")) for t in blocks]
                                   + [ly.gold_on_light_problem(t, base) for t in blocks]),
        "layers_light": _result("layers_light", [ly.light_problem(ly.light_side(Image.open(folder / pack["layer"])), ly.light_side(scene))] if pack else []),
        "layers_shadow_surface": _result("layers_shadow_surface", [ly.shadow_problem(m), ly.surface_problem(scene, pack["box"])] if pack else []),
        "compliance_tmall_rules": _result("compliance_tmall_rules",
            [f"banned word {w}" for w in tmall_rules.banned_hits(all_text, rules)]
            + [f"implies a result: {w}" for w in tmall_rules.after_state_hits(all_text, rules)]
            + [f"bonded-warehouse wording: {w}" for w in tmall_rules.bonded_hits(all_text, rules)]),
        "thumbnail": _result("thumbnail", [ly.thumbnail_problem(m, v("thumbnail.px"), v("thumbnail.min_headline_px"))] if is_main else []),
        "diagnosis_frame": _result("diagnosis_frame", [ly.frame_problem(m, v("diagnosis.product_height_min")),
                                                       ly.glare_problem(Image.open(final), pack["box"], v("diagnosis.glare_max_share"),
                                                                        pack_layer=Image.open(folder / pack["layer"]))] if pack and is_main else no_pack),
        "pack": _result("pack", [ly.pack_problem(folder, m)] + not_inventory if pack else no_pack),
        "size_weight": _result("size_weight", [ly.size_weight_problem(final, sizes, float("inf") if max_kb is None else max_kb)] + wrong_width),
        "no_copying": _result("no_copying", [f"repeats a studied listing: {h}" for h in copying_hits(all_text, competitor_strings)]),
        "font_licence": _result("font_licence", fonts_bad),
        "text_size": _result("text_size", [ly.size_problem(t, tmall_rules.for_width(rules, "text.min_px_main", m["size"][0]) if is_main
                                                           else v("text.min_px_detail")) for t in m["texts"]]),
        "style_lock": _result("style_lock", style_problems(m["texts"], style_lock)
                              + ([f"made under style lock version {m.get('style_lock_version')}, the current one is {style_lock['version']}"]
                                 if style_lock.get("version") is not None and m.get("style_lock_version") != style_lock["version"] else [])),
    }
    r.update({c: looked[c] for c in LOOKED if looked and c in looked})
    if quality_gate:
        r["compliance_quality_gate"] = quality_gate
    return build_report(m["name"], r, tmall_rules.not_confirmed(rules), image_sha256=common.sha256(final), folder=folder)
