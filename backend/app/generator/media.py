"""
Media and asset generation for AEM Guides datasets.

This module generates image references, placeholder images, and media assets.
"""

from typing import Dict, List, Tuple, Optional
import xml.etree.ElementTree as ET
import base64
from io import BytesIO

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_AVAILABLE = True
except ImportError:
    Image = ImageDraw = ImageFont = None  # type: ignore
    _PIL_AVAILABLE = False

from app.generator.dita_utils import stable_id
from app.generator.generate import safe_join, sanitize_filename


class MediaAssetGenerator:
    """Generate media assets and references."""
    
    def __init__(self, config, rand):
        self.config = config
        self.rand = rand
    
    def generate_placeholder_image(
        self,
        width: int = 800,
        height: int = 600,
        text: str = "Placeholder",
        format: str = "PNG",
    ) -> bytes:
        """Generate a placeholder image."""
        if not _PIL_AVAILABLE or Image is None:
            return base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
            )
        try:
            # Create image
            img = Image.new('RGB', (width, height), color='lightgray')
            draw = ImageDraw.Draw(img)
            
            # Try to use a font, fallback to default
            try:
                font = ImageFont.truetype("arial.ttf", 40)
            except Exception:
                font = ImageFont.load_default()
            
            # Calculate text position (center)
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            position = ((width - text_width) // 2, (height - text_height) // 2)
            
            # Draw text
            draw.text(position, text, fill='black', font=font)
            
            # Draw border
            draw.rectangle([0, 0, width-1, height-1], outline='gray', width=2)
            
            # Convert to bytes
            img_bytes = BytesIO()
            img.save(img_bytes, format=format)
            return img_bytes.getvalue()
        except Exception:
            # Fallback: return minimal valid PNG
            # 1x1 transparent PNG
            return base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
            )
    
    def generate_image_reference(
        self,
        image_path: str,
        alt_text: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        placement: str = "inline",
    ) -> ET.Element:
        """Generate an image element."""
        image = ET.Element("image")
        image.set("href", image_path)
        image.set("alt", alt_text)
        
        if width:
            image.set("width", str(width))
        if height:
            image.set("height", str(height))
        
        image.set("placement", placement)
        
        return image
    
    def generate_image_map(
        self,
        image_id: str,
        image_path: str,
        areas: List[Dict],
    ) -> Tuple[ET.Element, ET.Element]:
        """Generate an image with image map."""
        # Image element
        image = self.generate_image_reference(image_path, "Image with map")
        image.set("id", image_id)
        image.set("usemap", f"#{image_id}_map")
        
        # Image map
        imagemap = ET.Element("imagemap")
        imagemap.set("id", f"{image_id}_map")
        
        for area in areas:
            area_elem = ET.SubElement(imagemap, "area")
            area_elem.set("shape", area.get("shape", "rect"))
            area_elem.set("coords", area.get("coords", ""))
            area_elem.set("href", area.get("href", "#"))
            if "alt" in area:
                area_elem.set("alt", area["alt"])
        
        return image, imagemap
    
    def generate_media_references_dataset(
        self,
        base: str,
        topic_count: int = 50,
        images_per_topic: int = 3,
        generate_images: bool = True,
        include_map: bool = True,
    ) -> Dict[str, bytes]:
        """Generate a dataset with media references."""
        files = {}
        topic_dir = safe_join(base, "topics", "pool")
        images_dir = safe_join(base, "assets", "images")
        topic_paths = []
        
        # Generate placeholder images
        if generate_images:
            for i in range(1, topic_count * images_per_topic + 1):
                image_filename = sanitize_filename(f"image_{i:05d}.png", self.config.windows_safe_filenames)
                image_path = safe_join(images_dir, image_filename)
                
                image_bytes = self.generate_placeholder_image(
                    width=800,
                    height=600,
                    text=f"Image {i}",
                )
                files[image_path] = image_bytes
        
        # Generate topics with image references
        used_ids = set()
        for i in range(1, topic_count + 1):
            topic_filename = sanitize_filename(f"topic_{i:05d}.dita", self.config.windows_safe_filenames)
            topic_path = safe_join(topic_dir, topic_filename)
            topic_id = stable_id(self.config.seed, "media-topic", str(i), used_ids)
            
            # Create topic
            topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
            title = ET.SubElement(topic, "title")
            title.text = f"Topic with Media {i:05d}"
            
            body = ET.SubElement(topic, "body")
            
            # Add paragraphs with images
            for j in range(images_per_topic):
                p = ET.SubElement(body, "p")
                p.text = f"Content before image {j+1}."
                
                image_idx = (i - 1) * images_per_topic + j + 1
                image_filename = sanitize_filename(f"image_{image_idx:05d}.png", self.config.windows_safe_filenames)
                image_rel_path = f"../assets/images/{image_filename}"
                
                image_elem = self.generate_image_reference(
                    image_rel_path,
                    f"Image {image_idx}",
                    width=800,
                    height=600,
                )
                body.append(image_elem)
            
            # Generate XML
            xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
            doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{self.config.doctype_topic}\n'
            files[topic_path] = doc.encode("utf-8") + xml_body
            topic_paths.append(topic_path)
        
        # Generate map if requested
        if include_map:
            from app.generator.generate import _map_xml, _rel_href
            
            map_filename = sanitize_filename("media_rich_content.ditamap", self.config.windows_safe_filenames)
            map_path = safe_join(base, map_filename)
            map_id = stable_id(self.config.seed, "media_map", "", used_ids)
            
            hrefs = [_rel_href(map_path, tp) for tp in topic_paths]
            
            map_xml = _map_xml(
                self.config,
                map_id=map_id,
                title="Media Rich Content Map",
                topicref_hrefs=hrefs,
                keydef_entries=[],
                scoped_blocks=[],
            )
            files[map_path] = map_xml
        
        return files
    
    def generate_dam_metadata(
        self,
        asset_path: str,
        asset_type: str = "image",
        mime_type: str = "image/png",
    ) -> Dict:
        """Generate DAM asset metadata."""
        return {
            "jcr:primaryType": "dam:Asset",
            "jcr:content": {
                "jcr:primaryType": "nt:resource",
                "jcr:mimeType": mime_type,
                "dam:size": 0,  # Will be updated
                "dc:format": mime_type,
            },
            "metadata": {
                "jcr:primaryType": "nt:unstructured",
                "dc:title": asset_path.split("/")[-1],
                "dc:format": mime_type,
                "dam:assetState": "active",
            }
        }


def generate_media_rich_dataset(
    config,
    base: str,
    topic_count: int = 50,
    images_per_topic: int = 3,
    generate_images: bool = True,
    include_map: bool = True,
    rand=None,
) -> Dict[str, bytes]:
    """Generate a dataset with media assets."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    generator = MediaAssetGenerator(config, rand)
    return generator.generate_media_references_dataset(
        base,
        topic_count,
        images_per_topic,
        generate_images,
        include_map=include_map,
    )


RECIPE_SPECS = [
    {
        "id": "media_rich_content",
        "title": "Media Rich Content",
        "description": "Generate topics with embedded images and media references",
        "tags": ["media", "images", "assets"],
        "module": "app.generator.media",
        "function": "generate_media_rich_dataset",
        "params_schema": {"topic_count": "int", "images_per_topic": "int", "generate_images": "bool"},
        "default_params": {"topic_count": 50, "images_per_topic": 3, "generate_images": True},
        "stability": "stable",
    },
]
