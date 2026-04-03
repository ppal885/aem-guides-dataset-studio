# =============================================================================
# SECTION 6 — IMAGE TOOLS
# Add these to mcp_server.py above if __name__ == "__main__":
# =============================================================================

@mcp.tool()
def get_jira_issue_images(issue_key: str) -> str:
    """
    Fetch and download all image attachments from a Jira issue.
    Saves images to output/images/{issue_key}/ folder.
    Returns image metadata so Cursor can insert them into DITA as fig elements.

    Supports: PNG, JPG, GIF, SVG, BMP, WEBP
    Also detects: architecture diagrams, screenshots, flowcharts
    """
    try:
        import mimetypes
        from pathlib import Path
        from backend.app.services.jira_client import JiraClient
        from backend.app.services.jira_attachment_service import (
            ensure_attachment_cached,
            extract_excerpt,
        )
        from backend.app.db.session import SessionLocal
        from backend.app.db.jira_models import JiraAttachment, JiraIssue

        IMAGE_MIMES = {
            "image/png", "image/jpeg", "image/jpg", "image/gif",
            "image/svg+xml", "image/bmp", "image/webp", "image/tiff",
        }
        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".webp", ".tiff"}

        jira = JiraClient()

        # ── Get attachments from Jira API directly ────────────────────────────
        raw_attachments = jira.get_issue_attachments(issue_key)
        if not raw_attachments:
            return f"No attachments found for {issue_key}"

        # Filter images only
        image_attachments = []
        for att in raw_attachments:
            mime = (att.get("mimeType") or "").lower()
            filename = att.get("filename") or ""
            ext = Path(filename).suffix.lower()
            if mime in IMAGE_MIMES or ext in IMAGE_EXTS:
                image_attachments.append(att)

        if not image_attachments:
            return (
                f"No image attachments found for {issue_key}.\n"
                f"Total attachments: {len(raw_attachments)}\n"
                f"Types found: {', '.join(set(a.get('mimeType','unknown') for a in raw_attachments))}"
            )

        # ── Download images to output/images/{issue_key}/ ─────────────────────
        output_dir = PROJECT_ROOT / "output" / "images" / issue_key
        output_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for att in image_attachments:
            filename  = att.get("filename", "image.png")
            mime_type = att.get("mimeType", "image/png")
            size      = att.get("size", 0)
            content_url = att.get("content", "")

            # Download
            filepath = output_dir / filename
            if not filepath.exists():
                try:
                    content = jira.download_attachment(content_url)
                    filepath.write_bytes(content)
                except Exception as e:
                    results.append({
                        "filename": filename,
                        "error": str(e),
                        "downloaded": False,
                    })
                    continue

            # Detect image type for DITA alt text suggestion
            img_type = _detect_image_type(filename, mime_type)

            results.append({
                "filename": filename,
                "mime_type": mime_type,
                "size_bytes": size,
                "local_path": str(filepath),
                "relative_path": f"output/images/{issue_key}/{filename}",
                "aem_dam_path": f"/content/dam/dita-images/{issue_key}/{filename}",
                "image_type": img_type,
                "suggested_alt": _suggest_alt_text(filename, img_type),
                "suggested_title": _suggest_title(filename, img_type),
                "downloaded": True,
            })

        # Format output for Cursor
        lines = [
            f"✅ Found {len(results)} image(s) for {issue_key}",
            f"Saved to: {output_dir}",
            "",
            "IMAGES — Use these to insert fig elements in DITA:",
            "=" * 50,
        ]

        for i, r in enumerate(results, 1):
            if r.get("error"):
                lines.append(f"{i}. ❌ {r['filename']}: {r['error']}")
                continue
            lines.append(f"""
{i}. {r['filename']}
   Type:          {r['image_type']}
   Size:          {r['size_bytes']} bytes
   Local path:    {r['relative_path']}
   AEM DAM path:  {r['aem_dam_path']}
   Suggested alt: {r['suggested_alt']}
   Suggested title: {r['suggested_title']}

   DITA fig element to insert:
   <fig>
     <title>{r['suggested_title']}</title>
     <image href="{r['aem_dam_path']}"
            format="{r['mime_type'].split('/')[-1]}"
            scope="external">
       <alt>{r['suggested_alt']}</alt>
     </image>
   </fig>
""")

        lines.append("=" * 50)
        lines.append(
            "INSERT INSTRUCTION FOR CURSOR:\n"
            "For each image above, insert the fig element at the\n"
            "appropriate location in the DITA topic:\n"
            "- Screenshots → after the relevant step/context\n"
            "- Architecture diagrams → in concept body or section\n"
            "- Flowcharts → after context or before steps\n"
            "- Product images → in shortdesc context or section"
        )

        return "\n".join(lines)

    except Exception as e:
        return f"Error fetching images for {issue_key}: {e}"


@mcp.tool()
def save_dita_with_images(
    filename: str,
    content: str,
    issue_key: str,
) -> str:
    """
    Save a DITA file that references images.
    Validates that all <image href> paths exist locally.
    Reports any missing images so Cursor can fix them.

    filename: e.g. 'AEM-123-task.dita'
    content:  full DITA XML with fig/image elements
    issue_key: Jira issue key to find downloaded images
    """
    try:
        import re

        output_dir = PROJECT_ROOT / "output" / "dita"
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / filename

        # ── Check all image hrefs ─────────────────────────────────────────────
        image_refs = re.findall(r'<image[^>]+href="([^"]+)"', content)
        missing = []
        found   = []

        images_dir = PROJECT_ROOT / "output" / "images" / issue_key

        for href in image_refs:
            img_filename = href.split("/")[-1]
            local = images_dir / img_filename
            if local.exists():
                found.append(img_filename)
            else:
                missing.append(href)

        # Save the file
        filepath.write_text(content, encoding="utf-8")

        status_lines = [f"✅ Saved: {filepath}"]

        if found:
            status_lines.append(f"✅ Images verified: {', '.join(found)}")
        if missing:
            status_lines.append(f"⚠️ Missing images: {', '.join(missing)}")
            status_lines.append(
                "Run get_jira_issue_images to download missing images"
            )

        return "\n".join(status_lines)

    except Exception as e:
        return f"Error saving {filename}: {e}"


@mcp.tool()
def list_issue_images(issue_key: str) -> str:
    """
    List all downloaded images for a Jira issue.
    Use this to check what images are available before inserting into DITA.
    """
    try:
        images_dir = PROJECT_ROOT / "output" / "images" / issue_key
        if not images_dir.exists():
            return (
                f"No images downloaded for {issue_key} yet.\n"
                f"Run get_jira_issue_images('{issue_key}') first."
            )

        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".webp"}
        files = [
            f for f in images_dir.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS
        ]

        if not files:
            return f"No image files found in output/images/{issue_key}/"

        lines = [f"Images available for {issue_key}:", ""]
        for f in sorted(files):
            size = f.stat().st_size
            img_type = _detect_image_type(f.name, "")
            lines.append(
                f"  {f.name} ({size} bytes) — {img_type}\n"
                f"  AEM path: /content/dam/dita-images/{issue_key}/{f.name}"
            )

        return "\n".join(lines)

    except Exception as e:
        return f"Error listing images: {e}"


@mcp.tool()
def generate_fig_elements(issue_key: str) -> str:
    """
    Generate ready-to-paste DITA fig elements for all downloaded images.
    Cursor can copy these directly into the DITA topic.
    """
    try:
        images_dir = PROJECT_ROOT / "output" / "images" / issue_key
        if not images_dir.exists():
            return f"No images for {issue_key}. Run get_jira_issue_images first."

        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".webp"}
        files = [
            f for f in images_dir.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS
        ]

        if not files:
            return "No images found."

        lines = [
            f"DITA fig elements for {issue_key}:",
            "Copy and paste into appropriate location in your topic:",
            "",
        ]

        for f in sorted(files):
            img_type = _detect_image_type(f.name, "")
            alt      = _suggest_alt_text(f.name, img_type)
            title    = _suggest_title(f.name, img_type)
            fmt      = f.suffix.lower().strip(".")
            dam_path = f"/content/dam/dita-images/{issue_key}/{f.name}"

            lines.append(f"<!-- {f.name} — {img_type} -->")
            lines.append(f"""<fig>
  <title>{title}</title>
  <image href="{dam_path}"
         format="{fmt}"
         placement="break"
         scope="external">
    <alt>{alt}</alt>
  </image>
</fig>
""")

        return "\n".join(lines)

    except Exception as e:
        return f"Error generating fig elements: {e}"


# ── Helper functions ──────────────────────────────────────────────────────────

def _detect_image_type(filename: str, mime_type: str) -> str:
    """Detect what kind of image this is from filename."""
    name = filename.lower()
    if any(x in name for x in ["screenshot", "screen", "capture", "snap"]):
        return "screenshot"
    if any(x in name for x in ["arch", "architecture", "diagram", "design"]):
        return "architecture_diagram"
    if any(x in name for x in ["flow", "flowchart", "process", "workflow"]):
        return "flowchart"
    if any(x in name for x in ["product", "ui", "interface", "portal"]):
        return "product_image"
    if mime_type == "image/svg+xml" or name.endswith(".svg"):
        return "diagram"
    return "screenshot"  # default assumption


def _suggest_alt_text(filename: str, img_type: str) -> str:
    """Generate a sensible alt text from filename and type."""
    # Remove extension and clean up
    name = filename.rsplit(".", 1)[0]
    name = name.replace("-", " ").replace("_", " ").strip()

    suggestions = {
        "screenshot":          f"Screenshot showing {name}",
        "architecture_diagram": f"Architecture diagram of {name}",
        "flowchart":           f"Flowchart illustrating {name}",
        "product_image":       f"Product interface showing {name}",
        "diagram":             f"Diagram of {name}",
    }
    return suggestions.get(img_type, f"Image showing {name}")


def _suggest_title(filename: str, img_type: str) -> str:
    """Generate a sensible fig title from filename."""
    name = filename.rsplit(".", 1)[0]
    name = name.replace("-", " ").replace("_", " ").strip()
    name = name.capitalize()

    titles = {
        "screenshot":           name,
        "architecture_diagram": f"{name} architecture",
        "flowchart":            f"{name} flow",
        "product_image":        name,
        "diagram":              f"{name} diagram",
    }
    return titles.get(img_type, name)
