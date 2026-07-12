"""
Curated large-scale DITA corpus from realtime-friendly domain seeds.

Builds 100k–200k AEM Guides–safe topic files with rich prolog metadata, keywords/tags,
and optional live Stack Exchange question seeds (stackoverflow) plus blockchain and
cloud computing curated pools.
"""

from __future__ import annotations

import json
import logging
import random
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from xml.sax.saxutils import escape as _xml_escape

import httpx

from app.generator.dita_utils import stable_id
from app.generator.generate import safe_join, sanitize_filename
from app.generator.recipe_manifest import RecipeSpec

logger = logging.getLogger(__name__)

_ALLOWED_FETCH_HOSTS = frozenset({"api.stackexchange.com"})

_SOURCE_STACKOVERFLOW = "stackoverflow"
_SOURCE_BLOCKCHAIN = "blockchain"
_SOURCE_CLOUD = "cloud_computing"

_BLOCKCHAIN_SEEDS: List[Tuple[str, List[str]]] = [
    ("Solidity reentrancy guards in smart contracts", ["solidity", "ethereum", "security", "smart-contract"]),
    ("Layer-2 rollups vs sidechains for throughput", ["layer2", "rollup", "blockchain", "scalability"]),
    ("Hyperledger Fabric chaincode endorsement policies", ["hyperledger", "fabric", "chaincode", "enterprise"]),
    ("Wallet key management and HD derivation paths", ["wallet", "bip32", "cryptography", "keys"]),
    ("Consensus finality in proof-of-stake networks", ["pos", "consensus", "finality", "validators"]),
    ("NFT metadata standards on EVM chains", ["nft", "erc721", "metadata", "ipfs"]),
    ("Cross-chain bridge audit checklist", ["bridge", "interop", "security", "audit"]),
    ("Gas optimization patterns for EVM bytecode", ["gas", "evm", "optimization", "bytecode"]),
]

_CLOUD_SEEDS: List[Tuple[str, List[str]]] = [
    ("Kubernetes pod disruption budgets during upgrades", ["kubernetes", "pdb", "availability", "ops"]),
    ("AWS IAM least-privilege for CI/CD pipelines", ["aws", "iam", "cicd", "security"]),
    ("Azure AKS node pool autoscaling trade-offs", ["azure", "aks", "autoscale", "nodes"]),
    ("GCP Cloud Run cold start mitigation", ["gcp", "cloud-run", "latency", "serverless"]),
    ("Terraform remote state locking with S3 and DynamoDB", ["terraform", "state", "aws", "iac"]),
    ("Service mesh mTLS between microservices", ["istio", "mtls", "mesh", "microservices"]),
    ("Observability: RED vs USE metrics for SRE", ["observability", "prometheus", "sre", "metrics"]),
    ("Multi-region active-active database patterns", ["database", "ha", "multi-region", "cloud"]),
]

_STACKOVERFLOW_FALLBACK: List[Tuple[str, List[str]]] = [
    ("DITA conref vs keyref for reusable warnings", ["dita", "conref", "keyref", "reuse"]),
    ("CALS table entry morerows spanning rows", ["dita", "cals-table", "morerows", "aem-guides"]),
    ("DITA-OT preprocess copy-to and resource-only topics", ["dita-ot", "copy-to", "processing-role", "publish"]),
    ("AEM Guides map publish fails but HTML preview works", ["aem-guides", "publish", "troubleshooting", "dita"]),
    ("Keyscope boundaries in branched ditamaps", ["keyscope", "ditamap", "branch", "keys"]),
    ("Markdown format attribute on topicref href", ["markdown", "format", "topicref", "dita"]),
    ("Simpletable vs CALS table in technical content", ["simpletable", "table", "dita", "authoring"]),
]


def _xml_text(value: str) -> str:
    return _xml_escape(value or "", entities={'"': "&quot;", "'": "&apos;"})


def _is_allowed_fetch_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in _ALLOWED_FETCH_HOSTS


def fetch_stackoverflow_seeds(max_items: int = 200) -> List[Tuple[str, List[str]]]:
    """Fetch recent Stack Overflow questions (tagged dita/xml/aem). Falls back to static seeds."""
    if max_items <= 0:
        return list(_STACKOVERFLOW_FALLBACK)

    url = (
        "https://api.stackexchange.com/2.3/questions"
        "?order=desc&sort=activity&tagged=dita;xml;aem&site=stackoverflow&pagesize=100"
    )
    if not _is_allowed_fetch_url(url):
        return list(_STACKOVERFLOW_FALLBACK)

    try:
        with httpx.Client(timeout=15.0, follow_redirects=False) as client:
            response = client.get(url, headers={"User-Agent": "aem-guides-dataset-studio/1.0"})
            response.raise_for_status()
            payload = response.json()
        items: List[Tuple[str, List[str]]] = []
        for row in payload.get("items") or []:
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            tags = [str(t).strip().lower() for t in (row.get("tags") or []) if str(t).strip()]
            if not tags:
                tags = ["stackoverflow", "dita"]
            items.append((title, tags[:12]))
            if len(items) >= max_items:
                break
        if items:
            logger.info("Fetched %s Stack Overflow seeds for curated corpus", len(items))
            return items
    except Exception as exc:
        logger.warning("Stack Overflow seed fetch failed, using fallback corpus: %s", exc)

    return list(_STACKOVERFLOW_FALLBACK)


def _pool_for_source(
    source: str,
    *,
    fetch_live: bool,
    live_seeds: Optional[List[Tuple[str, List[str]]]] = None,
) -> List[Tuple[str, List[str]]]:
    if source == _SOURCE_STACKOVERFLOW:
        return list(live_seeds or (_STACKOVERFLOW_FALLBACK if not fetch_live else fetch_stackoverflow_seeds()))
    if source == _SOURCE_BLOCKCHAIN:
        return list(_BLOCKCHAIN_SEEDS)
    if source == _SOURCE_CLOUD:
        return list(_CLOUD_SEEDS)
    return list(_STACKOVERFLOW_FALLBACK)


def _pick_entry(
    index: int,
    sources: List[str],
    pools: Dict[str, List[Tuple[str, List[str]]]],
    rand: random.Random,
) -> Tuple[str, str, List[str], str]:
    source = sources[index % len(sources)]
    pool = pools.get(source) or _STACKOVERFLOW_FALLBACK
    title, tags = pool[index % len(pool)]
    extra = [
        source.replace("_", "-"),
        "aem-guides",
        "dita-1.3",
        f"batch-{index // 1000:04d}",
    ]
    merged_tags = list(dict.fromkeys([*(t.lower() for t in tags), *extra]))[:14]
    shortdesc = (
        f"Curated {source.replace('_', ' ')} knowledge slice #{index + 1:06d} "
        f"with AEM Guides–safe topic markup and searchable metadata."
    )
    return title, shortdesc, merged_tags, source


def _topic_xml(
    config,
    topic_id: str,
    title: str,
    shortdesc: str,
    tags: List[str],
    source: str,
    body_paragraph: str,
) -> str:
    keyword_xml = "\n".join(f'        <keyword>{_xml_text(tag)}</keyword>' for tag in tags)
    tag_list = "\n".join(f"        <li><ph>{_xml_text(tag)}</ph></li>" for tag in tags[:8])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
{config.doctype_topic}
<topic id="{topic_id}" xml:lang="{getattr(config, 'xml_lang', 'en') or 'en'}">
  <title>{_xml_text(title)}</title>
  <prolog>
    <metadata>
      <keywords>
        <keyword>source:{_xml_text(source)}</keyword>
{keyword_xml}
      </keywords>
    </metadata>
  </prolog>
  <shortdesc>{_xml_text(shortdesc)}</shortdesc>
  <body>
    <p outputclass="curated-summary">{_xml_text(body_paragraph)}</p>
    <section>
      <title>Tags</title>
      <ul>
{tag_list}
      </ul>
    </section>
  </body>
</topic>"""


def build_recipe_example_xml() -> str:
    """Representative Builder sample: real generator markup (2 topics + sample map)."""

    class _ExampleCfg:
        doctype_topic = '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">'
        doctype_map = '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">'
        xml_lang = "en"

    cfg = _ExampleCfg()

    so_title, so_tags = _STACKOVERFLOW_FALLBACK[0]
    so_shortdesc = (
        "Curated stackoverflow knowledge slice #000001 with AEM Guides-safe topic markup and searchable metadata."
    )
    so_body = (
        "This curated topic synthesizes stackoverflow patterns for AEM Guides training. "
        "It includes DITA 1.3 topic structure, prolog keywords, and outputclass metadata for retrieval."
    )
    so_tags_full = list(dict.fromkeys([*(t.lower() for t in so_tags), "stackoverflow", "aem-guides", "dita-1.3", "batch-0000"]))
    topic_so = _topic_xml(
        cfg,
        "curated-topic-example-so",
        so_title,
        so_shortdesc,
        so_tags_full,
        _SOURCE_STACKOVERFLOW,
        so_body,
    )

    bc_title, bc_tags = _BLOCKCHAIN_SEEDS[1]
    bc_shortdesc = (
        "Curated blockchain knowledge slice #000002 with AEM Guides-safe topic markup and searchable metadata."
    )
    bc_body = (
        "This curated topic synthesizes blockchain patterns for AEM Guides training. "
        "It includes DITA 1.3 topic structure, prolog keywords, and outputclass metadata for retrieval."
    )
    bc_tags_full = list(dict.fromkeys([*(t.lower() for t in bc_tags), "blockchain", "aem-guides", "dita-1.3", "batch-0000"]))
    topic_bc = _topic_xml(
        cfg,
        "curated-topic-example-bc",
        bc_title,
        bc_shortdesc,
        bc_tags_full,
        _SOURCE_BLOCKCHAIN,
        bc_body,
    )

    map_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
{cfg.doctype_map}
<map id="curated-root-map">
  <title>Curated realtime corpus (sample 2 of N)</title>
  <topicmeta>
    <keywords>
      <keyword>curated</keyword>
      <keyword>aem-guides</keyword>
      <keyword>dita</keyword>
    </keywords>
  </topicmeta>
  <topicref href="../topics/curated/curated_00000001.dita" format="dita"/>
  <topicref href="../topics/curated/curated_00000002.dita" format="dita"/>
</map>"""

    return f"""<!-- File: topics/curated/curated_00000001.dita (stackoverflow seed) -->
{topic_so}

<!-- File: topics/curated/curated_00000002.dita (blockchain seed) -->
{topic_bc}

<!-- File: maps/curated_root_sample.ditamap (first map_sample_size topicrefs) -->
{map_xml}

<!-- File: curated_corpus_manifest.json -->
{{
  "topic_count": 100000,
  "data_sources": ["stackoverflow", "blockchain", "cloud_computing"],
  "fetch_live": true,
  "map_sample_size": 2000
}}"""


def generate_curated_realtime_corpus(  # noqa: PLR0913
    config,
    base: str,
    *,
    topic_count: int = 100_000,
    data_sources: Optional[List[str]] = None,
    batch_size: int = 1000,
    fetch_live: bool = True,
    map_sample_size: int = 2000,
    content_subject: str = "",
    stream_callback: Optional[Callable[[Dict[str, bytes]], None]] = None,
    rand: Optional[random.Random] = None,
) -> Tuple[Dict[str, bytes], Dict]:
    if rand is None:
        rand = random.Random(config.seed)

    sources = [s for s in (data_sources or []) if s] or [
        _SOURCE_STACKOVERFLOW,
        _SOURCE_BLOCKCHAIN,
        _SOURCE_CLOUD,
    ]
    count = max(1, min(int(topic_count), 200_000))
    batch = max(100, min(int(batch_size), 10_000))
    subject = (content_subject or "").strip()

    live_stack = fetch_stackoverflow_seeds() if fetch_live and _SOURCE_STACKOVERFLOW in sources else None
    pools = {
        source: _pool_for_source(source, fetch_live=fetch_live, live_seeds=live_stack if source == _SOURCE_STACKOVERFLOW else None)
        for source in sources
    }

    files: Dict[str, bytes] = {} if stream_callback is None else {}
    used_ids: set[str] = set()
    topic_paths: List[str] = []
    topic_dir = safe_join(base, "topics", "curated")

    for batch_start in range(0, count, batch):
        batch_end = min(batch_start + batch, count)
        batch_files: Dict[str, bytes] = {}

        for i in range(batch_start + 1, batch_end + 1):
            filename = sanitize_filename(f"curated_{i:08d}.dita", config.windows_safe_filenames)
            path = safe_join(topic_dir, filename)
            topic_id = stable_id(config.seed, "curated-topic", str(i), used_ids)

            title, shortdesc, tags, source = _pick_entry(i - 1, sources, pools, rand)
            if subject:
                title = f"{subject}: {title}"
                shortdesc = f"{shortdesc} Domain focus: {subject}."

            body = (
                f"This curated topic synthesizes {source.replace('_', ' ')} patterns for AEM Guides training. "
                f"It includes DITA 1.3 topic structure, prolog keywords, and outputclass metadata for retrieval."
            )
            xml = _topic_xml(config, topic_id, title, shortdesc, tags, source, body)
            payload = xml.encode("utf-8")

            if stream_callback:
                batch_files[path] = payload
            else:
                files[path] = payload

            if len(topic_paths) < max(0, int(map_sample_size)):
                topic_paths.append(f"../topics/curated/{filename}")

        if stream_callback and batch_files:
            stream_callback(batch_files)

        if batch_start and batch_start % (batch * 10) == 0:
            logger.info("Curated corpus progress: %s/%s topics", batch_start, count)

    out_files = files if stream_callback is None else {}
    if topic_paths:
        refs = "\n".join(f'  <topicref href="{href}" format="dita"/>' for href in topic_paths)
        map_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
{config.doctype_map}
<map id="curated-root-map">
  <title>Curated realtime corpus (sample {len(topic_paths)} of {count})</title>
  <topicmeta>
    <keywords>
      <keyword>curated</keyword>
      <keyword>aem-guides</keyword>
      <keyword>dita</keyword>
    </keywords>
  </topicmeta>
{refs}
</map>"""
        map_path = safe_join(base, "maps", "curated_root_sample.ditamap")
        map_bytes = map_xml.encode("utf-8")
        if stream_callback:
            stream_callback({map_path: map_bytes})
        else:
            out_files[map_path] = map_bytes

    manifest = {
        "topic_count": count,
        "data_sources": sources,
        "fetch_live": fetch_live,
        "map_sample_size": len(topic_paths),
        "subject": subject,
    }
    manifest_path = safe_join(base, "curated_corpus_manifest.json")
    manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
    if stream_callback:
        stream_callback({manifest_path: manifest_bytes})
    else:
        out_files[manifest_path] = manifest_bytes

    return out_files, manifest


RECIPE_SPECS = [
    RecipeSpec(
        id="curated_realtime_corpus",
        mechanism_family="scale",
        title="Curated realtime corpus (1–2 lakh topics)",
        description=(
            "Generate 100k–200k well-curated DITA topics seeded from Stack Overflow (live when available), "
            "blockchain, and cloud computing domains. Each topic includes AEM Guides–safe DTD, prolog keywords, "
            "rich tags, and a sample root map."
        ),
        tags=[
            "curated",
            "large scale",
            "stackoverflow",
            "blockchain",
            "cloud computing",
            "aem guides",
            "dita",
            "100k",
            "200k",
        ],
        module="app.generator.curated_realtime_corpus",
        function="generate_curated_realtime_corpus",
        params_schema={
            "topic_count": "int",
            "data_sources": "list",
            "batch_size": "int",
            "fetch_live": "bool",
            "map_sample_size": "int",
            "content_subject": "str",
        },
        default_params={
            "topic_count": 100_000,
            "data_sources": [_SOURCE_STACKOVERFLOW, _SOURCE_BLOCKCHAIN, _SOURCE_CLOUD],
            "batch_size": 1000,
            "fetch_live": True,
            "map_sample_size": 2000,
            "content_subject": "",
        },
        stability="stable",
        constructs=["topic", "prolog", "keywords", "map", "metadata"],
        scenario_types=["LARGE_SCALE", "TRAINING_CORPUS"],
        use_when=[
            "need 1 lakh or 2 lakh curated training topics",
            "stackoverflow blockchain or cloud computing themed corpora",
            "AEM Guides DTD-safe bulk datasets with rich tags",
        ],
        avoid_when=["small hand-authored samples under 1000 topics"],
        positive_negative="positive",
        complexity="high",
        output_scale="xlarge",
        topic_type="topic",
        intent_tags=["curated", "realtime", "stackoverflow", "scale"],
        trigger_phrases=[
            "1 lakh topics",
            "2 lakh topics",
            "100000 curated",
            "stackoverflow dataset",
            "blockchain dita corpus",
        ],
        example_output=build_recipe_example_xml(),
        retrieval_keywords=["curated_realtime_corpus", "large scale", "stackoverflow", "blockchain", "cloud"],
    ),
]
