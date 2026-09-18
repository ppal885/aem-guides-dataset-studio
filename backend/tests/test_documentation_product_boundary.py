"""Retrieved Experience League rows must keep their real product-contract owner.

The crawled Experience League corpus covers every Adobe product published on
the host, so filtering retrieval by host suffix alone admits Workfront,
Journey Optimizer and AEM platform pages and then labels all of them as AEM
Guides product documentation.  These tests pin the product boundary.
"""

from app.services.guides_test_plan_generator_service import (
    DOC_PRODUCT_AEM_GUIDES,
    DOC_PRODUCT_AEM_PLATFORM,
    DOC_PRODUCT_UNRELATED,
    _documentation_product_path,
    _is_aem_guides_documentation,
    _split_documentation_by_product,
)

_EL = "https://experienceleague.adobe.com/en/docs/"
GUIDES_URL = _EL + "experience-manager-guides/using/user-guide/reports-intro"
ASSETS_URL = _EL + "experience-manager-cloud-service/content/assets/manage/download-assets"
WORKFRONT_URL = _EL + "workfront/using/manage-work/projects/project-basics"


def _row(url: str, **extra) -> dict:
    return {"canonical_url": url, "source_url": url, "snippet": "x", **extra}


def test_guides_tree_is_the_only_guides_product_contract():
    assert _documentation_product_path(_row(GUIDES_URL)) == DOC_PRODUCT_AEM_GUIDES
    assert _is_aem_guides_documentation(_row(GUIDES_URL))


def test_aem_platform_pages_are_not_guides_product_contract():
    assert _documentation_product_path(_row(ASSETS_URL)) == DOC_PRODUCT_AEM_PLATFORM
    assert not _is_aem_guides_documentation(_row(ASSETS_URL))
    assert (
        _documentation_product_path(_row(_EL + "dynamic-media/spin-sets"))
        == DOC_PRODUCT_AEM_PLATFORM
    )


def test_unrelated_adobe_products_establish_nothing_about_guides():
    assert _documentation_product_path(_row(WORKFRONT_URL)) == DOC_PRODUCT_UNRELATED
    assert (
        _documentation_product_path(_row(_EL + "journey-optimizer/using/get-started"))
        == DOC_PRODUCT_UNRELATED
    )


def test_split_routes_each_row_to_its_own_contract_lane():
    guides, platform, unrelated = _split_documentation_by_product(
        [_row(GUIDES_URL), _row(ASSETS_URL), _row(WORKFRONT_URL)]
    )

    assert [row["canonical_url"] for row in guides] == [GUIDES_URL]
    assert [row["canonical_url"] for row in platform] == [ASSETS_URL]
    assert [row["canonical_url"] for row in unrelated] == [WORKFRONT_URL]
    assert platform[0]["product_contract"] == "AEM_ASSETS_PLATFORM_CONTRACT"
    assert unrelated[0]["product_contract"] == DOC_PRODUCT_UNRELATED


def test_retrieval_errors_and_unknown_rows_are_never_silently_dropped():
    guides, platform, unrelated = _split_documentation_by_product(
        [{"error": "chroma unavailable"}, _row("")]
    )

    assert len(guides) == 2
    assert platform == []
    assert unrelated == []
