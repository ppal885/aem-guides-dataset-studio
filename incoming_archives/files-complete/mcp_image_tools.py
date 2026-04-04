# ─────────────────────────────────────────────────────────────────────────────
# ADD THESE TOOLS TO mcp_server.py
# Image pipeline — Jira attachments → DITA fig elements
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_issue_images(issue_key: str) -> str:
    """
    Check what image attachments are available for a Jira issue.
    Downloads them locally and returns metadata.

    Always call this BEFORE generate_dita_from_jira if you want
    images included in the generated DITA.

    Returns: list of images with filename, alt text, AEM DAM path.
    """
    try:
        from backend.app.services.dita_image_service import get_image_summary
        return get_image_summary(issue_key)
    except Exception as e:
        return f"Error fetching images for {issue_key}: {e}"


@mcp.tool()
def generate_dita_with_images(
    issue_key: str,
    dita_content: str,
    include_flowchart: bool = True,
) -> str:
    """
    Take generated DITA XML and inject images from Jira attachments.

    Steps:
    1. Fetches image attachments from Jira for issue_key
    2. Copies images to output/dita/images/
    3. Generates flowchart SVG from task steps (if task topic)
    4. Injects <fig> elements into the DITA XML
    5. Returns updated DITA with images included

    Use this AFTER generating DITA content but BEFORE saving.

    include_flowchart: set True for task topics to auto-generate
                       a process flowchart from the steps
    """
    try:
        from backend.app.services.dita_image_service import (
            build_dita_fig_elements_for_issue,
            save_flowchart_for_task,
            inject_images_into_dita,
        )

        output_dir = PROJECT_ROOT / "output" / "dita"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Get screenshot fig elements from Jira attachments
        fig_elements = build_dita_fig_elements_for_issue(issue_key, output_dir)

        # Generate flowchart if task topic
        flowchart = None
        if include_flowchart and "<taskbody>" in dita_content:
            # Extract steps from DITA
            import re
            cmd_re  = re.compile(r"<cmd[^>]*>([\s\S]*?)</cmd>", re.IGNORECASE)
            steps   = [
                m.group(1).replace("<[^>]+>", "").strip()
                for m in cmd_re.finditer(dita_content)
            ]
            steps = [re.sub(r"<[^>]+>", "", s).strip() for s in steps if s]

            if steps:
                # Extract title
                title_m = re.search(r"<title[^>]*>([\s\S]*?)</title>", dita_content, re.IGNORECASE)
                title   = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""
                flowchart = save_flowchart_for_task(steps, issue_key, output_dir, title)

        # Inject into DITA
        updated_dita = inject_images_into_dita(dita_content, fig_elements, flowchart)

        # Summary
        summary_parts = []
        if fig_elements:
            summary_parts.append(f"{len(fig_elements)} screenshot(s) added")
        if flowchart:
            summary_parts.append("flowchart generated")
        if not summary_parts:
            summary_parts.append("no images found in Jira attachments")

        return f"""
IMAGE INJECTION COMPLETE
{'='*50}
Issue:   {issue_key}
Result:  {', '.join(summary_parts)}

{'Images added:' if fig_elements else 'No screenshots found.'}
{chr(10).join(f'  - {f["filename"]} → {f["dita_href"]}' for f in fig_elements)}

{'Flowchart: output/dita/images/' + issue_key.lower() + '-flowchart.svg' if flowchart else ''}

UPDATED DITA XML:
{'='*50}
{updated_dita}
"""
    except Exception as e:
        return f"Error injecting images: {e}\n\nOriginal DITA:\n{dita_content}"


@mcp.tool()
def generate_flowchart(
    steps: list,
    issue_key: str,
    title: str = "",
) -> str:
    """
    Generate a process flowchart SVG from a list of steps.
    Saves to output/dita/images/<issue_key>-flowchart.svg

    steps: list of step strings e.g. ["Open the map", "Add keydef", "Save"]
    title: optional chart title

    Use for task topics to give readers a visual overview of the procedure.
    """
    try:
        from backend.app.services.dita_image_service import (
            save_flowchart_for_task,
            build_dita_fig_element,
        )

        output_dir = PROJECT_ROOT / "output" / "dita"
        output_dir.mkdir(parents=True, exist_ok=True)

        flowchart = save_flowchart_for_task(
            steps=steps,
            issue_key=issue_key,
            output_dir=output_dir,
            title=title,
        )

        if not flowchart:
            return "No steps provided — flowchart not generated"

        fig_xml = build_dita_fig_element(flowchart, f"fig_{issue_key.lower()}_flow")

        return f"""
✅ Flowchart generated:
  File:     output/dita/images/{issue_key.lower()}-flowchart.svg
  Steps:    {len(steps)}
  AEM DAM:  {flowchart['aem_dam_path']}

DITA fig element to insert:
{fig_xml}
"""
    except Exception as e:
        return f"Error generating flowchart: {e}"


@mcp.tool()
def list_issue_images(issue_key: str) -> str:
    """
    List all image attachments for a Jira issue with their details.
    Shows filename, size, mime type, and suggested AEM DAM path.
    """
    try:
        from backend.app.services.dita_image_service import get_image_attachments
        images = get_image_attachments(issue_key)

        if not images:
            return f"No image attachments found for {issue_key}"

        lines = [f"Images for {issue_key} ({len(images)} total):\n"]
        for i, img in enumerate(images, 1):
            lines.append(f"""
{i}. {img['filename']}
   Type:     {img['mime_type']}
   Size:     {img['size_bytes']} bytes
   Alt text: {img['alt_text']}
   AEM DAM:  {img['aem_dam_path']}
   DITA href: images/{img['filename']}""")

        return "\n".join(lines)
    except Exception as e:
        return f"Error listing images: {e}"
