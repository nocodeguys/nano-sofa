"""FROZEN copy of the prompt builders as of b41c860 — test oracle only.

Phase 2a moved the prompt assembly into app/core/prompt/. This file keeps
the previous implementation verbatim so tests/test_prompt_compiler_parity.py
can prove the new compiler emits byte-identical text across a grid of
requests. Do not edit; delete it when phase 2b deliberately changes wording.
"""
from __future__ import annotations

from typing import Optional

from app.core.generator import (
    GenerationRequest,
    is_dark_hex,
    plan_reference_slots,
    slot_numbers,
)
from studio.mappings import (
    _EDITORIAL_STYLES,
    _ENV_TO_SCENE,
    _HEIGHT_TO_PHRASE,
    _LENS_TO_PROMPT,
    _PEOPLE_TO_PROMPT,
    _TOD_TO_PROMPT,
)


def _build_scene_block(
    req: GenerationRequest, product_noun: str, slots: Optional[dict[str, int]] = None
) -> str:
    """
    Build the SCENE section as a narrative paragraph.

    Two modes are selected by req.env_mode:
      - "packshot"  → product on a neutral/cyclorama backdrop, no room context.
      - "lifestyle" → product placed inside a real interior; environment is
                      the primary creative instruction.

    Lens / time-of-day / shadow descriptors are woven into the paragraph as
    natural modifiers (Google's prompting guides recommend narrative prose
    over disconnected key:value fragments for image generation).

    When env_mode is empty the function falls back to the legacy single-line
    behavior so callers that haven't migrated to the structured fields yet
    keep working — but without the "Neutral studio backdrop" contradiction
    against the chosen environment (the legacy line is replaced by the
    scene-reference branch only).
    """
    if slots is None:
        slots = slot_numbers(plan_reference_slots(req))
    scene_slot = slots.get("scene")
    has_scene = scene_slot is not None
    lens_clause = f" Lens: {req.lens_descriptor}." if req.lens_descriptor else ""
    shadow_clause = (
        f" {req.shadow_description[0].upper()}{req.shadow_description[1:]}."
        if req.shadow_description else ""
    )
    # Variant sets reuse the anchor render as the room reference: it shows
    # this same product in a different colour, and the model must be told so.
    product_in_scene_clause = (
        f" The scene reference (slot {scene_slot}) shows this same {product_noun} "
        f"in a DIFFERENT upholstery colour: use it only for the room, floor, "
        f"walls, props, camera and lighting. Its upholstery colour and material "
        f"are wrong for this render — ignore them completely and use the "
        f"colour specified in the UPHOLSTERY section."
        if has_scene and req.scene_contains_product else ""
    )

    # ---- Legacy / unmigrated callers --------------------------------- #
    if not req.env_mode:
        if has_scene:
            return (
                f"\nSCENE: Place the {product_noun} naturally within the scene shown in the "
                f"reference image (slot {scene_slot}). Match lighting direction, color "
                f"temperature, and floor material from the scene reference. The shadow "
                f"beneath the {product_noun} must fall in the same direction as all other "
                f"shadows in the scene.{product_in_scene_clause}"
            )
        return (
            f"\nSCENE: Neutral studio backdrop. Clean, professional e-commerce "
            f"photography background."
        )

    # ---- Packshot mode ----------------------------------------------- #
    if req.env_mode == "packshot":
        tod_clause = f" Lighting: {req.tod_description}." if req.tod_description else ""
        scene_desc = req.env_description or "neutral grey studio backdrop, packshot lighting"
        # The white-bedding exposure rule only makes sense for beds; on a
        # sofa it talks about a duvet that isn't there and drags the exposure
        # of dark upholstery towards the backdrop.
        exposure_clause = "" if req.product_type != "bed" else (
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
        is_detail = req.shot_type in ("detail_fabric", "detail_corner")
        # Detail crop: at macro distance the cyclorama sweep, top-light
        # gradient, and contact shadow are not in the frame — emitting the
        # full cyclorama spec re-anchors the model to a hero packshot and
        # cancels the detail crop. Emit a minimal OOF-background line and
        # explicitly tell the model to disregard any attached cyclorama
        # reference (the wizard always attaches one for packshot shots).
        if is_detail:
            return (
                f"\nSCENE (detail crop): The background is the {product_noun}'s own "
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
                    f"render. Use slot 1 only for the {product_noun}'s color, material, "
                    f"and detail-region geometry."
                    if has_scene else ""
                )
            )
        # When a scene reference image is attached for a packshot, it's the
        # curated cyclorama reference (not a lifestyle scene). Tell the model
        # to copy backdrop characteristics — tone, top-light gradient, shadow
        # quality, floor blend — from the reference, NOT to place the product
        # "in" the reference scene.
        if has_scene and req.scene_contains_product:
            # A rendered product photo is NOT an empty studio plate: claiming
            # it is makes the model copy the old upholstery colour (the
            # variant-set colour-drift bug). Describe it truthfully.
            return (
                f"\nSCENE (packshot): {scene_desc}."
                f"{tod_clause}"
                f"{lens_clause}"
                f"{shadow_clause}"
                f"{exposure_clause}"
                f" No environment objects, no room context — product only on the backdrop."
                f"\n\nBACKDROP REFERENCE (slot {scene_slot}): slot {scene_slot} is an "
                f"earlier render of this same {product_noun} on the target backdrop, in a "
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
                f"or any geometry from it. The {product_noun}'s pose and angle come "
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
    tod_clause = (
        f" Time of day and lighting quality: {req.tod_description}."
        if req.tod_description else ""
    )
    scene_desc = req.env_description or "interior setting"
    is_detail = req.shot_type in ("detail_fabric", "detail_corner")
    # Detail crop in a lifestyle env: at macro distance the room isn't in
    # the frame. Emit OOF fabric background but keep the lighting hue/temp
    # so the room's light quality still influences the detail crop.
    if is_detail:
        return (
            f"\nSCENE (detail crop in {scene_desc}): The background is the "
            f"{product_noun}'s own upholstery surface, completely out of focus "
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
            f"Place the {product_noun} naturally within the scene shown in the "
            f"reference image (slot {scene_slot}). Match lighting direction, color "
            f"temperature, and floor material from the scene reference."
            f"{product_in_scene_clause}"
        )
    else:
        placement = (
            f"Place the {product_noun} naturally within {scene_desc}. "
            f"Render convincing room context — floor, walls, and ambient props "
            f"consistent with that environment. The environment should look like a "
            f"real photographed interior, not a studio backdrop."
        )

    return (
        f"\nSCENE (lifestyle): {placement}"
        f"{tod_clause}"
        f"{lens_clause}"
        f"{shadow_clause}"
        f" The shadow beneath the {product_noun} must fall in the same direction "
        f"as all other shadows in the scene."
    )


def _build_prompt_text(
    req: GenerationRequest, slots: Optional[dict[str, int]] = None
) -> str:
    """
    Assemble the full prompt text from the request fields.

    `slots` maps reference roles to the 1-based slot numbers that were
    ACTUALLY attached (see plan_reference_slots). When omitted it is derived
    from the request, which is what tests and dry runs do; generate() always
    passes the loaded list so the prompt never names a missing image.
    Branches on req.product_type so anatomy nouns are correct (sofa vs bed)
    and so leg-count emphasis is OMITTED entirely when leg_count is 0
    (the proximate cause of the model adding legs to platform beds).
    """
    # Freeform/editorial requests carry their complete prompt verbatim.
    if req.freeform_prompt:
        return req.freeform_prompt

    if slots is None:
        slots = slot_numbers(plan_reference_slots(req))
    lines: list[str] = []

    is_bed = req.product_type == "bed"
    product_noun = "bed" if is_bed else "sofa"
    legs_visible = req.leg_count > 0
    has_leg_swap = bool(req.leg_id or req.leg_explicit_descriptor)

    # In-place recoloring mode is active when the caller wants every aspect of
    # slot 1 preserved except the upholstery (Fotosesja packshot pass). The
    # lifestyle pass also sets preserve_camera_from_base but uses env_mode
    # "lifestyle" — those renders intentionally swap the backdrop, so they
    # should NOT use the strict in-place TASK framing. Gated by
    # strict_in_place_recolor so the wizard "preserve camera" toggle (which
    # also sets preserve_camera_from_base) does NOT freeze the backdrop.
    in_place_recolor = (
        req.strict_in_place_recolor
        and req.preserve_camera_from_base
        and (req.env_mode == "packshot" or req.keep_source_scene)
    )

    # ------------------------------------------------------------------ #
    # Primary instruction
    # ------------------------------------------------------------------ #
    if in_place_recolor:
        # Strong in-place framing — fights the model's prior toward "make a
        # new hero product photo" which causes the failure mode where tight
        # detail close-ups get re-framed into full hero shots. Lead with this
        # so it sets the prior before any other instruction lands.
        lines.append(
            f"TASK — IMPORTANT, READ FIRST: This is an in-place RECOLORING of "
            f"slot 1, NOT a new product photograph. The output must be a "
            f"near-pixel-identical reproduction of slot 1 with ONLY the "
            f"upholstery color and material updated to the spec below. "
            f"\n\nPreserve from slot 1, identically:"
            f"\n• The EXACT crop and framing. If slot 1 is a tight macro "
            f"close-up of fabric, a corner, the headboard, or any partial view "
            f"of the {product_noun}, the output must be that same tight "
            f"close-up. Do NOT zoom out. Do NOT re-frame. Do NOT 'complete' "
            f"the {product_noun} if slot 1 shows only part of it. If slot 1 "
            f"shows a detail crop, the output is a detail crop."
            f"\n• The EXACT camera angle, distance, perspective, and pose."
            f"\n• The lighting direction and quality."
            f"\n• The image aspect ratio and the {product_noun}'s silhouette "
            f"within the frame."
            f"\n\nThe output is a recolored version of slot 1's photograph, "
            f"not a re-shoot of the {product_noun}."
        )
        if req.keep_source_scene:
            lines.append(
                f"\nBACKGROUND — IMPORTANT: Keep slot 1's EXACT background, "
                f"environment, floor, walls, surfaces, props, and lighting. Do NOT "
                f"restage the scene, do NOT swap to a studio cyclorama or any new "
                f"backdrop, do NOT add or remove props. The background pixels must "
                f"match slot 1 — only the {product_noun}'s upholstery changes."
            )
    else:
        lines.append(
            f"Edit the {product_noun} in the first reference image to produce a product "
            f"photography variant with the following specifications."
        )
        lines.append(
            f"This is a {product_noun}, not any other furniture type. "
            f"Render anatomy and proportions consistent with a {product_noun}."
        )

    # ------------------------------------------------------------------ #
    # Bed-specific: frame style + size context
    # ------------------------------------------------------------------ #
    if is_bed:
        if req.frame_style:
            frame_label = req.frame_style.replace("-", " ")
            lines.append(
                f"\nFRAME STYLE: {frame_label} bed frame. "
                f"Render the frame silhouette consistent with a {frame_label} construction. "
                f"Do not invent footboards, posts, canopies, or storage drawers that are "
                f"not present in the base reference image and not stated here."
            )
        if req.sofa_configuration:
            lines.append(
                f"BED SIZE: {req.sofa_configuration}. "
                f"Maintain the proportions of a {req.sofa_configuration} bed."
            )

    # ------------------------------------------------------------------ #
    # Upholstery / surface
    # ------------------------------------------------------------------ #
    surface_noun = "UPHOLSTERY / FRAME FINISH" if is_bed else "UPHOLSTERY"
    if in_place_recolor:
        lines.append(
            f"\n{surface_noun}: Replace the upholstery COMPLETELY with "
            f"{req.upholstery_color} {req.upholstery_material}. None of slot 1's "
            f"original upholstery colour may remain — recolor every cushion and "
            f"upholstered surface of the {product_noun}. Keep the fabric weave and "
            f"sheen consistent with {req.upholstery_material}."
        )
    else:
        lines.append(
            f"\n{surface_noun}: {req.upholstery_color} {req.upholstery_material}."
        )
    if req.texture_notes:
        lines.append(f"Texture detail: {req.texture_notes}")

    # ------------------------------------------------------------------ #
    # Bedding & styling block — bed-only. Populated by the wizard's
    # section 10. Tells the model exactly what textiles are on the bed,
    # how tidy they should look, and how many extra props belong in
    # the frame. Skipped for sofas and for empty descriptions.
    # ------------------------------------------------------------------ #
    if is_bed and req.bedding_description.strip():
        lines.append(f"\nBEDDING & STYLING: {req.bedding_description.strip()}")

    # ------------------------------------------------------------------ #
    # Legs — only when relevant (leg_count > 0 OR explicit leg swap)
    # ------------------------------------------------------------------ #
    if has_leg_swap:
        # User picked a specific leg style from the manifest
        leg_instruction = req.leg_instruction or (
            f"Replace ONLY the legs with the leg style shown in the reference image. "
            + (
                f"The {product_noun} has exactly {req.leg_count} legs. "
                if legs_visible else
                f"Apply the leg style consistent with the {product_noun}'s frame. "
            )
            + f"Do not add braces, brackets, or structural elements not present in the "
            f"leg reference. Match the {product_noun}'s perspective and scale. "
            f"Keep contact shadow consistent with the scene lighting direction. "
            f"Do not modify the {product_noun} frame, "
            + ("cushions, upholstery, or stitching." if not is_bed else "headboard, mattress, or bedding.")
        )
        leg_instruction = leg_instruction.replace("[leg_count]", str(req.leg_count))
        lines.append(f"\nLEGS: {leg_instruction}")
        if req.leg_explicit_descriptor:
            lines.append(
                f"Leg style description (use this alongside the reference image): "
                f"{req.leg_explicit_descriptor}"
            )
    elif legs_visible:
        # Legs are visible in the base photo and we're keeping them
        lines.append(
            f"\nLEGS: Preserve the existing leg style exactly. "
            f"The {product_noun} has exactly {req.leg_count} legs — "
            f"do not add, remove, or merge any legs."
        )
    else:
        # No legs visible (typical platform bed). DO NOT mention legs at all —
        # mentioning leg-count even as "0 legs" can prime the model to add them.
        if is_bed:
            lines.append(
                f"\nFRAME BASE: The {product_noun} sits on a frame without visible legs "
                f"(platform-style construction). Do not add visible legs, feet, posts, "
                f"or risers under the {product_noun}."
            )

    # ------------------------------------------------------------------ #
    # Swatch reference instruction — when an additional reference image is
    # being passed as the canonical fabric/color source (set by the packshot
    # batch pass), make the role explicit so the model copies fabric appearance
    # only and not geometry.
    # ------------------------------------------------------------------ #
    if req.use_swatch_for_fabric and "material_macro" in slots:
        swatch_slot = slots["material_macro"]
        if req.swatch_texture_only:
            lines.append(
                f"\nMATERIAL TEXTURE AUTHORITY (slot {swatch_slot}): Slot "
                f"{swatch_slot} is a close-up photograph of the real target "
                f"fabric. Copy ONLY its microscopic yarn construction: strand, "
                f"nub or loop shape as actually present, real-world scale, density, "
                f"depth, gaps between yarns, pile direction and surface relief. "
                f"Do not invent loops or force a matte finish when the reference "
                f"shows a different construction or optical response. Apply that authentic surface "
                f"to every upholstered part of the {product_noun} in slot 1. "
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
                f"{req.upholstery_color}. Do not copy the fold visible in the "
                f"swatch onto the furniture.\n\nMATERIAL DOMAIN MASK — HARD "
                f"REQUIREMENT: apply slot {swatch_slot}'s microstructure ONLY inside "
                f"the upholstered product surfaces from slot 1. Never apply it to "
                f"bedding, mattress, pillows, floor, wall, cyclorama, background, "
                f"shadow, or empty pixels. The cyclorama must be uniformly smooth "
                f"matte paint: absolutely no enlarged loops, weave, fabric relief, "
                f"textile pattern, projected texture, or fabric-shaped shadow outside "
                f"the product. Keep all reference roles independent; do not "
                f"blend visual properties across their domains."
            )
        else:
            lines.append(
                f"\nFABRIC / COLOR REFERENCE (slot {swatch_slot}): Slot "
                f"{swatch_slot} is the authoritative reference for the target "
                f"upholstery color, fabric weave, and surface texture. Copy ONLY "
                f"those properties and apply them to the upholstery surfaces of "
                f"the {product_noun} in slot 1. "
                f"\n\nSlot 1 is the FRAMING AUTHORITY. Slot {swatch_slot} is "
                f"the FABRIC AUTHORITY. Do NOT inherit camera angle, framing, "
                f"crop, distance, perspective, product pose, lighting setup, or "
                f"shadow direction from slot {swatch_slot}."
            )

    # ------------------------------------------------------------------ #
    # Colour authority — a flat patch of the exact target colour. Text
    # alone ("deep bottle green (hex #2E3B2C)") drifts on dark shades; a
    # pixel reference does not. Deep shades additionally get an exposure
    # clause so the white backdrop doesn't lift them to grey.
    # ------------------------------------------------------------------ #
    if "color_patch" in slots:
        patch_slot = slots["color_patch"]
        lines.append(
            f"\nCOLOUR AUTHORITY (slot {patch_slot}): Slot {patch_slot} is a flat, "
            f"evenly lit patch of the exact target upholstery colour "
            f"{req.upholstery_hex.strip().upper()}. It is the single authority for the "
            f"hue, saturation and lightness of the upholstery. Under the scene's "
            f"neutral key light the upholstery's mid-tones must match this patch; "
            f"highlights may be lighter and shadows darker, but the hue and the "
            f"overall depth of the colour must not shift. Slot {patch_slot} carries no "
            f"texture, geometry or lighting — copy nothing else from it, and never "
            f"apply it to the backdrop, bedding or floor."
        )
    if is_dark_hex(req.upholstery_hex):
        lines.append(
            f"\nDEEP-SHADE EXPOSURE — HARD REQUIREMENT: the selected upholstery "
            f"colour is a deep, dark shade. Keep it deep: do not lift it towards "
            f"mid-grey, do not desaturate it, and do not add a milky haze to make "
            f"the texture visible. Fabric relief must read through subtle specular "
            f"micro-highlights and slightly lighter raised fibres while recessed "
            f"areas stay close to the target colour. Expose for the {product_noun}, "
            f"not for the backdrop: a bright backdrop must never push the "
            f"upholstery lighter than the specified colour."
        )

    angle_slots = [slots[role] for role in ("material_left", "material_right") if role in slots]
    if angle_slots:
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
        lines.append(
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
        )

    if "material_behavior" in slots:
        behavior_slot = slots["material_behavior"]
        lines.append(
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
        )

    if "material_application" in slots:
        application_slot = slots["material_application"]
        lines.append(
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
        )

    # ------------------------------------------------------------------ #
    # View-consistency instruction — when the caller wants the model to
    # render the product at a DIFFERENT angle than the scene reference,
    # while keeping every room detail (walls, floor, props, lighting)
    # identical to the scene reference. Used by the lifestyle pair pass.
    # ------------------------------------------------------------------ #
    if req.view_consistency and "scene" in slots:
        lines.append(
            f"\nROOM AND LIGHTING CONTINUITY: This {product_noun} is being "
            f"photographed in the EXACT same room as shown in the scene reference "
            f"image — the same wall paint, the same floor material, the same props, "
            f"the same windows, the same time of day, the same light source position. "
            f"Treat the scene reference as a fixed-pixel definition of the room. "
            f"The {product_noun}'s pose and camera angle come from the base image "
            f"(slot 1); the room and lighting come from the scene reference (slot {slots['scene']}). "
            f"Shadows on the {product_noun} fall in physically correct directions for "
            f"its new camera angle but originate from the same light source position "
            f"shown in the scene reference. Do not redesign the room, do not change "
            f"wall paint, floor, props, or window light direction."
        )

    # ------------------------------------------------------------------ #
    # Reference-lock mode — user uploaded a moodboard reference (section
    # 09) and toggled "Użyj referencji jako wzorca" so the reference is
    # the source of truth for camera, lighting, scene, and shadows. We
    # emit a strong directive here and short-circuit the wizard-driven
    # CAMERA / shadow / SCENE blocks below so they don't fight the ref.
    # Variant attributes (color, material, legs, size) still apply — the
    # whole point of this mode is "show my color in this reference's look",
    # not "ignore everything and clone the reference."
    # ------------------------------------------------------------------ #
    reference_locked = bool(req.lock_to_reference and "extra_reference_1" in slots)
    if reference_locked:
        lines.append(
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
            f"size. The {product_noun} silhouette itself comes from slot 1."
        )

    # ------------------------------------------------------------------ #
    # Camera angle — either preserved from the base image (photoshoot
    # session mode, where each render's correct angle is already in its
    # own base image) or stated explicitly from the wizard's cam preset.
    # ------------------------------------------------------------------ #
    if reference_locked:
        # Camera comes from the moodboard reference — skip the wizard block.
        pass
    elif req.preserve_camera_from_base:
        lines.append(
            f"\nCAMERA (slot 1 is authoritative): The camera angle, framing, "
            f"crop, distance, perspective, lens compression, and {product_noun} "
            f"silhouette of the output MUST match slot 1 exactly. Do NOT change "
            f"the camera position, the focal length, or the framing. Do NOT "
            f"'complete' the {product_noun} if slot 1 shows only a portion of it "
            f"— if slot 1 is a tight detail crop showing only fabric texture or "
            f"only one corner of the {product_noun}, the output is that same "
            f"tight crop. The output is a recoloring of slot 1, NOT a new "
            f"photograph of the {product_noun}."
        )
    else:
        angle_label = req.camera_angle.replace("-", " ")
        is_detail = req.shot_type in ("detail_fabric", "detail_corner")
        if is_detail:
            # Detail crop: lead with the framing instruction (the only thing
            # that matters at macro distance) and skip the yaw line entirely.
            # Yaw + "X degrees from the left" at macro reads as a centered
            # hero shot to the model and overrides the crop — the failure
            # mode behind the "can't generate detail photo" bug.
            lines.append(
                f"\nCAMERA: macro detail crop. Framing: {req.framing}. "
                f"Focal length equivalent {req.focal_length_mm} mm, {req.aperture} aperture, "
                f"shallow depth of field. The full {product_noun} must NOT be visible — "
                f"the frame is filled by the detail region only, with the rest of the "
                f"{product_noun} cropped out by the frame edge."
            )
        else:
            lines.append(
                f"\nCAMERA: {angle_label} view, approximately {req.angle_degrees_from_left} degrees "
                f"from the left. "
                f"Focal length equivalent {req.focal_length_mm} mm, {req.aperture} aperture. "
                f"Framing: {req.framing}."
            )

    # ------------------------------------------------------------------ #
    # Catalog framing contract — the numeric half of the camera spec. Placed
    # after the CAMERA / reference-lock blocks so it reads as the tightening
    # clause on whatever framing was just described, not as a competing one.
    # ------------------------------------------------------------------ #
    if req.catalog_framing_contract:
        lines.append(f"\n{req.catalog_framing_contract}")

    # ------------------------------------------------------------------ #
    # Shadow direction — required for leg swap and scene ref.
    # Skipped when the structured scene path is active (env_mode set):
    # the SCENE block already states shadow quality in narrative form,
    # and shadow_direction is often a non-clock label like "soft diffuse"
    # which makes the "(clock position)" sentence awkward.
    # ------------------------------------------------------------------ #
    if reference_locked:
        # Shadow direction comes from the moodboard reference — skip.
        pass
    elif req.shadow_direction and not req.env_mode:
        shadow_text = (
            f"Shadow direction: the shadow cast by the {product_noun} falls at "
            f"{req.shadow_direction} (clock position from the {product_noun}'s perspective)."
        )
        if legs_visible or has_leg_swap:
            shadow_text += " All leg contact shadows must be consistent with this direction."
        lines.append(shadow_text)
    elif req.env_mode and (legs_visible or has_leg_swap):
        # Still pin the leg contact shadows to the scene shadow, but rely on
        # the narrative SCENE block for the actual direction language.
        lines.append(
            f"All leg contact shadows must be consistent with the shadow direction "
            f"described in the SCENE section."
        )

    # ------------------------------------------------------------------ #
    # Scene block — two modes (packshot / lifestyle) driven by env_mode.
    # Eliminates the prior contradiction where a hardcoded "Neutral studio
    # backdrop" line was emitted even when the caller wanted a lifestyle
    # render with a specific environment.
    # Skipped entirely under reference_locked: the moodboard reference is
    # the authoritative scene/backdrop source.
    # ------------------------------------------------------------------ #
    # keep_source_scene suppresses the backdrop block entirely — the BACKGROUND
    # paragraph above already tells the model to preserve slot 1's own scene, and
    # a packshot/lifestyle backdrop description here would directly fight it.
    if not reference_locked and not req.keep_source_scene:
        lines.append(_build_scene_block(req, product_noun, slots))

    # ------------------------------------------------------------------ #
    # Preserve list
    # ------------------------------------------------------------------ #
    if req.preserve_list:
        preserve_readable = [p.replace("_", " ") for p in req.preserve_list]
        lines.append(
            f"\nPRESERVE — do NOT change any of the following: "
            + ", ".join(preserve_readable) + "."
        )
        # Repeat leg-count emphasis ONLY when legs are actually visible.
        if legs_visible:
            lines.append(
                f"The {product_noun} has exactly {req.leg_count} legs. "
                f"Leg count is {req.leg_count} — do not add, remove, or merge legs."
            )

    # ------------------------------------------------------------------ #
    # Output style — in in-place recolor mode, the "e-commerce hero
    # photography" default biases the model toward hero-framing. Replace
    # with a style instruction that matches slot 1 instead.
    # ------------------------------------------------------------------ #
    if in_place_recolor:
        lines.append(
            f"\nOUTPUT STYLE: Match the photographic style, sharpness, color "
            f"grading, and framing of slot 1. The output is a recoloring of "
            f"slot 1's photograph, not a re-shoot."
        )
    else:
        lines.append(f"\nOUTPUT STYLE: {req.output_style}")

    # ------------------------------------------------------------------ #
    # Negative list
    # ------------------------------------------------------------------ #
    negatives = list(req.negative_list)
    # When legs are NOT visible on a bed, explicitly negate legs at the
    # negative-list level too — the strongest signal we have.
    if is_bed and not legs_visible and not has_leg_swap:
        negatives = [
            "added legs",
            "added feet",
            "added posts",
            "added risers under the bed",
            "frame raised on visible supports",
        ] + negatives

    if negatives:
        lines.append(
            f"\nNEGATIVE (must not appear in output): "
            + "; ".join(negatives) + "."
        )

    # ------------------------------------------------------------------ #
    # Optional free-form notes
    # ------------------------------------------------------------------ #
    if req.notes:
        lines.append(f"\nADDITIONAL NOTES: {req.notes}")

    return "\n".join(lines)


def _build_freeform_prompt(
    *,
    text: str,
    style: str = "",
    env: str = "",
    tod: str = "",
    lens: str = "",
    height: str = "",
    color_en: str = "",
    mat_noun_en: str = "",
    mat_texture_en: str = "",
    mat_avoid_en: list[str] | None = None,
    people: str = "",
    seed: str = "",
    slots: dict[str, int] | None = None,
    color_hex: str = "",
) -> str:
    """
    Compose the full editorial prompt: the user's brief leads, picker
    fragments follow as art-direction constraints. Every picker is optional —
    empty ids are simply skipped, so the minimal prompt is TASK + BRIEF +
    OUTPUT STYLE.

    `slots` maps reference roles to the 1-based positions that are ACTUALLY
    attached (generator.plan_freeform_reference_slots after the engine's
    cap), so the prompt never describes an image the model did not receive.
    """
    lines: list[str] = [
        "TASK: Create a brand-new editorial photograph from scratch based on "
        "the brief below. There is no base product to preserve — full "
        "creative freedom within the art direction."
    ]
    slots = dict(slots or {})
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
        hex_label = (color_hex or "").strip().upper()
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
    lines.append("")
    lines.append(f"BRIEF: {text.strip()}")
    lines.append("")

    if style in _EDITORIAL_STYLES:
        lines.append(f"ART DIRECTION: {_EDITORIAL_STYLES[style]}.")
    if env and env in _ENV_TO_SCENE and env != "custom":
        lines.append(f"SETTING: {_ENV_TO_SCENE[env][1]}.")
    if tod in _TOD_TO_PROMPT:
        lines.append(f"LIGHT: {_TOD_TO_PROMPT[tod]}.")
    cam_bits = []
    if lens in _LENS_TO_PROMPT:
        cam_bits.append(_LENS_TO_PROMPT[lens]["descriptor"])
    if height in _HEIGHT_TO_PHRASE:
        cam_bits.append(_HEIGHT_TO_PHRASE[height])
    if cam_bits:
        lines.append("CAMERA: " + "; ".join(cam_bits) + ".")
    if color_en:
        lines.append(
            f"COLOR DIRECTION (hard constraint): the hero furniture piece and "
            f"the dominant tone of the frame are {color_en}; the supporting "
            "palette stays harmonious and neutral around it."
        )
    if mat_noun_en:
        # The full texture spec, not a one-line hint — with no base image to
        # anchor the fabric, a soft hint gets overridden by the model's own
        # styling (the same noun-vs-spec lesson as the variant pipeline).
        lines.append(
            f"TEXTILE DIRECTION (hard constraint): every upholstered "
            f"furniture piece in the frame is upholstered in {mat_noun_en}. "
            f"Fabric spec: {mat_texture_en}"
        )
        if mat_avoid_en:
            lines.append(
                "TEXTILE — must not appear: " + "; ".join(mat_avoid_en) + "."
            )
    if people in _PEOPLE_TO_PROMPT:
        lines.append(f"PEOPLE: {_PEOPLE_TO_PROMPT[people]}")
    if seed.strip():
        lines.append(f"seed hint: {seed.strip()}")

    lines.append("")
    lines.append(
        "OUTPUT STYLE: professional editorial furniture-brand photography, "
        "photorealistic, coherent high-end art direction, natural color grading."
    )
    negative = (
        "NEGATIVE (must not appear in output): any rendered text, typography, "
        "logos, watermarks or UI elements — leave clean negative space where "
        "a masthead or headline would be placed."
    )
    if people not in _PEOPLE_TO_PROMPT:
        negative += " No people, no human figures, no faces, no body parts."
    lines.append(negative)
    return "\n".join(lines)
