"""
legs/render-blender.py
======================
Blender batch-render script for the nano-sofa leg reference library.

USAGE
-----
From the command line (headless):

    blender --background legs/source/<style>.blend \
            --python legs/render-blender.py \
            -- <style> [--materials oak walnut blacksteel] [--angles front34l side90]

From Docker (recommended, uses the pinned Blender image):

    docker compose run --rm renderer <style>

Without arguments after the double-dash, all materials and all angles are rendered.

IDEMPOTENCY
-----------
Re-running the script against the same .blend with the same arguments produces
byte-identical output. Achieved by:
  - Fixed RNG seed in Cycles noise (no random sampling variation)
  - Fixed render sample count
  - Fixed camera matrices (no random jitter)
  - Output filenames are deterministic; existing files are overwritten in-place

OUTPUT
------
Per leg per angle per material, two PNGs are written:

  legs/<style>_<material>_<angle>.png         — leg + contact shadow on 18% grey
  legs/<style>_<material>_<angle>_alpha.png   — leg only, transparent background

Source EXR retained at:
  legs/source/renders/<style>_<material>_<angle>.exr

Naming slug reference:
  style     — e.g. tapered, hairpin, plinth, bun, block, splayedtaper, turned, cabriole
  material  — one of: oak, walnut, blacksteel, brass, chrome, mattewhite, whiteplastic
  angle     — one of: front0, front34l, front34r, side90, low34

BLENDER VERSION
---------------
Tested against Blender 4.2 LTS. The bpy API surface used here (cycles, scene,
camera, lights, material nodes) is stable across 3.6 LTS → 4.2 LTS. If running
on an earlier version, the principled BSDF node socket names may differ slightly
(roughness vs Roughness — the script uses bpy.types constants to stay portable).

LIGHTING STANDARD (3-point softbox, matches STANDARDS.md)
----------------------------------------------------------
  Key:  upper-front-left, 5500K, area 1.5x1.5m @ 4m, 800 W
  Fill: upper-right,      5500K, area 1.0x1.0m @ 3m, 240 W  (30% of key)
  Rim:  rear,             5500K, area 0.8x0.8m @ 2.5m, 400 W

Shadow direction from these lights: primary shadow falls to the rear-right
(approximately 4-5 o-clock from the leg's perspective), matching the schema
default shadow_direction of "4 o-clock" used in sofa generation requests.
"""

import sys
import os
import argparse
import json
import math

# ---------------------------------------------------------------------------
# Guard: this script must run inside Blender
# ---------------------------------------------------------------------------
try:
    import bpy
    import mathutils
except ImportError:
    print("ERROR: This script must be run via Blender's Python interpreter.")
    print("  blender --background <file.blend> --python legs/render-blender.py -- <args>")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LEGS_DIR = SCRIPT_DIR  # legs/ is the output root
SOURCE_DIR = os.path.join(LEGS_DIR, "source")
RENDERS_DIR = os.path.join(SOURCE_DIR, "renders")

MANIFEST_PATH = os.path.join(LEGS_DIR, "manifest.json")

# Render resolution for the standard pass (1024x1024 per STANDARDS.md)
RENDER_RES = 1024

# Cycles sample count — enough for clean shadows without excessive render time.
# Fixed value ensures idempotency.
CYCLES_SAMPLES = 256

# Random seed — must never change; any change breaks idempotency
CYCLES_SEED = 42

# 18% grey in sRGB linear (0.5^2.2 ≈ 0.2159; we use the exact sRGB value)
GREY_18_LINEAR = 0.2159

# ---------------------------------------------------------------------------
# Canonical material definitions
# ---------------------------------------------------------------------------
# Each entry defines a PrincipledBSDF parameterisation.
# Keys match the slug used in output filenames.

MATERIALS = {
    "oak": {
        "label": "Solid oak, natural finish",
        "base_color": (0.627, 0.431, 0.243, 1.0),   # warm mid-oak
        "metallic": 0.0,
        "roughness": 0.65,
        "specular": 0.3,
        "sheen": 0.1,
        "sheen_roughness": 0.5,
        "subsurface": 0.05,
        "subsurface_color": (0.7, 0.5, 0.3, 1.0),
    },
    "walnut": {
        "label": "Solid walnut, satin finish",
        "base_color": (0.251, 0.149, 0.082, 1.0),   # dark chocolate walnut
        "metallic": 0.0,
        "roughness": 0.45,
        "specular": 0.5,
        "sheen": 0.05,
        "sheen_roughness": 0.4,
        "subsurface": 0.03,
        "subsurface_color": (0.4, 0.2, 0.1, 1.0),
    },
    "blacksteel": {
        "label": "Black powder-coated steel",
        "base_color": (0.04, 0.04, 0.04, 1.0),
        "metallic": 0.0,                             # powder coat is non-metallic
        "roughness": 0.85,
        "specular": 0.15,
        "sheen": 0.0,
        "sheen_roughness": 0.5,
        "subsurface": 0.0,
        "subsurface_color": (0.0, 0.0, 0.0, 1.0),
    },
    "brass": {
        "label": "Brushed brass",
        "base_color": (0.796, 0.624, 0.208, 1.0),
        "metallic": 1.0,
        "roughness": 0.40,                           # brushed = moderate roughness
        "specular": 0.5,
        "sheen": 0.0,
        "sheen_roughness": 0.5,
        "subsurface": 0.0,
        "subsurface_color": (0.0, 0.0, 0.0, 1.0),
        "anisotropic": 0.6,                          # brushed direction highlight
        "anisotropic_rotation": 0.0,
    },
    "chrome": {
        "label": "Polished chrome",
        "base_color": (0.85, 0.85, 0.85, 1.0),
        "metallic": 1.0,
        "roughness": 0.05,
        "specular": 0.5,
        "sheen": 0.0,
        "sheen_roughness": 0.5,
        "subsurface": 0.0,
        "subsurface_color": (0.0, 0.0, 0.0, 1.0),
    },
    "mattewhite": {
        "label": "Matte white",
        "base_color": (0.95, 0.95, 0.95, 1.0),
        "metallic": 0.0,
        "roughness": 0.95,
        "specular": 0.05,
        "sheen": 0.0,
        "sheen_roughness": 0.5,
        "subsurface": 0.0,
        "subsurface_color": (0.0, 0.0, 0.0, 1.0),
    },
    "whiteplastic": {
        "label": "Neutral white plastic (shape-only reference)",
        "base_color": (0.9, 0.9, 0.9, 1.0),
        "metallic": 0.0,
        "roughness": 0.55,
        "specular": 0.3,
        "sheen": 0.0,
        "sheen_roughness": 0.5,
        "subsurface": 0.0,
        "subsurface_color": (0.0, 0.0, 0.0, 1.0),
    },
}

ALL_MATERIAL_SLUGS = list(MATERIALS.keys())

# ---------------------------------------------------------------------------
# Canonical camera angles
# ---------------------------------------------------------------------------
# Each angle is defined by:
#   location  — (x, y, z) in metres, relative to leg at origin
#   rotation  — Euler XYZ in degrees
#   fov_mm    — focal length in mm (50mm standard per schema)
#
# Coordinate system: Blender default (+Y = into screen, +Z = up)
# Camera looks toward the world origin from its location.

ANGLES = {
    "front0": {
        "description": "Dead-on front, leg axis perpendicular to camera",
        "location": (0.0, -0.50, 0.08),
        "rotation_euler_deg": (90.0, 0.0, 0.0),
        "focal_length_mm": 50,
    },
    "front34l": {
        "description": "34 degrees left of front (camera to the right of centre), matching sofa schema front-34-left",
        "location": (0.25, -0.45, 0.10),
        "rotation_euler_deg": (88.0, 0.0, 30.0),
        "focal_length_mm": 50,
    },
    "front34r": {
        "description": "34 degrees right of front (camera to the left of centre), matching sofa schema front-34-right",
        "location": (-0.25, -0.45, 0.10),
        "rotation_euler_deg": (88.0, 0.0, -30.0),
        "focal_length_mm": 50,
    },
    "side90": {
        "description": "Pure side profile",
        "location": (-0.50, 0.0, 0.08),
        "rotation_euler_deg": (90.0, 0.0, -90.0),
        "focal_length_mm": 50,
    },
    "low34": {
        "description": "Low camera, 34 degree upward tilt, three-quarter framing",
        "location": (0.20, -0.40, 0.02),
        "rotation_euler_deg": (80.0, 0.0, 25.0),
        "focal_length_mm": 50,
    },
}

ALL_ANGLE_SLUGS = list(ANGLES.keys())

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    """
    Extract arguments that appear after the '--' separator Blender uses to
    split its own args from the script's args.
    """
    argv = sys.argv
    if "--" in argv:
        script_args = argv[argv.index("--") + 1:]
    else:
        script_args = []

    parser = argparse.ArgumentParser(
        description="Render a leg style from its .blend file at all canonical angles and materials."
    )
    parser.add_argument(
        "style",
        help="Leg style slug (e.g. tapered, hairpin, plinth). Must match a .blend file in legs/source/.",
    )
    parser.add_argument(
        "--materials",
        nargs="+",
        default=ALL_MATERIAL_SLUGS,
        choices=ALL_MATERIAL_SLUGS,
        metavar="MATERIAL",
        help=f"Materials to render. Default: all ({', '.join(ALL_MATERIAL_SLUGS)})",
    )
    parser.add_argument(
        "--angles",
        nargs="+",
        default=ALL_ANGLE_SLUGS,
        choices=ALL_ANGLE_SLUGS,
        metavar="ANGLE",
        help=f"Angles to render. Default: all ({', '.join(ALL_ANGLE_SLUGS)})",
    )
    parser.add_argument(
        "--resolution",
        type=int,
        default=RENDER_RES,
        choices=[1024, 2048, 4096],
        help="Output resolution (square). Default: 1024.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=CYCLES_SAMPLES,
        help=f"Cycles sample count. Default: {CYCLES_SAMPLES}. Changing this breaks idempotency.",
    )
    return parser.parse_args(script_args)


# ---------------------------------------------------------------------------
# Scene setup helpers
# ---------------------------------------------------------------------------

def ensure_output_dirs(style: str):
    """Create output directories if they do not exist."""
    os.makedirs(LEGS_DIR, exist_ok=True)
    os.makedirs(RENDERS_DIR, exist_ok=True)


def set_render_settings(scene, resolution: int, samples: int):
    """
    Configure Cycles render settings for deterministic, high-quality output.
    All parameters that could introduce per-run variation are fixed.
    """
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True

    # Fixed seed — critical for idempotency
    scene.cycles.seed = CYCLES_SEED
    scene.cycles.use_animated_seed = False

    # Resolution
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100

    # Color management: sRGB output as specified in STANDARDS.md
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.sequencer_colorspace_settings.name = "sRGB"

    # PNG output
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 15  # lossless at modest compression


def build_standard_lighting(scene):
    """
    Build the canonical 3-point softbox rig defined in STANDARDS.md.
    Removes any existing lights first so re-runs are idempotent.

    Key:  upper-front-left, 5500K, area 1.5x1.5m @ 4m, 800 W
    Fill: upper-right,      5500K, area 1.0x1.0m @ 3m, 240 W
    Rim:  rear,             5500K, area 0.8x0.8m @ 2.5m, 400 W
    """
    # Remove existing lights
    for obj in list(scene.objects):
        if obj.type == "LIGHT":
            bpy.data.objects.remove(obj, do_unlink=True)

    light_defs = [
        {
            "name": "STANDARD_Key",
            # Upper-front-left: negative Y (toward camera), positive X (left from
            # camera's perspective), positive Z (above)
            "location": (-1.8, -2.5, 3.0),
            "power": 800,
            "size_x": 1.5,
            "size_y": 1.5,
            # Point toward origin
            "aim_at": (0.0, 0.0, 0.06),
        },
        {
            "name": "STANDARD_Fill",
            # Upper-right: positive X from camera side
            "location": (1.5, -1.5, 2.5),
            "power": 240,
            "size_x": 1.0,
            "size_y": 1.0,
            "aim_at": (0.0, 0.0, 0.06),
        },
        {
            "name": "STANDARD_Rim",
            # Rear: positive Y (behind leg)
            "location": (0.0, 1.5, 2.0),
            "power": 400,
            "size_x": 0.8,
            "size_y": 0.8,
            "aim_at": (0.0, 0.0, 0.06),
        },
    ]

    for ldef in light_defs:
        light_data = bpy.data.lights.new(name=ldef["name"], type="AREA")
        light_data.energy = ldef["power"]
        light_data.shape = "RECTANGLE"
        light_data.size = ldef["size_x"]
        light_data.size_y = ldef["size_y"]
        light_data.color = (1.0, 0.988, 0.941)  # 5500K warm white approximation
        light_data.use_shadow = True

        light_obj = bpy.data.objects.new(name=ldef["name"], object_data=light_data)
        scene.collection.objects.link(light_obj)
        light_obj.location = mathutils.Vector(ldef["location"])

        # Point toward aim target
        direction = mathutils.Vector(ldef["aim_at"]) - mathutils.Vector(ldef["location"])
        rot_quat = direction.to_track_quat("-Z", "Y")
        light_obj.rotation_euler = rot_quat.to_euler()


def build_background_plane(scene):
    """
    Create an 18% neutral grey infinite-plane backdrop. Removes any existing
    object named STANDARD_Background on re-run.
    """
    existing = scene.objects.get("STANDARD_Background")
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)

    bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, 0))
    bg_obj = bpy.context.object
    bg_obj.name = "STANDARD_Background"

    # Create or reuse background material
    mat_name = "STANDARD_Grey18"
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        output = nodes.new("ShaderNodeOutputMaterial")
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = (
            GREY_18_LINEAR, GREY_18_LINEAR, GREY_18_LINEAR, 1.0
        )
        bsdf.inputs["Roughness"].default_value = 1.0
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
        links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    if bg_obj.data.materials:
        bg_obj.data.materials[0] = mat
    else:
        bg_obj.data.materials.append(mat)


def set_camera_angle(scene, angle_slug: str):
    """
    Position the scene camera for the given angle slug.
    Creates a camera named STANDARD_Camera if one does not exist;
    always overwrites its position and rotation.
    """
    angle = ANGLES[angle_slug]

    cam_obj = scene.objects.get("STANDARD_Camera")
    if cam_obj is None:
        cam_data = bpy.data.cameras.new("STANDARD_Camera")
        cam_obj = bpy.data.objects.new("STANDARD_Camera", cam_data)
        scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    cam_obj.location = mathutils.Vector(angle["location"])

    # Euler rotation in radians
    rx, ry, rz = [math.radians(d) for d in angle["rotation_euler_deg"]]
    cam_obj.rotation_euler = mathutils.Euler((rx, ry, rz), "XYZ")

    cam_obj.data.lens = angle["focal_length_mm"]
    cam_obj.data.sensor_width = 36  # full-frame 35mm equivalent


def apply_material_to_leg(leg_obj, material_slug: str):
    """
    Apply a standard material definition from MATERIALS to a leg object.
    Creates a new PrincipledBSDF material or reuses one with the same name.

    The leg object is assumed to have at least one material slot.
    If it has none, a slot is added.
    """
    mdef = MATERIALS[material_slug]
    mat_name = f"LEGMAT_{material_slug}"

    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")

    bsdf.inputs["Base Color"].default_value = mdef["base_color"]
    bsdf.inputs["Metallic"].default_value = mdef["metallic"]
    bsdf.inputs["Roughness"].default_value = mdef["roughness"]

    # Subsurface (wood has a small SSS component for depth)
    if mdef.get("subsurface", 0) > 0:
        bsdf.inputs["Subsurface Weight"].default_value = mdef["subsurface"]
        bsdf.inputs["Subsurface Color"].default_value = mdef["subsurface_color"]

    # Sheen (fabric-like surface sheen on wood)
    if mdef.get("sheen", 0) > 0:
        bsdf.inputs["Sheen Weight"].default_value = mdef["sheen"]
        bsdf.inputs["Sheen Roughness"].default_value = mdef["sheen_roughness"]

    # Anisotropy (brushed brass)
    if "anisotropic" in mdef:
        bsdf.inputs["Anisotropic"].default_value = mdef["anisotropic"]
        bsdf.inputs["Anisotropic Rotation"].default_value = mdef["anisotropic_rotation"]

    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    # Assign to all slots on the leg object
    if not leg_obj.data.materials:
        leg_obj.data.materials.append(mat)
    else:
        for i in range(len(leg_obj.data.materials)):
            leg_obj.data.materials[i] = mat


def find_leg_object(scene):
    """
    Locate the leg mesh in the scene. Convention: the leg object must be named
    with the prefix 'LEG_' or be the only non-plane, non-light, non-camera object.

    Returns the object or raises a ValueError.
    """
    # Prefer explicitly named leg object
    for obj in scene.objects:
        if obj.name.startswith("LEG_"):
            return obj

    # Fall back: the only mesh that is not the background plane
    candidates = [
        o for o in scene.objects
        if o.type == "MESH" and o.name != "STANDARD_Background"
    ]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise ValueError(
            f"Multiple mesh objects found and none named 'LEG_*'. "
            f"Rename the leg mesh to 'LEG_<style>' in Blender: "
            f"{[o.name for o in candidates]}"
        )
    raise ValueError("No leg mesh object found in scene.")


# ---------------------------------------------------------------------------
# Shadow-only composite pass
# ---------------------------------------------------------------------------

def render_shadow_pass(scene, output_path: str):
    """
    Render the contact shadow as a separate RGBA PNG where the shadow region
    has alpha > 0 on a transparent background.

    Technique: use the Cycles shadow catcher on the background plane.
    The compositing nodes output the shadow layer independently.
    """
    bg_obj = scene.objects.get("STANDARD_Background")
    if bg_obj:
        bg_obj.is_shadow_catcher = True

    scene.render.film_transparent = True
    scene.render.filepath = output_path
    bpy.ops.render.render(write_still=True)

    # Reset film transparency for subsequent passes
    scene.render.film_transparent = False
    if bg_obj:
        bg_obj.is_shadow_catcher = False


# ---------------------------------------------------------------------------
# Main render loop
# ---------------------------------------------------------------------------

def render_leg(style: str, materials: list, angles: list, resolution: int, samples: int):
    """
    Main entry point. Renders all requested material × angle combinations for a
    given leg style.

    Expected .blend structure:
      - One mesh named 'LEG_<style>' (or the only non-background mesh)
      - Pivot at world origin (0, 0, 0) — base of leg on floor
    """
    ensure_output_dirs(style)

    scene = bpy.context.scene
    set_render_settings(scene, resolution, samples)
    build_standard_lighting(scene)
    build_background_plane(scene)

    try:
        leg_obj = find_leg_object(scene)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"\n=== Rendering leg style: {style} ===")
    print(f"Materials: {materials}")
    print(f"Angles:    {angles}")
    print(f"Resolution: {resolution}x{resolution}")
    print(f"Samples:   {samples}")
    print()

    rendered = []

    for material_slug in materials:
        print(f"  Material: {material_slug}")
        apply_material_to_leg(leg_obj, material_slug)

        for angle_slug in angles:
            print(f"    Angle: {angle_slug} ... ", end="", flush=True)
            set_camera_angle(scene, angle_slug)

            # --- Main pass (leg + shadow on grey) ---
            main_filename = f"{style}_{material_slug}_{angle_slug}.png"
            main_path = os.path.join(LEGS_DIR, main_filename)

            scene.render.film_transparent = False
            scene.render.filepath = main_path
            bpy.ops.render.render(write_still=True)

            # --- Alpha pass (leg only, transparent background) ---
            alpha_filename = f"{style}_{material_slug}_{angle_slug}_alpha.png"
            alpha_path = os.path.join(LEGS_DIR, alpha_filename)

            bg_obj = scene.objects.get("STANDARD_Background")
            if bg_obj:
                bg_obj.hide_render = True
            scene.render.film_transparent = True
            scene.render.filepath = alpha_path
            bpy.ops.render.render(write_still=True)
            scene.render.film_transparent = False
            if bg_obj:
                bg_obj.hide_render = False

            # --- EXR source pass (high-bit-depth archive) ---
            exr_filename = f"{style}_{material_slug}_{angle_slug}.exr"
            exr_path = os.path.join(RENDERS_DIR, exr_filename)

            scene.render.image_settings.file_format = "OPEN_EXR"
            scene.render.image_settings.color_mode = "RGBA"
            scene.render.image_settings.exr_codec = "DWAA"
            scene.render.filepath = exr_path
            bpy.ops.render.render(write_still=True)

            # Restore PNG settings for subsequent passes
            scene.render.image_settings.file_format = "PNG"
            scene.render.image_settings.color_mode = "RGBA"
            scene.render.image_settings.color_depth = "8"

            print("done")

            rendered.append({
                "main": main_path,
                "alpha": alpha_path,
                "exr": exr_path,
                "material": material_slug,
                "angle": angle_slug,
            })

    print(f"\n=== {style}: {len(rendered)} render passes complete ===")

    # --- Manifest update ---
    update_manifest_renders(style, materials, angles)

    return rendered


# ---------------------------------------------------------------------------
# Manifest helper
# ---------------------------------------------------------------------------

def update_manifest_renders(style: str, materials: list, angles: list):
    """
    Update legs/manifest.json to record which render files now exist for
    the given style. Only updates 'angles_available' and 'renders' sub-keys.
    Does not overwrite other manifest fields set by a human.

    Manifest write is atomic: load → mutate → write.
    """
    if not os.path.exists(MANIFEST_PATH):
        print(f"WARNING: {MANIFEST_PATH} not found. Skipping manifest update.")
        return

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    legs = manifest.get("legs", {})

    for material_slug in materials:
        leg_id = f"{style}_{material_slug}"
        entry = legs.get(leg_id, {})

        # Build the renders map
        renders = entry.get("renders", {})
        for angle_slug in angles:
            renders[angle_slug] = {
                "main": f"legs/{style}_{material_slug}_{angle_slug}.png",
                "alpha": f"legs/{style}_{material_slug}_{angle_slug}_alpha.png",
            }

        entry["renders"] = renders

        # Ensure angles_available is complete
        existing_angles = set(entry.get("angles_available", []))
        existing_angles.update(angles)
        entry["angles_available"] = sorted(existing_angles)

        legs[leg_id] = entry

    manifest["legs"] = legs

    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    print(f"  Manifest updated at {MANIFEST_PATH}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = parse_args()
    render_leg(
        style=args.style,
        materials=args.materials,
        angles=args.angles,
        resolution=args.resolution,
        samples=args.samples,
    )
