"""Pet skin discovery — scans pets/ folder for available sprites."""

from pathlib import Path

PETS_DIR = Path(__file__).resolve().parent.parent.parent / "pets"


def list_skins() -> list[str]:
    """Return sorted list of available pet skin names."""
    if not PETS_DIR.exists():
        return ["HaChiCat"]
    skins = []
    for d in sorted(PETS_DIR.iterdir()):
        if d.is_dir() and d.name != "default":
            has_img = any(
                (d / f).exists()
                for f in ("sprite_sheet.png", "spritesheet.webp", "spritesheet.png")
            )
            if has_img:
                skins.append(d.name)
    if "HaChiCat" not in skins:
        skins.insert(0, "HaChiCat")
    return skins


def get_sprite_path(skin: str) -> Path | None:
    """Return the full path to the sprite image for a given skin."""
    d = PETS_DIR / skin
    for name in ("sprite_sheet.png", "spritesheet.webp", "spritesheet.png"):
        p = d / name
        if p.exists():
            return p
    return None
