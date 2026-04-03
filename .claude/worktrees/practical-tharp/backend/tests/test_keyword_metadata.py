"""
Unit tests for keyword metadata generator.
"""
import pytest
import xml.etree.ElementTree as ET
from app.generator.keyword_metadata import generate_keyword_metadata_dataset
from app.jobs.schemas import DatasetConfig


@pytest.fixture
def sample_config():
    """Sample dataset configuration."""
    return DatasetConfig(
        name="Test Keyword Metadata",
        doctype_topic='<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">',
        doctype_map='<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">',
    )


class TestKeywordMetadataGeneration:
    """Test keyword metadata dataset generation."""
    
    def test_basic_generation(self, sample_config):
        """Test basic dataset generation."""
        files = generate_keyword_metadata_dataset(sample_config, "test_base")
        
        assert "test_base/aem_guides_keyword_metadata/maps/master.ditamap" in files
        assert "test_base/aem_guides_keyword_metadata/maps/metadata_map.ditamap" in files
        assert "test_base/aem_guides_keyword_metadata/README.txt" in files
    
    def test_metadata_topics_generated(self, sample_config):
        """Test that metadata topics are generated."""
        files = generate_keyword_metadata_dataset(sample_config, "test_base", num_keywords=5, num_categories=3)
        
        assert "test_base/aem_guides_keyword_metadata/topics/metadata/keyword_1.dita" in files
        assert "test_base/aem_guides_keyword_metadata/topics/metadata/keyword_5.dita" in files
        assert "test_base/aem_guides_keyword_metadata/topics/metadata/category_1.dita" in files
        assert "test_base/aem_guides_keyword_metadata/topics/metadata/category_3.dita" in files
        assert "test_base/aem_guides_keyword_metadata/topics/metadata/tag_beginner.dita" in files
        assert "test_base/aem_guides_keyword_metadata/topics/metadata/tag_advanced.dita" in files
    
    def test_consumer_topics_generated(self, sample_config):
        """Test that consumer topics are generated."""
        files = generate_keyword_metadata_dataset(sample_config, "test_base", num_topics=5)
        
        assert "test_base/aem_guides_keyword_metadata/topics/consumer_topic_1.dita" in files
        assert "test_base/aem_guides_keyword_metadata/topics/consumer_topic_5.dita" in files
    
    def test_metadata_map_structure(self, sample_config):
        """Test metadata map structure."""
        files = generate_keyword_metadata_dataset(sample_config, "test_base", num_keywords=3, num_categories=2)
        metadata_map_path = "test_base/aem_guides_keyword_metadata/maps/metadata_map.ditamap"
        
        assert metadata_map_path in files
        root = ET.fromstring(files[metadata_map_path].decode("utf-8").split("\n", 1)[1])
        
        keydefs = root.findall(".//keydef")
        assert len(keydefs) >= 5
        
        kw_keys = [k.get("keys") for k in keydefs if k.get("keys", "").startswith("kw-")]
        assert "kw-1" in kw_keys
        assert "kw-3" in kw_keys
        
        cat_keys = [k.get("keys") for k in keydefs if k.get("keys", "").startswith("cat-")]
        assert "kw-1" in kw_keys
        assert "cat-2" in cat_keys
    
    def test_master_map_structure(self, sample_config):
        """Test master map structure."""
        files = generate_keyword_metadata_dataset(sample_config, "test_base", num_topics=3)
        master_map_path = "test_base/aem_guides_keyword_metadata/maps/master.ditamap"
        
        assert master_map_path in files
        root = ET.fromstring(files[master_map_path].decode("utf-8").split("\n", 1)[1])
        
        maprefs = root.findall(".//mapref")
        assert len(maprefs) == 1
        
        metadata_mapref = maprefs[0]
        assert metadata_mapref.get("href") == "metadata_map.ditamap"
        assert metadata_mapref.get("processing-role") == "resource-only"
        
        topicrefs = root.findall(".//topicref")
        assert len(topicrefs) == 3
    
    def test_keyword_topics_have_metadata(self, sample_config):
        """Test that keyword topics contain metadata."""
        files = generate_keyword_metadata_dataset(sample_config, "test_base", num_keywords=2)
        keyword_path = "test_base/aem_guides_keyword_metadata/topics/metadata/keyword_1.dita"
        
        assert keyword_path in files
        root = ET.fromstring(files[keyword_path].decode("utf-8").split("\n", 1)[1])
        
        prolog = root.find(".//prolog")
        assert prolog is not None
        
        metadata = prolog.find(".//metadata")
        assert metadata is not None
        
        keywords = metadata.find(".//keywords")
        assert keywords is not None
    
    def test_consumer_topics_reference_keys(self, sample_config):
        """Test that consumer topics reference metadata keys."""
        files = generate_keyword_metadata_dataset(sample_config, "test_base", num_keywords=3, num_topics=2)
        consumer_path = "test_base/aem_guides_keyword_metadata/topics/consumer_topic_1.dita"
        
        assert consumer_path in files
        content = files[consumer_path].decode("utf-8")
        
        assert 'keyref="kw-1"' in content or 'keyref="kw-1"' in content.replace('"', '"')
    
    def test_custom_id_prefix(self, sample_config):
        """Test custom ID prefix."""
        files = generate_keyword_metadata_dataset(sample_config, "test_base", id_prefix="meta", num_keywords=2)
        
        keyword_path = "test_base/aem_guides_keyword_metadata/topics/metadata/keyword_1.dita"
        assert keyword_path in files
        
        root = ET.fromstring(files[keyword_path].decode("utf-8").split("\n", 1)[1])
        topic_id = root.get("id", "")
        
        assert topic_id.startswith("meta")
    
    def test_xml_well_formed(self, sample_config):
        """Test that all XML is well-formed."""
        files = generate_keyword_metadata_dataset(sample_config, "test_base", num_keywords=3, num_categories=2, num_topics=3)
        
        for path, content in files.items():
            if path.endswith((".dita", ".ditamap")):
                try:
                    xml_content = content.decode("utf-8")
                    xml_content = xml_content.split("\n", 1)[1]
                    ET.fromstring(xml_content)
                except ET.ParseError as e:
                    pytest.fail(f"XML parsing failed for {path}: {e}")
