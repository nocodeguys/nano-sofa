"""Prompt sections — one function per paragraph.

Each function takes the PromptSpec and returns the lines it contributes
(possibly none). compile.py decides the order. Wording here is the
2026-10 baseline, reproduced byte for byte from the previous builders;
phase 2b edits it deliberately, with the goldens showing every change.

Conventions kept from the old builders so the goldens stay identical:
  * a section that starts a new block begins its first line with "\\n";
  * the product prompt says "slot N", the freeform prompt says
    "Attached image N" (to be unified in 2b).
"""
from __future__ import annotations

from app.core.prompt.spec import PromptSpec

Lines = list[str]


# ==========================================================================
# PRODUCT sections
# ==========================================================================
def task(s: PromptSpec) -> Lines:
    noun = s.product.noun
    if s.in_place_recolor:
        lines = [
            f"TASK — IMPORTANT, READ FIRST: This is an in-place RECOLORING of "
            f"slot 1, NOT a new product photograph. The output must be a "
            f"near-pixel-identical reproduction of slot 1 with ONLY the "
            f"upholstery color and material updated to the spec below. "
            f"\n\nPreserve from slot 1, identically:"
            f"\n• The EXACT crop and framing. If slot 1 is a tight macro "
            f"close-up of fabric, a corner, the headboard, or any partial view "
            f"of the {noun}, the output must be that same tight "
            f"close-up. Do NOT zoom out. Do NOT re-frame. Do NOT 'complete' "
            f"the {noun} if slot 1 shows only part of it. If slot 1 "
            f"shows a detail crop, the output is a detail crop."
            f"\n• The EXACT camera angle, distance, perspective, and pose."
            f"\n• The lighting direction and quality."
            f"\n• The image aspect ratio and the {noun}'s silhouette "
            f"within the frame."
            f"\n\nThe output is a recolored version of slot 1's photograph, "
            f"not a re-shoot of the {noun}."
        ]
        if s.scene.keep_source_scene:
            lines.append(
                f"\nBACKGROUND — IMPORTANT: Keep slot 1's EXACT background, "
                f"environment, floor, walls, surfaces, props, and lighting. Do NOT "
                f"restage the scene, do NOT swap to a studio cyclorama or any new "
                f"backdrop, do NOT add or remove props. The background pixels must "
                f"match slot 1 — only the {noun}'s upholstery changes."
            )
        return lines
    return [
        f"Edit the {noun} in the first reference image to produce a product "
        f"photography variant with the following specifications.",
        f"This is a {noun}, not any other furniture type. "
        f"Render anatomy and proportions consistent with a {noun}.",
    ]


def bed_frame_and_size(s: PromptSpec) -> Lines:
    if not s.product.is_bed:
        return []
    lines: Lines = []
    if s.product.frame_style:
        frame_label = s.product.frame_style.replace("-", " ")
        lines.append(
            f"\nFRAME STYLE: {frame_label} bed frame. "
            f"Render the frame silhouette consistent with a {frame_label} construction. "
            f"Do not invent footboards, posts, canopies, or storage drawers that are "
            f"not present in the base reference image and not stated here."
        )
    if s.product.configuration:
        lines.append(
            f"BED SIZE: {s.product.configuration}. "
            f"Maintain the proportions of a {s.product.configuration} bed."
        )
    return lines


def upholstery(s: PromptSpec) -> Lines:
    noun = s.product.noun
    surface_noun = "UPHOLSTERY / FRAME FINISH" if s.product.is_bed else "UPHOLSTERY"
    if s.in_place_recolor:
        lines = [
            f"\n{surface_noun}: Replace the upholstery COMPLETELY with "
            f"{s.colour.text} {s.material.noun}. None of slot 1's "
            f"original upholstery colour may remain — recolor every cushion and "
            f"upholstered surface of the {noun}. Keep the fabric weave and "
            f"sheen consistent with {s.material.noun}."
        ]
    else:
        lines = [f"\n{surface_noun}: {s.colour.text} {s.material.noun}."]
    if s.material.spec:
        lines.append(f"Texture detail: {s.material.spec}")
    return lines


def bedding(s: PromptSpec) -> Lines:
    if s.product.is_bed and s.product.bedding.strip():
        return [f"\nBEDDING & STYLING: {s.product.bedding.strip()}"]
    return []


def legs(s: PromptSpec) -> Lines:
    p = s.product
    noun = p.noun
    if p.has_leg_swap:
        leg_instruction = p.leg_instruction or (
            f"Replace ONLY the legs with the leg style shown in the reference image. "
            + (
                f"The {noun} has exactly {p.leg_count} legs. "
                if p.legs_visible else
                f"Apply the leg style consistent with the {noun}'s frame. "
            )
            + f"Do not add braces, brackets, or structural elements not present in the "
            f"leg reference. Match the {noun}'s perspective and scale. "
            f"Keep contact shadow consistent with the scene lighting direction. "
            f"Do not modify the {noun} frame, "
            + ("cushions, upholstery, or stitching." if not p.is_bed else "headboard, mattress, or bedding.")
        )
        leg_instruction = leg_instruction.replace("[leg_count]", str(p.leg_count))
        lines = [f"\nLEGS: {leg_instruction}"]
        if p.leg_explicit_descriptor:
            lines.append(
                f"Leg style description (use this alongside the reference image): "
                f"{p.leg_explicit_descriptor}"
            )
        return lines
    if p.legs_visible:
        return [
            f"\nLEGS: Preserve the existing leg style exactly. "
            f"The {noun} has exactly {p.leg_count} legs — "
            f"do not add, remove, or merge any legs."
        ]
    if p.is_bed:
        return [
            f"\nFRAME BASE: The {noun} sits on a frame without visible legs "
            f"(platform-style construction). Do not add visible legs, feet, posts, "
            f"or risers under the {noun}."
        ]
    return []


def material_macro(s: PromptSpec) -> Lines:
    if not (s.use_swatch_for_fabric and "material_macro" in s.slots):
        return []
    noun = s.product.noun
    swatch_slot = s.slots["material_macro"]
    if s.swatch_texture_only:
        return [
            f"\nMATERIAL TEXTURE AUTHORITY (slot {swatch_slot}): Slot "
            f"{swatch_slot} is a close-up photograph of the real target "
            f"fabric. Copy ONLY its microscopic yarn construction: strand, "
            f"nub or loop shape as actually present, real-world scale, density, "
            f"depth, gaps between yarns, pile direction and surface relief. "
            f"Do not invent loops or force a matte finish when the reference "
            f"shows a different construction or optical response. Apply that authentic surface "
            f"to every upholstered part of the {noun} in slot 1. "
            f"Preserve its true physical scale: fine textiles must merge into "
            f"dense tactile microdetail at normal product-photography distance, "
            f"never enlarged into a coarse repeating motif. 'Merge' describes "
            f"perceived scale only: do not blur, denoise or smooth away the crisp "
            f"high-frequency separation, fibre edges and micro-shadows. "
            f"\n\nCRITICAL ROLE SEPARATION: Slot 1 is the PRODUCT GEOMETRY "
            f"authority. Slot {swatch_slot} is the MATERIAL MICROSTRUCTURE "
            f"authority only. IGNORE the photographed colour, folds, scale, "
            f"lighting, shadows, crop, and perspective of slot {swatch_slot}. "
            f"The upholstery colour must remain exactly the selected colour: "
            f"{s.colour.text}. Do not copy the fold visible in the "
            f"swatch onto the furniture.\n\nMATERIAL DOMAIN MASK — HARD "
            f"REQUIREMENT: apply slot {swatch_slot}'s microstructure ONLY inside "
            f"the upholstered product surfaces from slot 1. Never apply it to "
            f"bedding, mattress, pillows, floor, wall, cyclorama, background, "
            f"shadow, or empty pixels. The cyclorama must be uniformly smooth "
            f"matte paint: absolutely no enlarged loops, weave, fabric relief, "
            f"textile pattern, projected texture, or fabric-shaped shadow outside "
            f"the product. Keep all reference roles independent; do not "
            f"blend visual properties across their domains."
        ]
    return [
        f"\nFABRIC / COLOR REFERENCE (slot {swatch_slot}): Slot "
        f"{swatch_slot} is the authoritative reference for the target "
        f"upholstery color, fabric weave, and surface texture. Copy ONLY "
        f"those properties and apply them to the upholstery surfaces of "
        f"the {noun} in slot 1. "
        f"\n\nSlot 1 is the FRAMING AUTHORITY. Slot {swatch_slot} is "
        f"the FABRIC AUTHORITY. Do NOT inherit camera angle, framing, "
        f"crop, distance, perspective, product pose, lighting setup, or "
        f"shadow direction from slot {swatch_slot}."
    ]


def colour_authority(s: PromptSpec) -> Lines:
    lines: Lines = []
    if "color_patch" in s.slots:
        patch_slot = s.slots["color_patch"]
        lines.append(
            f"\nCOLOUR AUTHORITY (slot {patch_slot}): Slot {patch_slot} is a flat, "
            f"evenly lit patch of the exact target upholstery colour "
            f"{s.colour.hex_upper}. It is the single authority for the "
            f"hue, saturation and lightness of the upholstery. Under the scene's "
            f"neutral key light the upholstery's mid-tones must match this patch; "
            f"highlights may be lighter and shadows darker, but the hue and the "
            f"overall depth of the colour must not shift. Slot {patch_slot} carries no "
            f"texture, geometry or lighting — copy nothing else from it, and never "
            f"apply it to the backdrop, bedding or floor."
        )
    if s.colour.dark:
        lines.append(
            f"\nDEEP-SHADE EXPOSURE — HARD REQUIREMENT: the selected upholstery "
            f"colour is a deep, dark shade. Keep it deep: do not lift it towards "
            f"mid-grey, do not desaturate it, and do not add a milky haze to make "
            f"the texture visible. Fabric relief must read through subtle specular "
            f"micro-highlights and slightly lighter raised fibres while recessed "
            f"areas stay close to the target colour. Expose for the {s.product.noun}, "
            f"not for the backdrop: a bright backdrop must never push the "
            f"upholstery lighter than the specified colour."
        )
    return lines


def material_angles(s: PromptSpec) -> Lines:
    angle_slots = [s.slots[role] for role in ("material_left", "material_right") if role in s.slots]
    if not angle_slots:
        return []
    slots_label = " and ".join(str(slot) for slot in angle_slots)
    noun = "Slots" if len(angle_slots) > 1 else "Slot"
    viewpoint_clause = (
        "show the same flat target fabric from opposing oblique viewpoints. "
        "Compare them to infer the stable three-dimensional yarn relief "
        "separately from angle-dependent brightness."
        if len(angle_slots) > 1 else
        "shows the same flat target fabric from an oblique viewpoint. Use it to "
        "infer the stable three-dimensional yarn relief separately from "
        "angle-dependent brightness."
    )
    return [
        f"\nFABRIC MULTI-ANGLE OPTICAL AUTHORITY ({noun.lower()} {slots_label}): "
        f"{noun} {slots_label} {viewpoint_clause} Preserve the "
        f"same fine nub and slub geometry in both bright and shaded orientations; "
        f"do not average the two views into a smooth surface. Reproduce the short "
        f"pile's reversible directional sheen: tiny fibres and raised yarn faces "
        f"catch pearly grazing highlights while recessed crossings retain narrow "
        f"micro-shadows. This evidence describes material optics only. Do not copy "
        f"the photographed colour, white background, crop, depth of field, camera "
        f"angle or light direction into the final composition. Keep the selected "
        f"upholstery colour and slot 1 geometry authoritative."
    ]


def material_behavior(s: PromptSpec) -> Lines:
    if "material_behavior" not in s.slots:
        return []
    behavior_slot = s.slots["material_behavior"]
    return [
        f"\nFABRIC LIGHT-RESPONSE AUTHORITY (slot {behavior_slot}): Slot "
        f"{behavior_slot} shows the same target fabric under grazing light "
        f"and across a curved or touched surface. Copy ONLY its optical "
        f"behaviour: the pile, nap or raised yarn changes local brightness according "
        f"to fibre lay, surface normal and light direction. Brushed or raised "
        f"fibres facing the light receive soft pearly highlights; fibres laid "
        f"away from it become gently darker. These irregular luminance shifts "
        f"must follow real curves, seams, folds and locally disturbed nap — they "
        f"are not a printed colour pattern and must never form repeating bands. "
        f"Keep the catalog lighting soft overall, but preserve a directional "
        f"grazing component across the upholstery so raised fibres cast tiny "
        f"self-shadows into the recessed weave. Render a delicate fuzzy rim at "
        f"light-facing curves and sparse satin micro-glints on individual fibres. "
        f"Do not flatten these into uniform roughness, and do not smooth the "
        f"surface into generic linen, foam or sponge. The weave keeps the same "
        f"fine physical scale around rounded edges and tufting without stretching. "
        f"Do not copy slot {behavior_slot}'s photographed colour, crop, fold, "
        f"camera angle, depth of field or scale. Keep the selected upholstery "
        f"colour authoritative."
    ]


def material_application(s: PromptSpec) -> Lines:
    if "material_application" not in s.slots:
        return []
    application_slot = s.slots["material_application"]
    return [
        f"\nMATERIAL EVIDENCE HIERARCHY — HARD REQUIREMENT: The physical "
        f"sample photographs in the preceding fabric slots are the absolute "
        f"authority for weave construction, pile size, irregularity, colour "
        f"response and directional sheen. Slot {application_slot} is secondary "
        f"context only and can never override or reinterpret those samples."
        f"\n\nFABRIC IN-USE SCALE CHECK (slot {application_slot}): "
        f"Slot {application_slot} shows a comparable fabric applied across "
        f"a complete upholstered furniture piece at normal viewing distance. Use ONLY the "
        f"attenuation and apparent scale of fine textile detail at that distance "
        f"— never the reference piece's "
        f"geometry, dimensions, seams, channeling, storage mechanism, room, "
        f"camera, colour or styling. At hero distance the fabric must read first "
        f"as a calm, continuous, finely tactile surface of the specified material. Local brightness "
        f"changes may follow surface curvature, grazing light and disturbed pile, "
        f"but must not become broad cloudy patches, panel-scale blotches, crushed-"
        f"velvet marbling, stains or a printed pattern. Do not turn the upholstery "
        f"into a different generic weave or a flat featureless textile. Do not copy any visual "
        f"feature from slot {application_slot} when it conflicts with the physical "
        f"sample slots. Slot 1 remains "
        f"the absolute product-geometry authority."
    ]


def view_consistency(s: PromptSpec) -> Lines:
    if not (s.scene.view_consistency and "scene" in s.slots):
        return []
    noun = s.product.noun
    return [
        f"\nROOM AND LIGHTING CONTINUITY: This {noun} is being "
        f"photographed in the EXACT same room as shown in the scene reference "
        f"image — the same wall paint, the same floor material, the same props, "
        f"the same windows, the same time of day, the same light source position. "
        f"Treat the scene reference as a fixed-pixel definition of the room. "
        f"The {noun}'s pose and camera angle come from the base image "
        f"(slot 1); the room and lighting come from the scene reference (slot {s.slots['scene']}). "
        f"Shadows on the {noun} fall in physically correct directions for "
        f"its new camera angle but originate from the same light source position "
        f"shown in the scene reference. Do not redesign the room, do not change "
        f"wall paint, floor, props, or window light direction."
    ]


def reference_lock(s: PromptSpec) -> Lines:
    if not s.reference_locked:
        return []
    noun = s.product.noun
    return [
        f"\nREFERENCE LOCK — IMPORTANT: An additional moodboard reference "
        f"photograph is attached to this request. That reference photograph "
        f"is the AUTHORITATIVE source of truth for the look of the output. "
        f"Match the reference EXACTLY on all of the following dimensions:"
        f"\n• CAMERA: identical camera angle, viewpoint, height, distance, "
        f"perspective, focal length / lens compression, framing, and crop. "
        f"If the reference is a tight detail or macro crop, the output is "
        f"the same tight crop — do not pull back to a hero shot."
        f"\n• LIGHTING: identical light direction, quality (hard/soft), "
        f"intensity, color temperature, time-of-day mood, and key/fill "
        f"ratio. Reproduce the reference's overall exposure and contrast."
        f"\n• SHADOWS: identical shadow direction, length, softness, and "
        f"density as cast in the reference photograph."
        f"\n• SCENE / BACKDROP: identical background, environment, props, "
        f"floor, walls, and any contextual scene elements visible in the "
        f"reference. Do not invent a new backdrop, do not swap to a "
        f"studio cyclorama, do not add props that aren't in the reference."
        f"\n• COLOR GRADE: identical overall color grade, white balance, "
        f"and post-processing mood."
        f"\nIGNORE any conflicting camera, lens, time-of-day, shadow, or "
        f"environment directives elsewhere in this prompt — the reference "
        f"photograph overrides them. The ONLY things you take from the "
        f"wizard instead of the reference are the upholstery color, "
        f"upholstery material, leg style (when specified), and product "
        f"size. The {noun} silhouette itself comes from slot 1."
    ]


def camera(s: PromptSpec) -> Lines:
    if s.reference_locked:
        return []
    noun = s.product.noun
    c = s.camera
    if c.preserve_from_base:
        return [
            f"\nCAMERA (slot 1 is authoritative): The camera angle, framing, "
            f"crop, distance, perspective, lens compression, and {noun} "
            f"silhouette of the output MUST match slot 1 exactly. Do NOT change "
            f"the camera position, the focal length, or the framing. Do NOT "
            f"'complete' the {noun} if slot 1 shows only a portion of it "
            f"— if slot 1 is a tight detail crop showing only fabric texture or "
            f"only one corner of the {noun}, the output is that same "
            f"tight crop. The output is a recoloring of slot 1, NOT a new "
            f"photograph of the {noun}."
        ]
    if c.is_detail:
        return [
            f"\nCAMERA: macro detail crop. Framing: {c.framing}. "
            f"Focal length equivalent {c.focal_mm} mm, {c.aperture} aperture, "
            f"shallow depth of field. The full {noun} must NOT be visible — "
            f"the frame is filled by the detail region only, with the rest of the "
            f"{noun} cropped out by the frame edge."
        ]
    angle_label = c.angle_label.replace("-", " ")
    return [
        f"\nCAMERA: {angle_label} view, approximately {c.degrees} degrees "
        f"from the left. "
        f"Focal length equivalent {c.focal_mm} mm, {c.aperture} aperture. "
        f"Framing: {c.framing}."
    ]


def catalog_contract(s: PromptSpec) -> Lines:
    return [f"\n{s.catalog_framing_contract}"] if s.catalog_framing_contract else []


def shadow(s: PromptSpec) -> Lines:
    if s.reference_locked:
        return []
    p, sc = s.product, s.scene
    if sc.shadow_direction and not sc.mode:
        text = (
            f"Shadow direction: the shadow cast by the {p.noun} falls at "
            f"{sc.shadow_direction} (clock position from the {p.noun}'s perspective)."
        )
        if p.legs_visible or p.has_leg_swap:
            text += " All leg contact shadows must be consistent with this direction."
        return [text]
    if sc.mode and (p.legs_visible or p.has_leg_swap):
        return [
            f"All leg contact shadows must be consistent with the shadow direction "
            f"described in the SCENE section."
        ]
    return []


def scene(s: PromptSpec) -> Lines:
    if s.reference_locked or s.scene.keep_source_scene:
        return []
    return [_scene_block(s)]


def _scene_block(s: PromptSpec) -> str:
    noun = s.product.noun
    sc = s.scene
    scene_slot = s.slots.get("scene")
    has_scene = scene_slot is not None
    lens_clause = f" Lens: {s.camera.lens_descriptor}." if s.camera.lens_descriptor else ""
    shadow_clause = (
        f" {sc.shadow_description[0].upper()}{sc.shadow_description[1:]}."
        if sc.shadow_description else ""
    )
    product_in_scene_clause = (
        f" The scene reference (slot {scene_slot}) shows this same {noun} "
        f"in a DIFFERENT upholstery colour: use it only for the room, floor, "
        f"walls, props, camera and lighting. Its upholstery colour and material "
        f"are wrong for this render — ignore them completely and use the "
        f"colour specified in the UPHOLSTERY section."
        if has_scene and sc.contains_product else ""
    )

    # ---- Legacy / unmigrated callers --------------------------------- #
    if not sc.mode:
        if has_scene:
            return (
                f"\nSCENE: Place the {noun} naturally within the scene shown in the "
                f"reference image (slot {scene_slot}). Match lighting direction, color "
                f"temperature, and floor material from the scene reference. The shadow "
                f"beneath the {noun} must fall in the same direction as all other "
                f"shadows in the scene.{product_in_scene_clause}"
            )
        return (
            f"\nSCENE: Neutral studio backdrop. Clean, professional e-commerce "
            f"photography background."
        )

    # ---- Packshot mode ----------------------------------------------- #
    if sc.mode == "packshot":
        tod_clause = f" Lighting: {sc.tod}." if sc.tod else ""
        scene_desc = sc.description or "neutral grey studio backdrop, packshot lighting"
        exposure_clause = "" if not s.product.is_bed else (
            " WHITE-TEXTILE EXPOSURE — PASS/FAIL REQUIREMENT: expose for the "
            "white bedding, not for the backdrop, using a neutral D55 white balance. "
            "The duvet, sheets and pillows must remain visibly darker than the brightest "
            "part of the cyclorama. Preserve separate tonal bands in every fold, seam, "
            "piping edge and weave: broad white textile areas live around RGB 232-244, "
            "fold highlights may reach RGB 246, and no fabric-sized region may reach "
            "RGB 250-255. Pure white is permitted only in pin-point reflections. The "
            "result must still show textile relief when viewed as a small catalog tile; "
            "a featureless white duvet is an exposure failure. Do not compensate by "
            "greying, yellowing or darkening the canonical backdrop and do not create "
            "a bright halo around the product."
        )
        if s.camera.is_detail:
            return (
                f"\nSCENE (detail crop): The background is the {noun}'s own "
                f"upholstery surface, completely out of focus at macro distance — "
                f"soft, blurred, no studio backdrop visible, no horizon, no contact "
                f"shadow, no environment objects. The frame is filled by the detail "
                f"region in sharp focus; everything beyond ~5 cm depth is rendered "
                f"as smooth, defocused bokeh of the same fabric color."
                f"{lens_clause}"
                + (
                    f"\n\nNOTE ON BACKDROP REFERENCE: A cyclorama reference image is "
                    f"attached (slot {scene_slot}). At macro distance the backdrop is not in "
                    f"the frame — disregard the backdrop reference entirely for this "
                    f"render. Use slot 1 only for the {noun}'s color, material, "
                    f"and detail-region geometry."
                    if has_scene else ""
                )
            )
        if has_scene and sc.contains_product:
            return (
                f"\nSCENE (packshot): {scene_desc}."
                f"{tod_clause}"
                f"{lens_clause}"
                f"{shadow_clause}"
                f"{exposure_clause}"
                f" No environment objects, no room context — product only on the backdrop."
                f"\n\nBACKDROP REFERENCE (slot {scene_slot}): slot {scene_slot} is an "
                f"earlier render of this same {noun} on the target backdrop, in a "
                f"DIFFERENT upholstery colour. Match its backdrop tone, luminance field, "
                f"white balance, floor-to-wall blend, camera and contact shadow exactly. "
                f"Its upholstery colour and material are wrong for this render: ignore "
                f"them completely and use only the colour specified in the UPHOLSTERY "
                f"section. Every output pixel outside the product must match the backdrop "
                f"of slot {scene_slot}; the product itself comes from slot 1."
            )
        if has_scene:
            return (
                f"\nSCENE (packshot): {scene_desc}."
                f"{tod_clause}"
                f"{lens_clause}"
                f"{shadow_clause}"
                f"{exposure_clause}"
                f" No environment objects, no room context — product only on the backdrop."
                f"\n\nBACKDROP / CYCLORAMA REFERENCE: An additional reference image is "
                f"attached (slot {scene_slot}) that shows the canonical cyclorama look for this "
                f"shoot. Match its backdrop tone, restrained luminance field, neutral "
                f"white balance, and floor-to-wall seamless blend exactly. The reference "
                f"is an EMPTY studio plate, so create only the small contact shadow "
                f"specified above; do not invent a broad cast shadow. Use ONLY the "
                f"backdrop characteristics from this "
                f"reference — do not copy the product, the camera angle, the framing, "
                f"or any geometry from it. The {noun}'s pose and angle come "
                f"from the base image (slot 1). The cyclorama is a separate physical "
                f"surface from the product: it must remain perfectly smooth and must "
                f"not inherit, project, magnify, echo, or cast a silhouette of any "
                f"fabric texture supplied in another reference slot.\n\nSOURCE "
                f"BACKGROUND DISCARD — HARD REQUIREMENT: Treat every pixel outside "
                f"the product silhouette in slot 1 as transparent and unusable. "
                f"Completely discard slot 1's background, floor, cast shadow, halo, "
                f"lighting gradient, compression noise, stains and edge glow. Never "
                f"average, blend or reconcile slot 1's background with slot {scene_slot}. Every "
                f"output pixel outside the product and its small new contact shadow "
                f"must come only from the clean empty studio plate in slot {scene_slot}."
            )
        return (
            f"\nSCENE (packshot): {scene_desc}."
            f"{tod_clause}"
            f"{lens_clause}"
            f"{shadow_clause}"
            f"{exposure_clause}"
            f" No environment objects, no room context — product only on the backdrop."
        )

    # ---- Lifestyle mode ---------------------------------------------- #
    tod_clause = f" Time of day and lighting quality: {sc.tod}." if sc.tod else ""
    scene_desc = sc.description or "interior setting"
    if s.camera.is_detail:
        return (
            f"\nSCENE (detail crop in {scene_desc}): The background is the "
            f"{noun}'s own upholstery surface, completely out of focus "
            f"at macro distance — no room interior visible in the frame. The "
            f"frame is filled by the detail region in sharp focus; everything "
            f"beyond ~5 cm depth is smooth defocused bokeh of the same fabric. "
            f"The ambient light color temperature and direction come from the "
            f"surrounding {scene_desc}, not from a studio strobe."
            f"{tod_clause}"
            f"{lens_clause}"
        )
    if has_scene:
        placement = (
            f"Place the {noun} naturally within the scene shown in the "
            f"reference image (slot {scene_slot}). Match lighting direction, color "
            f"temperature, and floor material from the scene reference."
            f"{product_in_scene_clause}"
        )
    else:
        placement = (
            f"Place the {noun} naturally within {scene_desc}. "
            f"Render convincing room context — floor, walls, and ambient props "
            f"consistent with that environment. The environment should look like a "
            f"real photographed interior, not a studio backdrop."
        )
    return (
        f"\nSCENE (lifestyle): {placement}"
        f"{tod_clause}"
        f"{lens_clause}"
        f"{shadow_clause}"
        f" The shadow beneath the {noun} must fall in the same direction "
        f"as all other shadows in the scene."
    )


def preserve(s: PromptSpec) -> Lines:
    if not s.product.preserve:
        return []
    readable = [p.replace("_", " ") for p in s.product.preserve]
    lines = [f"\nPRESERVE — do NOT change any of the following: " + ", ".join(readable) + "."]
    if s.product.legs_visible:
        lines.append(
            f"The {s.product.noun} has exactly {s.product.leg_count} legs. "
            f"Leg count is {s.product.leg_count} — do not add, remove, or merge legs."
        )
    return lines


def output_style(s: PromptSpec) -> Lines:
    if s.in_place_recolor:
        return [
            f"\nOUTPUT STYLE: Match the photographic style, sharpness, color "
            f"grading, and framing of slot 1. The output is a recoloring of "
            f"slot 1's photograph, not a re-shoot."
        ]
    return [f"\nOUTPUT STYLE: {s.output_style}"]


def negatives(s: PromptSpec) -> Lines:
    items = list(s.material.avoid)
    p = s.product
    if p.is_bed and not p.legs_visible and not p.has_leg_swap:
        items = [
            "added legs",
            "added feet",
            "added posts",
            "added risers under the bed",
            "frame raised on visible supports",
        ] + items
    if not items:
        return []
    return [f"\nNEGATIVE (must not appear in output): " + "; ".join(items) + "."]


def notes(s: PromptSpec) -> Lines:
    return [f"\nADDITIONAL NOTES: {s.notes}"] if s.notes else []


# ==========================================================================
# FREEFORM (editorial) sections
# ==========================================================================
def ed_task(s: PromptSpec) -> Lines:
    return [
        "TASK: Create a brand-new editorial photograph from scratch based on "
        "the brief below. There is no base product to preserve — full "
        "creative freedom within the art direction."
    ]


def ed_references(s: PromptSpec) -> Lines:
    lines: Lines = []
    slots = s.slots
    macro_slot = slots.get("material_macro")
    if macro_slot:
        lines.append(
            f"Attached image {macro_slot} is a close-up photograph of the real "
            "target upholstery fabric. Copy ONLY its yarn construction, texture "
            "scale and surface relief onto every upholstered piece; ignore its "
            "photographed colour, crop, fold and lighting."
        )
    patch_slot = slots.get("color_patch")
    if patch_slot:
        hex_label = s.colour.hex_upper
        lines.append(
            f"Attached image {patch_slot} is a flat, evenly lit patch of the exact "
            f"target upholstery colour{(' ' + hex_label) if hex_label else ''}. It is "
            "the single authority for the hue, saturation and lightness of the hero "
            "upholstery: under the scene's key light its mid-tones must match this "
            "patch. It carries no texture, geometry or lighting — copy nothing else "
            "from it. The fabric photographs show a different colour and contribute "
            "texture only."
        )
    angle_slots = [slots[role] for role in ("material_left", "material_right") if role in slots]
    if angle_slots:
        plural = len(angle_slots) > 1
        label = " and ".join(str(slot) for slot in angle_slots)
        viewpoint = "opposing oblique viewpoints" if plural else "an oblique viewpoint"
        lines.append(
            f"Attached image{'s' if plural else ''} {label} show{'' if plural else 's'} "
            f"the same fabric from {viewpoint}: use "
            f"{'them' if plural else 'it'} only for how its pile, nubs and sheen "
            "respond to light from the side; ignore "
            f"{'their' if plural else 'its'} colour, crop and background."
        )
    behavior_slot = slots.get("material_behavior")
    if behavior_slot:
        lines.append(
            f"Attached image {behavior_slot} shows the same fabric under grazing light "
            "across a curved, touched surface: copy only that optical behaviour — "
            "raised fibres facing the light brighten, fibres laid away darken, and "
            "these shifts follow real curves and folds, never a printed pattern."
        )
    application_slot = slots.get("material_application")
    if application_slot:
        lines.append(
            f"Attached image {application_slot} shows a comparable fabric on a whole "
            "furniture piece at normal viewing distance: use it only to judge how "
            "fine the texture reads from the camera — never its geometry, room, "
            "colour or styling, and never let it override the physical sample "
            "photographs."
        )
    mood_slots = sorted(
        number for role, number in slots.items() if role.startswith("extra_reference_")
    )
    if mood_slots:
        label = (
            f"image {mood_slots[0]}" if len(mood_slots) == 1
            else f"images {mood_slots[0]}–{mood_slots[-1]}"
        )
        lines.append(
            f"Use attached {label} as loose mood and styling "
            "inspiration only — do not copy them literally."
        )
    return lines


def ed_brief(s: PromptSpec) -> Lines:
    return ["", f"BRIEF: {s.editorial.brief.strip()}", ""]


def ed_direction(s: PromptSpec) -> Lines:
    lines: Lines = []
    e, sc, c = s.editorial, s.scene, s.camera
    if e.art_direction:
        lines.append(f"ART DIRECTION: {e.art_direction}.")
    if sc.setting_text:
        lines.append(f"SETTING: {sc.setting_text}.")
    if sc.light_text:
        lines.append(f"LIGHT: {sc.light_text}.")
    cam_bits = [bit for bit in (c.lens_descriptor, c.height_phrase) if bit]
    if cam_bits:
        lines.append("CAMERA: " + "; ".join(cam_bits) + ".")
    if s.colour.text:
        lines.append(
            f"COLOR DIRECTION (hard constraint): the hero furniture piece and "
            f"the dominant tone of the frame are {s.colour.text}; the supporting "
            "palette stays harmonious and neutral around it."
        )
    if s.material.noun:
        lines.append(
            f"TEXTILE DIRECTION (hard constraint): every upholstered "
            f"furniture piece in the frame is upholstered in {s.material.noun}. "
            f"Fabric spec: {s.material.spec}"
        )
        if s.material.avoid:
            lines.append("TEXTILE — must not appear: " + "; ".join(s.material.avoid) + ".")
    if e.people_text:
        lines.append(f"PEOPLE: {e.people_text}")
    if e.seed.strip():
        lines.append(f"seed hint: {e.seed.strip()}")
    return lines


def ed_output(s: PromptSpec) -> Lines:
    negative = (
        "NEGATIVE (must not appear in output): any rendered text, typography, "
        "logos, watermarks or UI elements — leave clean negative space where "
        "a masthead or headline would be placed."
    )
    if not s.editorial.people_text:
        negative += " No people, no human figures, no faces, no body parts."
    return [
        "",
        "OUTPUT STYLE: professional editorial furniture-brand photography, "
        "photorealistic, coherent high-end art direction, natural color grading.",
        negative,
    ]
