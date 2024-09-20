import re
import csv
import sys
import time
import logging
import argparse
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from contact_identifiers import CONTACT_PATTERN


def setup_logging():
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.StreamHandler()])
    return logging.getLogger(__name__)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Check for email domains in website HTML and contact pages using Selenium.")
    parser.add_argument("-i", "--input_file", required=True,
                        help="Path to the input CSV file")
    parser.add_argument("-o", "--output_file",
                        default="domains_on_sites.csv", help="Path to the output CSV file")
    parser.add_argument("-c", "--chromedriver",
                        default="/opt/homebrew/bin/chromedriver",
                        help="Path to the ChromeDriver executable")
    return parser.parse_args()


def setup_webdriver(chromedriver_path):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    prefs = {
        # 2 means 'block'. Set to prevent redirection to English site.
        "profile.default_content_setting_values.geolocation": 2,
        "intl.accept_languages": ""
    }
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)")
    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


def read_csv(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                yield row
    except IOError as e:
        logger.error(f"Error reading CSV file: {e}")
        sys.exit(1)


def normalize_url(url):
    parsed = urlparse(url)
    if not parsed.scheme:
        return f"https://{url}"
    return url


def try_url(driver, url):
    try:
        logger.info(f"Attempting to access URL: {url}")
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body")))
        return True
    except (TimeoutException, WebDriverException, InvalidArgumentException):
        logger.warning(f"Failed to access URL: {url}")
        return False


def fetch_html_content(driver, url):
    url = normalize_url(url)
    try:
        driver.delete_all_cookies()
        driver.execute_cdp_cmd('Network.enable', {})
        driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {"headers": {}})
        if try_url(driver, url):
            final_url = driver.current_url
            logger.info(f"Successfully accessed URL. Final URL: {final_url}")
            return driver.page_source, final_url
        if url.startswith("https://"):
            http_url = "http://" + url[8:]
            if try_url(driver, http_url):
                final_url = driver.current_url
                logger.info(f"Successfully accessed URL via HTTP. Final URL: {final_url}")
                return driver.page_source, final_url
        logger.error(f"Failed to access URL via both HTTPS and HTTP: {url}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error fetching HTML content from {url}: {e}")
        return None, None


def check_email_domain(html_content, domain):
    if html_content is None:
        return False
    pattern = r'@' + re.escape(domain)
    return bool(re.search(pattern, html_content))


def identify_contact_pages(links):
    potential_contact_links = []
    for link in links:
        if CONTACT_PATTERN.search(link):
            potential_contact_links.append(link)
    return list(set(potential_contact_links))


def extract_links(html_content, base_url):
    soup = BeautifulSoup(html_content, 'html.parser')
    links = []
    for a_tag in soup.find_all('a', href=True):
        link = urljoin(base_url, a_tag['href'])
        links.append(link)
    return links


def process_row(driver, row):
    logger.info(f"Processing: {row['ror_id']}")
    html_content, final_url = fetch_html_content(
        driver, row['extracted_domain'])
    if html_content:
        logger.info(f"Successfully fetched HTML content for {row['ror_id']}")
        email_found = check_email_domain(html_content, row['extracted_domain'])
        if email_found:
            logger.info(f"Email domain found on main page for {row['ror_id']}")
            row['email_found'] = True
        else:
            logger.info(f"Email domain not found on main page for {row['ror_id']}, checking contact pages")
            links = extract_links(html_content, final_url)
            contact_pages = identify_contact_pages(links)
            for contact_page in contact_pages:
                contact_html, _ = fetch_html_content(driver, contact_page)
                if contact_html and check_email_domain(contact_html, row['extracted_domain']):
                    logger.info(f"Email domain found on contact page for {row['ror_id']}")
                    row['email_found'] = True
                    break
            else:
                logger.info(f"Email domain not found on any page for {row['ror_id']}")
                row['email_found'] = False
    else:
        logger.warning(f"Failed to fetch HTML content for {row['ror_id']}")
        row['email_found'] = False

    logger.info(f"Finished processing {row['ror_id']}")
    return row


def write_csv_header(file_path, fieldnames):
    try:
        with open(file_path, 'w', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
    except IOError as e:
        logger.error(f"Error writing CSV header: {e}")
        sys.exit(1)


def append_to_csv(file_path, row):
    try:
        with open(file_path, 'a', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=row.keys())
            writer.writerow(row)
    except IOError as e:
        logger.error(f"Error appending to CSV file: {e}")


def main():
    args = parse_arguments()
    driver = setup_webdriver(args.chromedriver)
    try:
        first_row = next(read_csv(args.input_file))
        fieldnames = list(first_row.keys()) + ['email_found']
        write_csv_header(args.output_file, fieldnames)
        for row in [first_row] + list(read_csv(args.input_file)):
            processed_row = process_row(driver, row)
            append_to_csv(args.output_file, processed_row)
            time.sleep(1)
        logger.info("Processing complete. Results written to output file.")
    finally:
        driver.quit()


if __name__ == "__main__":
    logger = setup_logging()
    main()
