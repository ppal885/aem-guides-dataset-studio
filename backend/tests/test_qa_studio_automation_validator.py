"""Automation artifact validation (Behave / framework contract)."""

from __future__ import annotations

from app.services.qa_studio_automation_validator import validate_automation_artifacts, validate_feature_and_steps


def test_rejects_keys_and_actionchains():
    r = validate_automation_artifacts(step_defs_text="from selenium.webdriver.common.keys import Keys\nel.send_keys(Keys.ENTER)")
    assert not r.ok
    assert any("Keys" in e for e in r.errors)
    r2 = validate_automation_artifacts(step_defs_text="ActionChains(driver).move_to_element(el).click().perform()")
    assert not r2.ok


def test_rejects_move_to_element_override():
    r = validate_automation_artifacts(step_defs_text="po.move_to_element(el, override=True)")
    assert not r.ok
    assert any("move_to_element" in e for e in r.errors)


def test_move_to_element_override_ok_with_transient_comment():
    r = validate_automation_artifacts(
        step_defs_text="po.move_to_element(el, override=True)  # transient spectrum menu row",
    )
    assert r.ok


def test_rejects_webdriver_wait():
    r = validate_automation_artifacts(
        step_defs_text="WebDriverWait(driver, 10).until(lambda d: True)\n",
    )
    assert not r.ok
    assert any("WebDriverWait" in e for e in r.errors)


def test_rejects_expected_conditions_ec():
    r = validate_automation_artifacts(step_defs_text="from selenium.webdriver.support import expected_conditions as EC\n")
    assert not r.ok


def test_click_override_requires_comment():
    r = validate_automation_artifacts(step_defs_text="el.click(override=True)")
    assert not r.ok
    ok_line = "el.click(override=True)  # ellipsis overflow menu"
    r2 = validate_automation_artifacts(step_defs_text=ok_line)
    assert r2.ok


def test_rejects_raw_xpath_in_feature_step():
    feature = 'When the user follows "//button[1]"'
    r = validate_feature_and_steps(feature, "")
    assert not r.ok


def test_rejects_raw_xpath_in_step_defs():
    steps = 'el = context.browser.find_element(By.XPATH, "//div[@role=\'dialog\']")\n'
    r = validate_automation_artifacts(step_defs_text=steps)
    assert not r.ok
    assert any("raw_selector_in_behave_step" in e for e in r.errors)


def test_rejects_generic_then():
    r = validate_feature_and_steps("Then it works\n", "")
    assert not r.ok


def test_traceability_with_jira_context_rejects_vague_then():
    r = validate_automation_artifacts(
        feature_text="Then I verify the page works\n",
        jira_summary="X",
        expected_behavior="PDF downloads",
    )
    assert not r.ok


def test_traceability_ok_when_then_aligns_with_expected():
    r = validate_automation_artifacts(
        feature_text="Then the PDF downloads successfully for the map\n",
        jira_summary="X",
        expected_behavior="PDF downloads successfully for the map.",
    )
    assert r.ok


def test_move_to_element_without_override_allowed():
    r = validate_automation_artifacts(step_defs_text="Element.move_to_element(el)\npo.move_to_element(btn)\n")
    assert r.ok


def test_click_override_rejects_flaky_only_comment():
    r = validate_automation_artifacts(step_defs_text="el.click(override=True)  # flaky hover")
    assert not r.ok


def test_rejects_fragile_xpath_literal():
    r = validate_automation_artifacts(
        page_object_text='x = (By.XPATH, "//button[1]")\n',
    )
    assert not r.ok
    assert any("Fragile XPath" in e for e in r.errors)


def test_rejects_invented_page_class_in_steps():
    r = validate_automation_artifacts(step_defs_text="class MyEditorPage:\n    pass\n")
    assert not r.ok
    assert any("Page Object" in e for e in r.errors)


def test_rejects_page_object_call_stub():
    r = validate_automation_artifacts(step_defs_text="page_object_call(context, 'foo')\n")
    assert not r.ok


def test_rejects_silent_is_visible_before_confirm_click():
    steps = """
@when('x')
def step_x(context):
    if dlg.is_visible():
        pass
    confirm_btn.click()
"""
    r = validate_automation_artifacts(step_defs_text=steps)
    assert not r.ok
    assert any("is_visible" in e.lower() for e in r.errors)


def test_given_assert_requires_destructive_precondition_comment():
    bad = '''@given("init")
def step(c):
    assert c.browser is not None
'''
    r = validate_automation_artifacts(step_defs_text=bad)
    assert not r.ok
    ok = '''@given("init")
def step(c):
    # destructive-action precondition
    assert c.dlg.is_visible()
'''
    r2 = validate_automation_artifacts(step_defs_text=ok)
    assert r2.ok


def test_rejects_find_elements_by_xpath_in_steps():
    r = validate_automation_artifacts(
        step_defs_text='driver.find_element_by_xpath("//div[2]")\n',
    )
    assert not r.ok


def test_rejects_asyncio_sleep():
    r = validate_automation_artifacts(step_defs_text="import asyncio\nasyncio.sleep(2)\n")
    assert not r.ok


def test_rejects_generic_then_ui_ok():
    r = validate_feature_and_steps("Then the UI is ok\n", "")
    assert not r.ok
