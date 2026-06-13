"""WebDriver management module for browser automation."""

import logging
import sys

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.chrome.service import Service

from ..config import Config

logger = logging.getLogger(__name__)


class WebDriverManager:
    """Manages WebDriver creation and configuration."""

    @staticmethod
    def create_driver() -> WebDriver:
        """Create and configure a WebDriver instance based on arguments and configuration."""
        # Build options (headless or not) and force local binary paths
        if WebDriverManager._is_headless_mode():
            logger.info('Running in headless mode')
            options = WebDriverManager._get_headless_options()
        else:
            options = WebDriverManager._get_default_options()

        # Prefer explicit CHROMEDRIVER_PATH when provided, otherwise use system path
        driver_path = Config.CHROMEDRIVER_PATH or '/usr/bin/chromedriver'
        logger.info('Using chromedriver executable: %s', driver_path)
        service = Service(executable_path=driver_path)

        return webdriver.Chrome(service=service, options=options)

    @staticmethod
    def _is_headless_mode() -> bool:
        """Check if the script should run in headless mode."""
        return len(sys.argv) > 1 and '--headless' in sys.argv

    @staticmethod
    def _get_headless_options() -> Options:
        """Configure Chrome options for headless browser operation."""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")  # CRUCIAL: Prevents shared memory saturation in Docker
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-application-cache")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-software-rasterizer")  # Optimize for low-memory systems
        chrome_options.add_argument("--disable-setuid-sandbox")
        chrome_options.add_argument("--single-process")  # Optional but useful on small architectures (ARM64)

        # Force use of local Chromium binary on systems where Selenium Manager fails
        chrome_options.binary_location = '/usr/bin/chromium-browser'

        return chrome_options

    @staticmethod
    def _get_default_options() -> Options:
        """Configure Chrome options for non-headless browser operation."""
        options = Options()
        # Optimize for low-memory systems (Docker/ARM64)
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")  # CRUCIAL: Prevents shared memory saturation in Docker
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")  # Optimize for low-memory systems
        options.add_argument("--single-process")  # Optional but useful on small architectures (ARM64)
        # Force use of local Chromium binary
        options.binary_location = '/usr/bin/chromium-browser'
        return options
