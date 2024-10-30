import re
import csv
import sys
import time
import logging
import argparse
import requests
from bs4 import BeautifulSoup
from furl import furl
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from requests.exceptions import RequestException
from contact_identifiers import CONTACT_PATTERN


def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.StreamHandler()])
    return logging.getLogger(__name__)


logger = setup_logging()


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Check for email domains in website HTML and contact pages.")
    parser.add_argument("-i", "--input", required=True,
                        help="Input CSV file path")
    parser.add_argument(
        "-o", "--output", default="domains_on_sites.csv", help="Output CSV file path")
    parser.add_argument("-d", "--id", default="ror_id", help="ID field name")
    parser.add_argument("-w", "--website", default="website",
                        help="Website field name")
    parser.add_argument("-f", "--field", default="domains",
                        help="Domains field name")
    parser.add_argument("-s", "--sep", default=None, help="Domain separator")
    parser.add_argument("-t", "--timeout", type=int,
                        default=10, help="Resolution timeout")
    parser.add_argument("-r", "--redirects", type=int,
                        default=5, help="Max redirects")
    parser.add_argument("-v", "--verify", type=bool,
                        default=True, help="Verify SSL")
    return parser.parse_args()


def setup_webdriver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    prefs = {"profile.default_content_setting_values.geolocation": 2,
             "intl.accept_languages": ""}
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)")
    service = Service('/opt/homebrew/bin/chromedriver')
    return webdriver.Chrome(service=service, options=chrome_options)


def normalize_domain(domain):
    domain = domain.lower().strip().rstrip('/')
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain


def clean_url(url):
    try:
        f = furl(url)
        if len(f.path.segments) > 0 and len(f.path.segments[0]) == 2:
            f.path.segments.pop(0)
        if f.path.segments and f.path.segments[-1] in ['index.html', 'index.php', 'index.htm']:
            f.path.segments.pop()
        f.query = ''
        f.fragment = ''
        return f.url.rstrip('/')
    except Exception as e:
        logger.warning(f"Error cleaning URL {url}: {e}")
        return url.rstrip('/')


def is_url_different(url1, url2):
    norm_url1 = clean_url(url1).rstrip('/').lower()
    norm_url2 = clean_url(url2).rstrip('/').lower()
    return norm_url1 != norm_url2


def construct_url_variations(domain, url):
    return [f"https://www.{domain}", f"https://{domain}", url, f"http://{domain}", f"http://www.{domain}"]


def resolve_domain(domain, url, timeout=10, max_redirects=5, verify_ssl=True):
    session = requests.Session()
    urls_to_try = construct_url_variations(domain, url)
    for url in urls_to_try:
        try:
            response = session.get(url, timeout=timeout, allow_redirects=True, verify=verify_ssl,
                                   headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            if response.status_code == 200:
                return {'success': True, 'url': clean_url(response.url), 'status_code': response.status_code,
                        'was_redirected': len(response.history) > 0, 'original_url': url}
        except RequestException as e:
            logger.warning(f"Failed to resolve {url}: {e}")
            continue
    return {'success': False, 'url': None, 'status_code': None, 'was_redirected': False, 'original_url': None}


def check_email_domain(html_content, domain):
    if html_content is None:
        return False
    pattern = r'@' + re.escape(normalize_domain(domain))
    return bool(re.search(pattern, html_content))


def identify_contact_pages(links):
    return list(set([link for link in links if CONTACT_PATTERN.search(str(link))]))


def extract_links(html_content, base_url):
    soup = BeautifulSoup(html_content, 'html.parser')
    links = []
    for a_tag in soup.find_all('a', href=True):
        try:
            link = urljoin(base_url, a_tag['href'])
            if link.startswith(('http://', 'https://')):
                links.append(link)
        except Exception as e:
            logger.warning(f"Error processing link: {e}")
    return links


def fetch_html_content(driver, url, timeout=10):
    try:
        driver.delete_all_cookies()
        driver.execute_cdp_cmd('Network.enable', {})
        driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {"headers": {}})
        driver.get(url)
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body")))
        return {'success': True, 'content': driver.page_source, 'final_url': driver.current_url}
    except (TimeoutException, WebDriverException) as e:
        logger.warning(f"Failed to access URL {url}: {e}")
        return {'success': False, 'content': None, 'final_url': None}
    except Exception as e:
        logger.error(f"Unexpected error fetching content from {url}: {e}")
        return {'success': False, 'content': None, 'final_url': None}


def process_row(driver, row, args):
    logger.info(f"Processing: {row.get(args.id, 'unknown')}")
    website = row.get(args.website, "").strip()
    if not website:
        return create_error_result(row)
    domains = row.get(args.field, "").strip()
    if not domains:
        return create_error_result(row)
    domains = domains.split(args.sep) if args.sep and args.sep in domains else [domains]
    domains = [d.strip() for d in domains if d.strip()]
    for domain in domains:
        if not domain:
            continue
        resolution_result = resolve_domain(domain, website, timeout=args.timeout,
                                           max_redirects=args.redirects, verify_ssl=args.verify)
        result = {**row}
        result.update({'resolved_domain': domain, 'resolved_url': resolution_result['url'],
                       'resolution_method': resolution_result['original_url'],
                       'was_redirected': resolution_result['was_redirected'],
                       'status_code': resolution_result['status_code'],
                       'email_found': False, 'contact_page_checked': False})
        if resolution_result['success']:
            html_result = fetch_html_content(driver, resolution_result['url'])
            if html_result['success']:
                content = html_result['content']
                final_url = html_result['final_url']
                if check_email_domain(content, domain):
                    result['email_found'] = True
                    logger.info(f"Email domain found on main page for {row.get(args.id, 'unknown')}")
                else:
                    logger.info(f"Checking contact pages for {row.get(args.id, 'unknown')}")
                    links = extract_links(content, final_url)
                    contact_pages = identify_contact_pages(links)
                    result['contact_page_checked'] = bool(contact_pages)
                    for contact_page in contact_pages:
                        contact_result = fetch_html_content(
                            driver, contact_page)
                        if contact_result['success'] and check_email_domain(contact_result['content'], domain):
                            result['email_found'] = True
                            logger.info(f"Email domain found on contact page for {row.get(args.id, 'unknown')}")
                            break
                    if not result['email_found']:
                        logger.info(f"Email domain not found for {row.get(args.id, 'unknown')}")
        return result


def create_error_result(row):
    result = {**row}
    result.update({'resolved_domain': None, 'resolved_url': None, 'resolution_method': None,
                   'was_redirected': False, 'status_code': None, 'email_found': False,
                   'contact_page_checked': False})
    return result


def write_csv_header(file_path, fieldnames):
    try:
        with open(file_path, 'w', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
    except IOError as e:
        logger.error(f"Error writing CSV header: {e}")
        sys.exit(1)


def append_to_csv(file_path, row, fieldnames):
    try:
        with open(file_path, 'a', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writerow(row)
    except IOError as e:
        logger.error(f"Error appending to CSV file: {e}")


def process_input_file(args, driver):
    try:
        with open(args.input, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            input_fieldnames = reader.fieldnames
            required_fields = [args.id, args.website, args.field]
            missing_fields = [
                field for field in required_fields if field not in input_fieldnames]
            if missing_fields:
                logger.error(f"Missing required fields in CSV: {', '.join(missing_fields)}")
                return
            if not input_fieldnames:
                logger.error("Input file has no headers")
                return
            output_fieldnames = input_fieldnames + \
                ['resolved_domain', 'resolved_url', 'resolution_method',
                    'was_redirected', 'status_code', 'email_found', 'contact_page_checked']
            write_csv_header(args.output, output_fieldnames)
            for row in reader:
                try:
                    result = process_row(driver, row, args)
                    append_to_csv(args.output, result, output_fieldnames)
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"Error processing row {row.get(args.id, 'unknown')}: {e}")
                    error_result = create_error_result(row)
                    append_to_csv(args.output, error_result, output_fieldnames)
                    continue
    except Exception as e:
        logger.error(f"Fatal error processing input file: {e}")
        raise


def cleanup(driver):
    try:
        driver.quit()
        logger.info("Webdriver successfully closed")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")


def main():
    args = parse_arguments()
    logger.info("Starting domain resolution and checking process")
    driver = None
    try:
        driver = setup_webdriver()
        process_input_file(args, driver)
        logger.info("Processing completed successfully")
    except Exception as e:
        logger.error(f"Fatal error during execution: {e}")
        sys.exit(1)
    finally:
        if driver:
            cleanup(driver)


if __name__ == "__main__":
    main()
