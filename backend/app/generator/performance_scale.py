"""
Performance and scalability testing dataset generation.

This module generates datasets for testing:
- Large-scale generation (100k+ topics)
- Deep hierarchy (10+ levels)
- Wide branching (1000+ children)
- Memory usage patterns
- Generation time profiling
"""

from typing import Dict, List, Tuple, Optional, Callable
import xml.etree.ElementTree as ET
import time
import psutil
import os
from app.generator.dita_utils import stable_id
from app.generator.generate import safe_join, sanitize_filename, _map_xml


class PerformanceMetrics:
    """Track performance metrics during generation."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.memory_start = None
        self.memory_end = None
        self.memory_peak = None
        self.topics_generated = 0
        self.maps_generated = 0
        self.files_generated = 0
        self.total_size = 0
    
    def start(self):
        """Start tracking."""
        self.start_time = time.time()
        process = psutil.Process(os.getpid())
        self.memory_start = process.memory_info().rss / 1024 / 1024  # MB
    
    def stop(self):
        """Stop tracking."""
        self.end_time = time.time()
        process = psutil.Process(os.getpid())
        self.memory_end = process.memory_info().rss / 1024 / 1024  # MB
        self.memory_peak = process.memory_info().peak_wss / 1024 / 1024 if hasattr(process.memory_info(), 'peak_wss') else self.memory_end
    
    def add_file(self, size: int):
        """Record file generation."""
        self.files_generated += 1
        self.total_size += size
    
    def add_topic(self):
        """Record topic generation."""
        self.topics_generated += 1
    
    def add_map(self):
        """Record map generation."""
        self.maps_generated += 1
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        duration = (self.end_time - self.start_time) if self.end_time and self.start_time else None
        memory_delta = (self.memory_end - self.memory_start) if self.memory_end and self.memory_start else None
        
        return {
            "duration_seconds": duration,
            "memory_start_mb": self.memory_start,
            "memory_end_mb": self.memory_end,
            "memory_peak_mb": self.memory_peak,
            "memory_delta_mb": memory_delta,
            "topics_generated": self.topics_generated,
            "maps_generated": self.maps_generated,
            "files_generated": self.files_generated,
            "total_size_bytes": self.total_size,
            "topics_per_second": self.topics_generated / duration if duration else None,
            "mb_per_second": (self.total_size / 1024 / 1024) / duration if duration else None,
        }


class ScalabilityGenerator:
    """Generate datasets for scalability testing."""
    
    def __init__(self, config, rand, metrics: Optional[PerformanceMetrics] = None):
        self.config = config
        self.rand = rand
        self.metrics = metrics or PerformanceMetrics()
    
    def generate_large_scale_dataset(
        self,
        base: str,
        topic_count: int = 100000,
        batch_size: int = 1000,
        stream_callback: Optional[Callable[[Dict[str, bytes]], None]] = None,
    ) -> Dict[str, bytes]:
        """
        Generate large-scale dataset (100k+ topics).
        
        Args:
            base: Base path for files
            topic_count: Number of topics to generate
            batch_size: Batch size for processing
            stream_callback: Optional callback function(file_batch_dict) to stream batches directly to storage.
                           If provided, files are written in batches instead of accumulating in memory.
        
        Returns:
            Dictionary of files (empty if stream_callback is used, otherwise full dict)
        """
        files = {} if stream_callback is None else None
        used_ids = set()
        topic_dir = safe_join(base, "topics", "pool")
        
        # Generate topics in batches to manage memory
        for batch_start in range(0, topic_count, batch_size):
            batch_end = min(batch_start + batch_size, topic_count)
            batch_files = {}
            
            for i in range(batch_start + 1, batch_end + 1):
                filename = sanitize_filename(f"topic_{i:08d}.dita", self.config.windows_safe_filenames)
                path = safe_join(topic_dir, filename)
                topic_id = stable_id(self.config.seed, "scale-topic", str(i), used_ids)
                
                topic_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
{self.config.doctype_topic}
<topic id="{topic_id}">
    <title>Topic {i:08d}</title>
    <body>
        <p>Content for topic {i}.</p>
    </body>
</topic>"""
                
                topic_bytes = topic_xml.encode('utf-8')
                
                if stream_callback:
                    batch_files[path] = topic_bytes
                else:
                    files[path] = topic_bytes
                
                if self.metrics:
                    self.metrics.add_topic()
                    self.metrics.add_file(len(topic_bytes))
            
            # Stream batch if callback provided
            if stream_callback and batch_files:
                stream_callback(batch_files)
                batch_files = {}  # Clear batch from memory
            
            # Log progress periodically for large datasets
            if batch_start % (batch_size * 10) == 0 and batch_start > 0:
                progress_pct = (batch_start / topic_count) * 100
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Large scale generation progress: {batch_start}/{topic_count} topics ({progress_pct:.1f}%)")
        
        # Generate map with all topics (only if not streaming or small dataset)
        if topic_count <= 5000 and (stream_callback is None or topic_count <= 1000):
            map_path = safe_join(base, "maps", "all_topics.ditamap")
            topicref_hrefs = [
                safe_join("topics", "pool", sanitize_filename(f"topic_{i:08d}.dita", self.config.windows_safe_filenames))
                for i in range(1, min(topic_count + 1, 5000))
            ]
            
            map_xml = _map_xml(
                self.config,
                map_id=stable_id(self.config.seed, "scale-map", "", used_ids),
                title=f"Large Scale Dataset ({topic_count} topics)",
                topicref_hrefs=topicref_hrefs,
                keydef_entries=[],
                scoped_blocks=[],
            )
            
            if stream_callback:
                stream_callback({map_path: map_xml})
            else:
                files[map_path] = map_xml
            
            if self.metrics:
                self.metrics.add_map()
                self.metrics.add_file(len(map_xml))
        
        return files
    
    def generate_deep_hierarchy_dataset(
        self,
        base: str,
        depth: int = 10,
        children_per_level: int = 5,
        include_maps: bool = True,
    ) -> Dict[str, bytes]:
        """Generate deep hierarchy dataset (10+ levels)."""
        files = {}
        used_ids = set()
        topic_dir = safe_join(base, "topics")
        
        # Calculate total topics needed
        total_topics = sum(children_per_level ** level for level in range(depth + 1))
        
        # Generate topics level by level
        level_topics = {}  # {level: [(path, id), ...]}
        
        for level in range(depth + 1):
            level_dir = safe_join(topic_dir, f"level_{level}")
            level_topics[level] = []
            
            topics_in_level = children_per_level ** level if level > 0 else 1
            
            for i in range(topics_in_level):
                filename = sanitize_filename(f"topic_l{level}_{i:05d}.dita", self.config.windows_safe_filenames)
                path = safe_join(level_dir, filename)
                topic_id = stable_id(self.config.seed, f"depth-l{level}", str(i), used_ids)
                
                topic_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
{self.config.doctype_topic}
<topic id="{topic_id}">
    <title>Level {level} Topic {i:05d}</title>
    <body>
        <p>Content at depth level {level}.</p>
    </body>
</topic>"""
                
                topic_bytes = topic_xml.encode('utf-8')
                files[path] = topic_bytes
                level_topics[level].append((path, topic_id))
                
                if self.metrics:
                    self.metrics.add_topic()
                    self.metrics.add_file(len(topic_bytes))
        
        # Generate maps for each level (if include_maps is True)
        if include_maps:
            maps_dir = safe_join(base, "maps")
            for level in range(depth):
                if level == 0:
                    # Root level map
                    parent_topics = level_topics[0]
                    child_topics = level_topics[1]
                else:
                    # Use topics from previous level as parents
                    parent_topics = level_topics[level]
                    child_topics = level_topics[level + 1]
                
                # Create map with parent-child relationships
                map_path = safe_join(maps_dir, f"level_{level}_map.ditamap")
                
                # Generate topicrefs
                topicref_hrefs = []
                for parent_path, _ in parent_topics[:min(len(parent_topics), 10)]:  # Limit for performance
                    topicref_hrefs.append(parent_path)
                
                map_xml = _map_xml(
                    self.config,
                    map_id=stable_id(self.config.seed, f"depth-map-l{level}", "", used_ids),
                    title=f"Level {level} Map",
                    topicref_hrefs=topicref_hrefs,
                    keydef_entries=[],
                    scoped_blocks=[],
                )
                files[map_path] = map_xml
                
                if self.metrics:
                    self.metrics.add_map()
                    self.metrics.add_file(len(map_xml))
        
        return files
    
    def generate_wide_branching_dataset(
        self,
        base: str,
        root_topics: int = 10,
        children_per_root: int = 1000,
    ) -> Dict[str, bytes]:
        """Generate wide branching dataset (1000+ children)."""
        files = {}
        used_ids = set()
        topic_dir = safe_join(base, "topics")
        
        # Generate root topics
        root_dir = safe_join(topic_dir, "roots")
        root_topics_list = []
        
        for i in range(1, root_topics + 1):
            filename = sanitize_filename(f"root_{i:05d}.dita", self.config.windows_safe_filenames)
            path = safe_join(root_dir, filename)
            topic_id = stable_id(self.config.seed, "root", str(i), used_ids)
            
            topic_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
{self.config.doctype_topic}
<topic id="{topic_id}">
    <title>Root Topic {i:05d}</title>
    <body>
        <p>Root topic {i}.</p>
    </body>
</topic>"""
            
            topic_bytes = topic_xml.encode('utf-8')
            files[path] = topic_bytes
            root_topics_list.append((path, topic_id))
            
            if self.metrics:
                self.metrics.add_topic()
                self.metrics.add_file(len(topic_bytes))
        
        # Generate children for each root
        for root_idx, (root_path, root_id) in enumerate(root_topics_list):
            children_dir = safe_join(topic_dir, "children", f"root_{root_idx + 1}")
            children_list = []
            
            for i in range(1, children_per_root + 1):
                filename = sanitize_filename(f"child_{i:05d}.dita", self.config.windows_safe_filenames)
                path = safe_join(children_dir, filename)
                topic_id = stable_id(self.config.seed, f"child-r{root_idx}", str(i), used_ids)
                
                topic_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
{self.config.doctype_topic}
<topic id="{topic_id}">
    <title>Child {i:05d} of Root {root_idx + 1}</title>
    <body>
        <p>Child topic {i}.</p>
    </body>
</topic>"""
                
                topic_bytes = topic_xml.encode('utf-8')
                files[path] = topic_bytes
                children_list.append((path, topic_id))
                
                if self.metrics:
                    self.metrics.add_topic()
                    self.metrics.add_file(len(topic_bytes))
            
            # Generate map for root with all children
            map_path = safe_join(base, "maps", f"root_{root_idx + 1}_map.ditamap")
            
            # Limit topicrefs for performance (first 500 children)
            topicref_hrefs = [path for path, _ in children_list[:500]]
            topicref_hrefs.insert(0, root_path)  # Add root first
            
            map_xml = _map_xml(
                self.config,
                map_id=stable_id(self.config.seed, f"wide-map-r{root_idx}", "", used_ids),
                title=f"Root {root_idx + 1} Map ({len(children_list)} children)",
                topicref_hrefs=topicref_hrefs,
                keydef_entries=[],
                scoped_blocks=[],
            )
            files[map_path] = map_xml
            
            if self.metrics:
                self.metrics.add_map()
                self.metrics.add_file(len(map_xml))
        
        return files
    
    def generate_incremental_topicref_maps_dataset(
        self,
        base: str,
        pool_size: int,
        map_topicref_counts: List[int],
        deep_folders: bool = False,
    ) -> Dict[str, bytes]:
        """Generate incremental topicref maps dataset."""
        files = {}
        used_ids = set()
        
        # Generate topic pool
        topic_dir = safe_join(base, "topics", "pool")
        pool_topics = []
        
        for i in range(1, pool_size + 1):
            if deep_folders:
                # Create deep folder structure: topics/pool/level1/level2/level3/topic_N.dita
                level1 = (i - 1) // 1000
                level2 = ((i - 1) % 1000) // 100
                level3 = ((i - 1) % 100) // 10
                folder_path = safe_join(topic_dir, f"level1_{level1}", f"level2_{level2}", f"level3_{level3}")
            else:
                folder_path = topic_dir
            
            filename = sanitize_filename(f"topic_{i:05d}.dita", self.config.windows_safe_filenames)
            path = safe_join(folder_path, filename)
            topic_id = stable_id(self.config.seed, "pool", str(i), used_ids)
            
            topic_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
{self.config.doctype_topic}
<topic id="{topic_id}">
    <title>Pool Topic {i:05d}</title>
    <body>
        <p>Topic {i} from the pool.</p>
    </body>
</topic>"""
            
            topic_bytes = topic_xml.encode('utf-8')
            files[path] = topic_bytes
            pool_topics.append(path)
            
            if self.metrics:
                self.metrics.add_topic()
                self.metrics.add_file(len(topic_bytes))
        
        # Generate maps with incremental topicref counts
        maps_dir = safe_join(base, "maps")
        for idx, topicref_count in enumerate(map_topicref_counts):
            map_id = stable_id(self.config.seed, "incr-map", str(idx), used_ids)
            map_filename = sanitize_filename(f"map_{idx:02d}_{topicref_count}_topicrefs.ditamap", self.config.windows_safe_filenames)
            map_path = safe_join(maps_dir, map_filename)
            
            # Select topics from pool (up to topicref_count)
            selected_topics = pool_topics[:min(topicref_count, len(pool_topics))]
            
            map_xml = _map_xml(
                self.config,
                map_id=map_id,
                title=f"Incremental Map {idx + 1} ({topicref_count} topicrefs)",
                topicref_hrefs=selected_topics,
                keydef_entries=[],
                scoped_blocks=[],
            )
            files[map_path] = map_xml
            
            if self.metrics:
                self.metrics.add_map()
                self.metrics.add_file(len(map_xml))
        
        return files


def generate_performance_test_dataset(
    config,
    base: str,
    test_type: str = "large_scale",
    test_params: Dict = None,
    rand=None,
    stream_callback: Optional[Callable[[Dict[str, bytes]], None]] = None,
) -> Tuple[Dict[str, bytes], Dict]:
    """
    Generate performance test dataset.
    
    Args:
        config: DatasetConfig
        base: Base path
        test_type: "large_scale", "deep_hierarchy", "wide_branching"
        test_params: Parameters for test type
        rand: Random generator
        stream_callback: Optional callback for streaming batches directly to storage
    
    Returns:
        Tuple of (files_dict, metrics_dict). files_dict will be empty if stream_callback is used.
    """
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    if test_params is None:
        test_params = {}
    
    metrics = PerformanceMetrics()
    metrics.start()
    
    generator = ScalabilityGenerator(config, rand, metrics)
    
    if test_type == "large_scale":
        topic_count = test_params.get("topic_count", 100000)
        batch_size = test_params.get("batch_size", 1000)
        files = generator.generate_large_scale_dataset(base, topic_count, batch_size, stream_callback)
    
    elif test_type == "deep_hierarchy":
        depth = test_params.get("depth", 10)
        children_per_level = test_params.get("children_per_level", 5)
        include_maps = test_params.get("include_maps", True)
        files = generator.generate_deep_hierarchy_dataset(base, depth, children_per_level, include_maps)
    
    elif test_type == "wide_branching":
        root_topics = test_params.get("root_topics", 10)
        children_per_root = test_params.get("children_per_root", 1000)
        files = generator.generate_wide_branching_dataset(base, root_topics, children_per_root)
    
    elif test_type == "incremental_topicref_maps":
        pool_size = test_params.get("pool_size", 10000)
        map_topicref_counts = test_params.get("map_topicref_counts", [10, 100, 1000, 5000, 10000])
        deep_folders = test_params.get("deep_folders", False)
        files = generator.generate_incremental_topicref_maps_dataset(
            base, pool_size, map_topicref_counts, deep_folders
        )
    
    else:
        raise ValueError(f"Unknown test type: {test_type}")
    
    metrics.stop()
    
    return files, metrics.to_dict()
