"""E2E smoke coverage for localization and local picker UI."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_language_switch_updates_ui_and_batch_picker_controls(app_page: Page):
    language_select = app_page.locator("#language-select")
    expect(language_select).to_be_visible()

    language_select.select_option("zh-CN")
    expect(app_page.locator("#mode-quick")).to_have_text("快速模式")
    expect(app_page.locator("#video-browse-btn")).to_be_visible()

    app_page.locator("#btn-batch-render").click()
    expect(app_page.locator("#batch-modal-title")).to_have_text("批量渲染")
    expect(app_page.locator("#batch-select-video-dir")).to_be_visible()
    expect(app_page.locator("#batch-select-shared-gps")).to_be_visible()

    app_page.locator("#batch-modal-close").click()
    language_select.select_option("en")
    expect(app_page.locator("#mode-quick")).to_have_text("Quick Mode")
