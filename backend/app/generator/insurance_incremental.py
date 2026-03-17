"""
Insurance Incremental Maps dataset generation.

This module generates insurance domain DITA content with:
- Large pool of insurance topics (10k+)
- Multiple maps with incremental topicref counts (10, 100, 1k, 5k, 10k)
- Insurance-specific content: policies, claims, underwriting, compliance
- Rotating themes: Term Life, Health, Motor, Endorsements, Surveyor Notes
- DTD-safe IDs (start with letter)
"""

from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
from app.generator.dita_utils import make_dita_id
from app.generator.generate import safe_join, sanitize_filename, _map_xml
from app.utils.xml_escape import xml_escape_text, xml_escape_attr


class InsuranceContentGenerator:
    """Generate insurance domain DITA content."""
    
    def __init__(self, config, rand):
        self.config = config
        self.rand = rand
        
        # Insurance domain content templates
        self.themes = [
            "term_life",
            "health",
            "motor",
            "endorsements",
            "surveyor_notes"
        ]
        
        # Content snippets for each theme
        self.content_templates = {
            "term_life": {
                "title_prefix": "Term Life Insurance",
                "overview": "Term life insurance provides coverage for a specified period. Premiums are typically lower than whole life policies.",
                "sections": [
                    ("Underwriting Guidelines", "Underwriting assesses risk factors including age, health history, and lifestyle. Premium rates vary based on risk classification."),
                    ("Rider Options", "Common riders include accidental death benefit, disability waiver, and accelerated death benefit riders."),
                    ("Premium Structure", "Premiums are calculated based on coverage amount, term length, age, and health status.")
                ]
            },
            "health": {
                "title_prefix": "Health Insurance",
                "overview": "Health insurance covers medical expenses including hospitalization, outpatient care, and preventive services.",
                "sections": [
                    ("KYC Requirements", "Know Your Customer (KYC) verification includes identity proof, address verification, and medical history disclosure."),
                    ("Coverage Matrix", "Coverage includes hospitalization, day care procedures, pre and post hospitalization expenses, and annual health check-ups."),
                    ("Compliance", "Policies must comply with IRDAI regulations including portability, renewal guarantees, and claim settlement timelines.")
                ]
            },
            "motor": {
                "title_prefix": "Motor Insurance",
                "overview": "Motor insurance provides coverage for vehicles against damage, theft, and third-party liability.",
                "sections": [
                    ("FNOL Process", "First Notice of Loss (FNOL) must be reported within 24 hours. Required documents include RC copy, driving license, and claim form."),
                    ("Claim Workflow", "Claim processing involves surveyor inspection, damage assessment, repair authorization, and settlement approval."),
                    ("Surveyor Notes", "Surveyor documents vehicle condition, damage extent, repair estimates, and recommends claim approval or rejection.")
                ]
            },
            "endorsements": {
                "title_prefix": "Policy Endorsements",
                "overview": "Endorsements modify existing policies to add, remove, or change coverage terms.",
                "sections": [
                    ("Exclusion Clauses", "Common exclusions include war risks, nuclear perils, intentional damage, and pre-existing conditions."),
                    ("Coverage Extensions", "Endorsements can extend coverage to additional drivers, geographical areas, or specific perils."),
                    ("Premium Adjustments", "Endorsements may result in premium increases or decreases based on risk modification.")
                ]
            },
            "surveyor_notes": {
                "title_prefix": "Surveyor Assessment",
                "overview": "Surveyor notes document claim assessment, damage evaluation, and settlement recommendations.",
                "sections": [
                    ("Triage Process", "Initial triage categorizes claims by severity, urgency, and complexity for appropriate handling."),
                    ("Documentation Requirements", "Required documents include photographs, repair estimates, police reports, and medical certificates."),
                    ("Assessment Summary", "Surveyor provides detailed assessment including cause of loss, extent of damage, and recommended settlement amount.")
                ]
            }
        }
    
    def generate_premium_slab_table(self) -> ET.Element:
        """Generate premium slab simpletable."""
        simpletable = ET.Element("simpletable")
        simpletable.set("relcolwidth", xml_escape_attr("1* 1* 1*"))
        
        # Header
        sthead = ET.SubElement(simpletable, "sthead")
        strow = ET.SubElement(sthead, "strow")
        for header in ["Age Group", "Coverage Amount", "Annual Premium"]:
            stentry = ET.SubElement(strow, "stentry")
            stentry.text = xml_escape_text(header)
        
        # Body rows
        stbody = ET.SubElement(simpletable, "stbody")
        age_groups = ["18-30", "31-40", "41-50", "51-60", "60+"]
        for age in age_groups:
            strow = ET.SubElement(stbody, "strow")
            stentry = ET.SubElement(strow, "stentry")
            stentry.text = xml_escape_text(age)
            stentry = ET.SubElement(strow, "stentry")
            stentry.text = xml_escape_text(f"?{self.rand.randint(5, 50)}L")
            stentry = ET.SubElement(strow, "stentry")
            stentry.text = xml_escape_text(f"?{self.rand.randint(10, 100)}K")
        
        return simpletable
    
    def generate_coverage_matrix_table(self) -> ET.Element:
        """Generate coverage matrix simpletable."""
        simpletable = ET.Element("simpletable")
        simpletable.set("relcolwidth", xml_escape_attr("1* 1* 1*"))
        
        sthead = ET.SubElement(simpletable, "sthead")
        strow = ET.SubElement(sthead, "strow")
        for header in ["Coverage Type", "Included", "Limit"]:
            stentry = ET.SubElement(strow, "stentry")
            stentry.text = xml_escape_text(header)
        
        stbody = ET.SubElement(simpletable, "stbody")
        coverages = [
            ("Hospitalization", "Yes", "Room rent limit"),
            ("Day Care", "Yes", "As per policy"),
            ("Pre-Hospitalization", "Yes", "30 days"),
            ("Post-Hospitalization", "Yes", "60 days"),
            ("Annual Health Check", "Yes", "Once per year")
        ]
        for cov_type, included, limit in coverages:
            strow = ET.SubElement(stbody, "strow")
            stentry = ET.SubElement(strow, "stentry")
            stentry.text = xml_escape_text(cov_type)
            stentry = ET.SubElement(strow, "stentry")
            stentry.text = xml_escape_text(included)
            stentry = ET.SubElement(strow, "stentry")
            stentry.text = xml_escape_text(limit)
        
        return simpletable
    
    def generate_claim_checklist_table(self) -> ET.Element:
        """Generate claim checklist simpletable."""
        simpletable = ET.Element("simpletable")
        simpletable.set("relcolwidth", xml_escape_attr("1* 1*"))
        
        sthead = ET.SubElement(simpletable, "sthead")
        strow = ET.SubElement(sthead, "strow")
        for header in ["Document", "Status"]:
            stentry = ET.SubElement(strow, "stentry")
            stentry.text = xml_escape_text(header)
        
        stbody = ET.SubElement(simpletable, "stbody")
        documents = [
            "Claim Form",
            "RC Copy",
            "Driving License",
            "FIR Copy",
            "Repair Estimate",
            "Surveyor Report"
        ]
        for doc in documents:
            strow = ET.SubElement(stbody, "strow")
            stentry = ET.SubElement(strow, "stentry")
            stentry.text = xml_escape_text(doc)
            stentry = ET.SubElement(strow, "stentry")
            stentry.text = xml_escape_text(self.rand.choice(["Required", "Received", "Pending"]))
        
        return simpletable
    
    def generate_claim_request_json(self) -> ET.Element:
        """Generate claim request JSON codeblock."""
        codeblock = ET.Element("codeblock")
        codeblock.set("outputclass", xml_escape_attr("json"))
        codeblock.set("xml:space", xml_escape_attr("preserve"))
        
        json_content = """{
  "claimId": "CLM-2024-001234",
  "policyNumber": "POL-2023-567890",
  "claimType": "motor",
  "incidentDate": "2024-01-15T10:30:00Z",
  "incidentLocation": {
    "address": "123 Main Street",
    "city": "Mumbai",
    "state": "Maharashtra",
    "pincode": "400001"
  },
  "claimAmount": 125000,
  "vehicleDetails": {
    "registrationNumber": "MH-01-AB-1234",
    "make": "Maruti",
    "model": "Swift",
    "year": 2022
  },
  "claimDescription": "Rear-end collision resulting in bumper and tailgate damage",
  "claimantDetails": {
    "name": "John Doe",
    "contactNumber": "+91-9876543210",
    "email": "john.doe@example.com"
  }
}"""
        codeblock.text = xml_escape_text(json_content)
        return codeblock
    
    def generate_api_response_json(self) -> ET.Element:
        """Generate API response JSON codeblock."""
        codeblock = ET.Element("codeblock")
        codeblock.set("outputclass", xml_escape_attr("json"))
        codeblock.set("xml:space", xml_escape_attr("preserve"))
        
        json_content = """{
  "status": "success",
  "claimId": "CLM-2024-001234",
  "statusCode": "APPROVED",
  "approvedAmount": 118500,
  "settlementDate": "2024-02-01",
  "paymentMethod": "NEFT",
  "transactionId": "TXN-2024-567890",
  "notes": "Claim approved after surveyor verification. Deductible of ?6,500 applied."
}"""
        codeblock.text = xml_escape_text(json_content)
        return codeblock
    
    def generate_config_json(self) -> ET.Element:
        """Generate config JSON codeblock."""
        codeblock = ET.Element("codeblock")
        codeblock.set("outputclass", xml_escape_attr("json"))
        codeblock.set("xml:space", xml_escape_attr("preserve"))
        
        json_content = """{
  "policyConfiguration": {
    "policyType": "comprehensive",
    "coveragePeriod": "12 months",
    "premiumFrequency": "annual",
    "deductible": {
      "ownDamage": 5000,
      "thirdParty": 0
    },
    "addOns": [
      "zero_depreciation",
      "engine_protection",
      "roadside_assistance"
    ],
    "discounts": {
      "noClaimBonus": 20,
      "voluntaryDeductible": 5
    }
  }
}"""
        codeblock.text = xml_escape_text(json_content)
        return codeblock
    
    def generate_insurance_topic(
        self,
        topic_id: str,
        topic_num: int,
        theme: str
    ) -> bytes:
        """Generate an insurance domain topic."""
        template = self.content_templates[theme]
        
        topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
        
        # Title
        title_elem = ET.SubElement(topic, "title")
        title_elem.text = xml_escape_text(f"{template['title_prefix']} - Topic {topic_num:05d}")
        
        # Short description
        shortdesc = ET.SubElement(topic, "shortdesc")
        shortdesc.text = xml_escape_text(f"{template['overview']}")
        
        # Body
        body = ET.SubElement(topic, "body")
        
        # Overview section
        section = ET.SubElement(body, "section")
        section.set("id", xml_escape_attr(f"overview_{topic_id}"))
        section_title = ET.SubElement(section, "title")
        section_title.text = xml_escape_text("Overview")
        section_p = ET.SubElement(section, "p")
        section_p.text = xml_escape_text(template["overview"])
        
        # Reference Data section with table
        section = ET.SubElement(body, "section")
        section.set("id", xml_escape_attr(f"reference_{topic_id}"))
        section_title = ET.SubElement(section, "title")
        section_title.text = xml_escape_text("Reference Data")
        
        # Rotate between table types
        table_type = topic_num % 3
        if table_type == 0:
            section_p = ET.SubElement(section, "p")
            section_p.text = xml_escape_text("Premium slab structure for different age groups:")
            section.append(self.generate_premium_slab_table())
        elif table_type == 1:
            section_p = ET.SubElement(section, "p")
            section_p.text = xml_escape_text("Coverage matrix showing included benefits:")
            section.append(self.generate_coverage_matrix_table())
        else:
            section_p = ET.SubElement(section, "p")
            section_p.text = xml_escape_text("Claim documentation checklist:")
            section.append(self.generate_claim_checklist_table())
        
        # Sample Payload section with codeblock
        section = ET.SubElement(body, "section")
        section.set("id", xml_escape_attr(f"payload_{topic_id}"))
        section_title = ET.SubElement(section, "title")
        section_title.text = xml_escape_text("Sample Payload")
        
        # Rotate between JSON types
        json_type = topic_num % 3
        if json_type == 0:
            section_p = ET.SubElement(section, "p")
            section_p.text = xml_escape_text("Sample claim request JSON payload:")
            section.append(self.generate_claim_request_json())
        elif json_type == 1:
            section_p = ET.SubElement(section, "p")
            section_p.text = xml_escape_text("Sample API response JSON:")
            section.append(self.generate_api_response_json())
        else:
            section_p = ET.SubElement(section, "p")
            section_p.text = xml_escape_text("Sample policy configuration JSON:")
            section.append(self.generate_config_json())
        
        # Add theme-specific sections
        for section_title_text, section_content in template["sections"]:
            section = ET.SubElement(body, "section")
            section.set("id", xml_escape_attr(f"{section_title_text.lower().replace(' ', '_')}_{topic_id}"))
            section_title = ET.SubElement(section, "title")
            section_title.text = xml_escape_text(section_title_text)
            section_p = ET.SubElement(section, "p")
            section_p.text = xml_escape_text(section_content)
        
        # Generate XML
        ET.indent(topic, space="  ")
        xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{self.config.doctype_topic}\n'
        return doc.encode("utf-8") + xml_body


def generate_insurance_incremental_dataset(
    config,
    base: str,
    max_topics: int = 10000,
    map_sizes: List[int] = None,
    include_local_dtd_stubs: bool = True,
    output_root_folder_name: str = None,
    rand=None,
) -> Dict[str, bytes]:
    """
    Generate insurance incremental maps dataset.
    
    Args:
        config: DatasetConfig object
        base: Base path for files
        max_topics: Maximum number of topics to generate
        map_sizes: List of topicref counts for each map (e.g., [10, 100, 1000, 5000, 10000])
        include_local_dtd_stubs: Whether to generate DTD stub files
        rand: Random number generator
    
    Returns:
        Dictionary mapping file paths to file contents
    """
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    if map_sizes is None:
        map_sizes = [10, 100, 1000, 5000, 10000]
    
    # Validate map_sizes
    if not map_sizes:
        raise ValueError("map_sizes cannot be empty")
    if max(map_sizes) > max_topics:
        raise ValueError(f"max(map_sizes) ({max(map_sizes)}) must be <= max_topics ({max_topics})")
    
    generator = InsuranceContentGenerator(config, rand)
    files = {}
    used_ids = set()
    
    # Use output_root_folder_name if provided, otherwise use base directly
    if output_root_folder_name:
        output_base = safe_join(base, output_root_folder_name)
    else:
        output_base = base
    
    # Generate topics
    topics_dir = safe_join(output_base, "topics")
    topic_paths = []
    
    themes = generator.themes
    
    for i in range(1, max_topics + 1):
        filename = sanitize_filename(f"ins_topic_{i:05d}.dita", config.windows_safe_filenames)
        path = safe_join(topics_dir, filename)
        
        # Use deterministic ID: t_ins_topic_00001, etc. (already DTD-safe, starts with 't')
        topic_id = f"t_ins_topic_{i:05d}"
        # Ensure uniqueness by checking used_ids, but IDs should be deterministic
        if topic_id in used_ids:
            # This shouldn't happen with deterministic IDs, but handle it just in case
            counter = 1
            while topic_id in used_ids:
                topic_id = f"t_ins_topic_{i:05d}_{counter}"
                counter += 1
        used_ids.add(topic_id)
        
        # Rotate themes
        theme = themes[(i - 1) % len(themes)]
        
        topic_xml = generator.generate_insurance_topic(topic_id, i, theme)
        files[path] = topic_xml
        topic_paths.append(path)
    
    # Generate maps with incremental topicref counts
    maps_dir = safe_join(output_base, "maps")
    
    for idx, topicref_count in enumerate(map_sizes):
        # Use deterministic ID: map_ins_10, map_ins_100, etc. (already DTD-safe, starts with 'map')
        map_id = f"map_ins_{topicref_count}"
        # Ensure uniqueness by checking used_ids, but IDs should be deterministic
        if map_id in used_ids:
            # This shouldn't happen with deterministic IDs, but handle it just in case
            counter = 1
            while map_id in used_ids:
                map_id = f"map_ins_{topicref_count}_{counter}"
                counter += 1
        used_ids.add(map_id)
        
        map_filename = sanitize_filename(f"map_ins_{topicref_count}.ditamap", config.windows_safe_filenames)
        map_path = safe_join(maps_dir, map_filename)
        
        # Select topics from pool
        selected_topics = topic_paths[:topicref_count]
        
        map_xml = _map_xml(
            config,
            map_id=map_id,
            title=f"Insurance Incremental Map ({topicref_count} topicrefs)",
            topicref_hrefs=selected_topics,
            keydef_entries=[],
            scoped_blocks=[],
        )
        files[map_path] = map_xml
    
    # Generate DTD stub files if requested
    if include_local_dtd_stubs:
        dtd_dir = safe_join(output_base, "technicalContent", "dtd")
        
        # Topic DTD stub
        topic_dtd_path = safe_join(dtd_dir, "topic.dtd")
        topic_dtd_content = """<!-- Minimal DITA Topic DTD stub -->
<!ENTITY % topic "topic">
<!ELEMENT topic (title, shortdesc?, prolog?, body?, related-links?, topic*)>
<!ATTLIST topic
  id CDATA #REQUIRED
  xml:lang CDATA #IMPLIED>
<!ELEMENT title (#PCDATA)>
<!ELEMENT shortdesc (#PCDATA)>
<!ELEMENT body (section*)>
<!ELEMENT section (title, p*, simpletable?, codeblock?)>
<!ATTLIST section id CDATA #IMPLIED>
<!ELEMENT p (#PCDATA)>
<!ELEMENT simpletable (sthead?, stbody)>
<!ELEMENT sthead (strow)>
<!ELEMENT stbody (strow+)>
<!ELEMENT strow (stentry+)>
<!ELEMENT stentry (#PCDATA)>
<!ELEMENT codeblock (#PCDATA)>
<!ATTLIST codeblock outputclass CDATA #IMPLIED>
"""
        files[topic_dtd_path] = topic_dtd_content.encode('utf-8')
        
        # Map DTD stub
        map_dtd_path = safe_join(dtd_dir, "map.dtd")
        map_dtd_content = """<!-- Minimal DITA Map DTD stub -->
<!ENTITY % map "map">
<!ELEMENT map (title, topicref*)>
<!ATTLIST map
  id CDATA #REQUIRED
  xml:lang CDATA #IMPLIED>
<!ELEMENT title (#PCDATA)>
<!ELEMENT topicref EMPTY>
<!ATTLIST topicref href CDATA #REQUIRED>
"""
        files[map_dtd_path] = map_dtd_content.encode('utf-8')
    
    return files
