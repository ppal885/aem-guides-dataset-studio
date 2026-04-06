"""AI image generation service for DITA topics.

Scans DITA XML for <image> and <fig> elements, generates images via
OpenAI DALL-E or placeholder fallback, and saves them alongside the topic.

Feature flag: DITA_IMAGE_GENERATION_ENABLED (default False)
"""
import os
import re
import base64
from pathlib import Path
from typing import Optional
from uuid import uuid4

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger("image_generation_service")

DITA_IMAGE_GENERATION_ENABLED = os.getenv("DITA_IMAGE_GENERATION_ENABLED", "false").lower() == "true"
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "openai")  # openai | placeholder
DALL_E_MODEL = os.getenv("DALL_E_MODEL", "dall-e-3")
DALL_E_SIZE = os.getenv("DALL_E_SIZE", "1024x1024")
DALL_E_QUALITY = os.getenv("DALL_E_QUALITY", "standard")  # standard | hd


def extract_image_refs(dita_xml: str) -> list[dict]:
    """Extract image references from DITA XML.

    Returns list of dicts with keys: href, alt_text, context (surrounding text).
    """
    refs = []

    # Match <image href="..." ...> with optional <alt> child
    image_pattern = re.compile(
        r'<image\s+[^>]*href=["\']([^"\']+)["\'][^>]*/?>',
        re.DOTALL,
    )
    # Match <fig> with <title> and <image>
    fig_pattern = re.compile(
        r'<fig[^>]*>(.*?)</fig>',
        re.DOTALL,
    )

    for m in fig_pattern.finditer(dita_xml):
        fig_content = m.group(1)
        title_m = re.search(r'<title[^>]*>(.*?)</title>', fig_content, re.DOTALL)
        img_m = re.search(r'href=["\']([^"\']+)["\']', fig_content)
        alt_m = re.search(r'<alt[^>]*>(.*?)</alt>', fig_content, re.DOTALL)
        if img_m:
            refs.append({
                "href": img_m.group(1),
                "alt_text": _strip_tags(alt_m.group(1)) if alt_m else "",
                "fig_title": _strip_tags(title_m.group(1)) if title_m else "",
                "context": _strip_tags(fig_content)[:200],
            })

    # Also find standalone <image> not inside <fig>
    for m in image_pattern.finditer(dita_xml):
        href = m.group(1)
        # Skip if already found in a <fig>
        if any(r["href"] == href for r in refs):
            continue
        # Try to find nearby <alt> text
        alt_m = re.search(
            rf'<image[^>]*href=["\']{ re.escape(href) }["\'][^>]*>.*?<alt[^>]*>(.*?)</alt>',
            dita_xml, re.DOTALL,
        )
        refs.append({
            "href": href,
            "alt_text": _strip_tags(alt_m.group(1)) if alt_m else "",
            "fig_title": "",
            "context": "",
        })

    return refs


def _strip_tags(text: str) -> str:
    """Remove XML tags from text."""
    return re.sub(r'<[^>]+>', '', text).strip()


def _build_image_prompt(ref: dict, topic_context: str = "") -> str:
    """Build a DALL-E prompt from image reference metadata."""
    parts = []
    if ref.get("fig_title"):
        parts.append(f"Technical illustration: {ref['fig_title']}")
    if ref.get("alt_text"):
        parts.append(ref["alt_text"])
    if ref.get("context") and not parts:
        parts.append(f"Technical diagram for: {ref['context'][:100]}")
    if topic_context:
        parts.append(f"Context: {topic_context[:100]}")

    prompt = ". ".join(parts) if parts else "Technical documentation placeholder image"
    # Add style guidance
    prompt += ". Clean, professional technical illustration style. White background. No text overlays."
    return prompt[:1000]


async def generate_image_openai(prompt: str, output_path: Path) -> Optional[str]:
    """Generate an image using OpenAI DALL-E and save to output_path."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — cannot generate images")
        return None

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)

        response = await client.images.generate(
            model=DALL_E_MODEL,
            prompt=prompt,
            n=1,
            size=DALL_E_SIZE,
            quality=DALL_E_QUALITY,
            response_format="b64_json",
        )

        if response.data and response.data[0].b64_json:
            img_bytes = base64.b64decode(response.data[0].b64_json)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(img_bytes)
            logger.info_structured(
                "Image generated",
                extra_fields={"path": str(output_path), "size_bytes": len(img_bytes)},
            )
            return str(output_path)
    except Exception as e:
        logger.warning_structured(
            "DALL-E image generation failed",
            extra_fields={"error": str(e), "prompt": prompt[:100]},
        )
    return None


def generate_placeholder_image(output_path: Path, label: str = "Placeholder") -> str:
    """Generate a simple SVG placeholder image."""
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400" viewBox="0 0 800 400">
  <rect width="800" height="400" fill="#f1f5f9" rx="8"/>
  <rect x="20" y="20" width="760" height="360" fill="none" stroke="#94a3b8" stroke-width="2" stroke-dasharray="10,5" rx="6"/>
  <text x="400" y="180" text-anchor="middle" fill="#64748b" font-family="system-ui, sans-serif" font-size="24" font-weight="600">{_escape_svg(label[:60])}</text>
  <text x="400" y="220" text-anchor="middle" fill="#94a3b8" font-family="system-ui, sans-serif" font-size="14">Replace with actual screenshot or diagram</text>
  <rect x="360" y="250" width="80" height="80" fill="none" stroke="#cbd5e1" stroke-width="2" rx="4"/>
  <line x1="360" y1="250" x2="440" y2="330" stroke="#cbd5e1" stroke-width="1.5"/>
  <line x1="440" y1="250" x2="360" y2="330" stroke="#cbd5e1" stroke-width="1.5"/>
</svg>'''
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")
    return str(output_path)


def _escape_svg(text: str) -> str:
    """Escape text for SVG."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


async def generate_images_for_dita(
    dita_xml: str,
    output_dir: Path,
    topic_title: str = "",
) -> list[dict]:
    """Generate images for all <image> references in DITA XML.

    Returns list of dicts: {href, generated_path, method}
    """
    if not DITA_IMAGE_GENERATION_ENABLED:
        return []

    refs = extract_image_refs(dita_xml)
    if not refs:
        return []

    results = []
    for ref in refs:
        href = ref["href"]
        # Determine output filename from href
        img_name = Path(href).name
        if not img_name or img_name == href:
            img_name = f"image_{uuid4().hex[:8]}.png"

        output_path = output_dir / href  # Preserve relative path structure

        if IMAGE_PROVIDER == "openai" and os.getenv("OPENAI_API_KEY"):
            prompt = _build_image_prompt(ref, topic_title)
            # Force PNG extension for DALL-E output
            if output_path.suffix.lower() == ".svg":
                output_path = output_path.with_suffix(".png")
            generated = await generate_image_openai(prompt, output_path)
            if generated:
                results.append({"href": href, "generated_path": generated, "method": "dall-e"})
                continue

        # Fallback: SVG placeholder
        svg_path = output_path.with_suffix(".svg") if output_path.suffix.lower() != ".svg" else output_path
        label = ref.get("fig_title") or ref.get("alt_text") or img_name
        generate_placeholder_image(svg_path, label)
        results.append({"href": href, "generated_path": str(svg_path), "method": "placeholder"})

    logger.info_structured(
        "Images generated for DITA topic",
        extra_fields={
            "topic_title": topic_title,
            "total": len(results),
            "dall_e": sum(1 for r in results if r["method"] == "dall-e"),
            "placeholder": sum(1 for r in results if r["method"] == "placeholder"),
        },
    )
    return results
