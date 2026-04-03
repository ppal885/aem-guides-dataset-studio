"""
Unit tests for keyscope demo generator.
"""
import pytest
import xml.etree.ElementTree as ET
from app.generator.keyscope_demo import generate_keyscope_demo_dataset
from app.generator.dita_utils import is_valid_dita_id
from app.jobs.schemas import DatasetConfig


@pytest.fixture
def sample_config():
    """Create sample dataset config."""
    return DatasetConfig(
        name="Test Keyscope Demo",
        seed="test",
        doctype_topic='<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
        doctype_map='<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
    )


class TestKeyscopeDemoGeneration:
    """Test keyscope demo dataset generation."""
    
    def test_generates_all_files(self, sample_config):
        """Test that all required files are generated."""
        files = generate_keyscope_demo_dataset(sample_config, "test_base")
        
        assert "test_base/aem_guides_keyscope_demo/maps/root_map.ditamap" in files
        assert "test_base/aem_guides_keyscope_demo/maps/submap_s1.ditamap" in files
        assert "test_base/aem_guides_keyscope_demo/maps/submap_s2.ditamap" in files
        assert "test_base/aem_guides_keyscope_demo/topics/root_target.dita" in files
        assert "test_base/aem_guides_keyscope_demo/topics/s1_target.dita" in files
        assert "test_base/aem_guides_keyscope_demo/topics/s2_target.dita" in files
        assert "test_base/aem_guides_keyscope_demo/topics/consumer_root.dita" in files
        assert "test_base/aem_guides_keyscope_demo/topics/consumer_s1.dita" in files
        assert "test_base/aem_guides_keyscope_demo/topics/consumer_s2.dita" in files
        assert "test_base/aem_guides_keyscope_demo/README.txt" in files
    
    def test_all_ids_are_dita_compliant(self, sample_config):
        """Test that all generated IDs are DITA-compliant."""
        files = generate_keyscope_demo_dataset(sample_config, "test_base")
        
        for file_path, content in files.items():
            if file_path.endswith(('.dita', '.ditamap')):
                try:
                    root = ET.fromstring(content)
                    if 'id' in root.attrib:
                        assert is_valid_dita_id(root.attrib['id']), f"Invalid ID in {file_path}: {root.attrib['id']}"
                except ET.ParseError:
                    pass
    
    def test_no_broken_hrefs(self, sample_config):
        """Test that all href references exist."""
        files = generate_keyscope_demo_dataset(sample_config, "test_base")
        
        file_paths = set(files.keys())
        
        for file_path, content in files.items():
            if file_path.endswith('.ditamap'):
                try:
                    root = ET.fromstring(content)
                    for elem in root.iter():
                        if 'href' in elem.attrib:
                            href = elem.attrib['href']
                            if href.startswith('../'):
                                relative_path = file_path.rsplit('/', 1)[0] + '/' + href
                                normalized = relative_path.replace('//', '/')
                                assert normalized in file_paths or any(normalized.endswith(f) for f in file_paths), \
                                    f"Broken href in {file_path}: {href}"
                except ET.ParseError:
                    pass
    
    def test_root_map_structure(self, sample_config):
        """Test root map structure."""
        files = generate_keyscope_demo_dataset(sample_config, "test_base")
        root_map_path = "test_base/aem_guides_keyscope_demo/maps/root_map.ditamap"
        
        assert root_map_path in files
        root = ET.fromstring(files[root_map_path])
        
        assert root.tag == "map"
        assert 'id' in root.attrib
        assert is_valid_dita_id(root.attrib['id'])
        
        keydefs = [e for e in root if e.tag == "keydef"]
        assert len(keydefs) == 1
        assert keydefs[0].get("keys") == "prod"
        
        maprefs = [e for e in root if e.tag == "mapref"]
        assert len(maprefs) == 2
        assert any(m.get("keyscope") == "s1" for m in maprefs)
        assert any(m.get("keyscope") == "s2" for m in maprefs)
    
    def test_submap_s1_structure(self, sample_config):
        """Test submap S1 structure."""
        files = generate_keyscope_demo_dataset(sample_config, "test_base")
        submap_path = "test_base/aem_guides_keyscope_demo/maps/submap_s1.ditamap"
        
        assert submap_path in files
        root = ET.fromstring(files[submap_path])
        
        assert root.tag == "map"
        keydefs = [e for e in root if e.tag == "keydef"]
        assert len(keydefs) == 1
        assert keydefs[0].get("keys") == "prod"
    
    def test_qualified_keyrefs_included(self, sample_config):
        """Test that qualified keyrefs are included when requested."""
        files = generate_keyscope_demo_dataset(
            sample_config,
            "test_base",
            include_qualified_keyrefs=True
        )
        
        consumer_s1_path = "test_base/aem_guides_keyscope_demo/topics/consumer_s1.dita"
        content = files[consumer_s1_path].decode("utf-8")
        assert "s1.prod" in content
    
    def test_qualified_keyrefs_excluded(self, sample_config):
        """Test that qualified keyrefs are excluded when not requested."""
        files = generate_keyscope_demo_dataset(
            sample_config,
            "test_base",
            include_qualified_keyrefs=False
        )
        
        consumer_s1_path = "test_base/aem_guides_keyscope_demo/topics/consumer_s1.dita"
        content = files[consumer_s1_path].decode("utf-8")
        assert "s1.prod" not in content
