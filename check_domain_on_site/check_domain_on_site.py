import os
import re
import csv
import json
import time
import asyncio
import argparse
import logging
import aiocsv
import aiohttp
import aiofiles
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
from concurrent.futures import ProcessPoolExecutor
from contact_identifiers import CONTACT_PATTERN
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ASYNC_CONFIG = {
    'max_concurrent_tasks': 200,
    'queue_size': 500,
    'selenium_workers': 2,
    'selenium_timeout': 15,
    'http_timeout': 10,
    'max_redirects': 5,
    'requests_per_minute': 15,
    'result_buffer_size': 100,
    'js_render_threshold_kb': 2,
}


ROBOTS_CACHE = {}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

selenium_driver = None


def init_selenium_worker():
    global selenium_driver
    if selenium_driver is None:
        logger.info(f"[PID {os.getpid()}] Initializing Selenium WebDriver...")
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--blink-settings=imagesEnabled=false")
            prefs = {
                "profile.managed_default_content_settings.images": 2,
                "profile.default_content_setting_values.media_stream_mic": 2,
                "profile.default_content_setting_values.media_stream_camera": 2,
            }
            chrome_options.add_experimental_option("prefs", prefs)
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument(
                "user-agent=Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
            )

            service = Service()
            selenium_driver = webdriver.Chrome(
                service=service, options=chrome_options)
            logger.info(f"[PID {os.getpid()}] Selenium WebDriver initialized.")
        except Exception as e:
            logger.error(f"[PID {os.getpid()}] Failed to initialize WebDriver: {e}")
            selenium_driver = None


def shutdown_selenium_worker():
    global selenium_driver
    if selenium_driver:
        logger.info(f"[PID {os.getpid()}] Shutting down Selenium WebDriver.")
        selenium_driver.quit()


def fetch_with_selenium(url):
    global selenium_driver
    if not selenium_driver:
        logger.error(f"[PID {os.getpid()}] Selenium not available to fetch {url}")
        return None, None
    try:
        selenium_driver.get(url)
        WebDriverWait(selenium_driver, ASYNC_CONFIG['selenium_timeout']).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        return selenium_driver.page_source, selenium_driver.current_url
    except Exception as e:
        logger.warning(f"[PID {os.getpid()}] Selenium failed to fetch {url}: {e}")
        return None, None


class AsyncDomainRateLimiter:
    """
    An asyncio-compatible rate limiter to control request frequency per domain.
    """

    def __init__(self, requests_per_minute):
        self.requests_per_minute = requests_per_minute
        self.interval = 60.0 / requests_per_minute
        self._locks = {}
        self._last_request_times = {}
        self._global_lock = asyncio.Lock()

    @staticmethod
    def get_domain_from_url(url):
        try:
            return urlparse(url).netloc.lower().replace('www.', '')
        except Exception:
            return url.lower()

    async def wait(self, url):
        """Ensures that requests to a domain respect the defined rate limit."""
        domain = self.get_domain_from_url(url)
        async with self._global_lock:
            if domain not in self._locks:
                self._locks[domain] = asyncio.Lock()

        async with self._locks[domain]:
            current_time = time.monotonic()
            last_time = self._last_request_times.get(domain, 0)
            elapsed = current_time - last_time

            if elapsed < self.interval:
                sleep_time = self.interval - elapsed
                await asyncio.sleep(sleep_time)

            self._last_request_times[domain] = time.monotonic()


class AsyncFetcher:
    def __init__(self, session, rate_limiter, selenium_pool):
        self.session = session
        self.rate_limiter = rate_limiter
        self.selenium_pool = selenium_pool

    async def fetch_html(self, url):
        await self.rate_limiter.wait(url)
        try:
            async with self.session.get(
                url,
                timeout=ASYNC_CONFIG['http_timeout'],
                allow_redirects=True,
                max_redirects=ASYNC_CONFIG['max_redirects'],
                ssl=False
            ) as response:
                response.raise_for_status()
                content = await response.text()
                final_url = str(response.url)

                if len(content.encode('utf-8')) / 1024 < ASYNC_CONFIG['js_render_threshold_kb']:
                    if 'javascript' in content.lower() or '<noscript>' in content.lower():
                        logger.info(f"Possible JS-required site {url}. Falling back to Selenium.")
                        return await self.fetch_html_with_selenium(url)

                return {'success': True, 'content': content, 'final_url': final_url}

        except Exception as e:
            logger.warning(f"aiohttp fetch failed for {url}: {type(e).__name__}. Trying Selenium as a last resort.")
            return await self.fetch_html_with_selenium(url)

    async def fetch_html_with_selenium(self, url):
        await self.rate_limiter.wait(url)
        loop = asyncio.get_running_loop()
        try:
            page_source, final_url = await loop.run_in_executor(
                self.selenium_pool, fetch_with_selenium, url
            )
            if page_source and final_url:
                return {'success': True, 'content': page_source, 'final_url': final_url}
            else:
                return {'success': False, 'content': None, 'final_url': None}
        except Exception as e:
            logger.error(f"Error in Selenium execution for {url}: {e}")
            return {'success': False, 'content': None, 'final_url': None}


def _normalize_domain(domain):
    return domain.lower().strip().rstrip('/').replace('www.', '')


def _construct_url_variations(domain):
    return [
        f"https://{domain}",
        f"https://www.{domain}",
        f"http://{domain}",
        f"http://www.{domain}"
    ]


def _check_email_domain(html_content, domain):
    if not html_content:
        return False
    pattern = r'@' + re.escape(_normalize_domain(domain)) + r'\b'
    return bool(re.search(pattern, html_content, re.IGNORECASE))


def _extract_and_score_contact_links(html_content, base_url):
    soup = BeautifulSoup(html_content, 'html.parser')
    scored_links = {}
    for a_tag in soup.find_all('a', href=True):
        try:
            link_url = urljoin(base_url, a_tag['href'])
            if not link_url.startswith(('http://', 'https://')):
                continue

            link_text = a_tag.get_text(strip=True)
            link_path = urlparse(link_url).path

            score = 0
            if CONTACT_PATTERN.search(link_text):
                score += 3
            if CONTACT_PATTERN.search(link_path):
                score += 2
            if CONTACT_PATTERN.search(a_tag.get('title', '')):
                score += 1

            if score > 0:
                scored_links[link_url] = max(
                    score, scored_links.get(link_url, 0))

        except Exception:
            continue

    return sorted(scored_links.items(), key=lambda item: item[1], reverse=True)


async def check_robots_txt(session, url):
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    if domain in ROBOTS_CACHE:
        return ROBOTS_CACHE[domain].can_fetch("*", url)

    robots_url = f"{parsed_url.scheme}://{domain}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        async with session.get(robots_url, timeout=ASYNC_CONFIG['http_timeout']) as response:
            if response.status == 200:
                content = await response.text()
                rp.parse(content.splitlines())
            else:
                rp.allow_all = True
    except Exception:
        rp.allow_all = True

    ROBOTS_CACHE[domain] = rp
    return rp.can_fetch("*", url)


async def process_row(row, args, fetcher):
    website = row.get(args.website, "").strip()
    domains_str = row.get(args.field, "").strip()

    if not website or not domains_str:
        return {**row, 'reason': 'Missing website or domain data'}

    domain_list = [_normalize_domain(
        d) for d in domains_str.split(args.sep) if d.strip()]

    for domain in domain_list:
        resolved_url, status_code, resolution_method = None, None, None

        for url_variation in _construct_url_variations(domain):
            try:
                await fetcher.rate_limiter.wait(url_variation)
                async with fetcher.session.head(
                    url_variation,
                    timeout=ASYNC_CONFIG['http_timeout'],
                    allow_redirects=True,
                    max_redirects=ASYNC_CONFIG['max_redirects'],
                    ssl=False
                ) as response:
                    if 200 <= response.status < 300:
                        resolved_url = str(response.url)
                        status_code = response.status
                        resolution_method = url_variation
                        break
            except Exception:
                continue

        result_base = {
            **row,
            'resolved_domain': domain,
            'resolved_url': resolved_url,
            'status_code': status_code,
            'resolution_method': resolution_method,
            'email_found': False,
            'robots_txt_blocked': False
        }

        if not resolved_url:
            return {**result_base, 'reason': 'Failed to resolve domain to a working URL'}

        if not await check_robots_txt(fetcher.session, resolved_url):
            return {**result_base, 'robots_txt_blocked': True, 'reason': 'Disallowed by robots.txt'}

        main_page_result = await fetcher.fetch_html(resolved_url)
        if not main_page_result['success']:
            return {**result_base, 'reason': 'Failed to fetch main page content'}

        if _check_email_domain(main_page_result['content'], domain):
            logger.info(f"Email domain '{domain}' FOUND on main page for {website}")
            return {**result_base, 'email_found': True, 'reason': 'Found on main page'}

        contact_links = _extract_and_score_contact_links(
            main_page_result['content'],
            main_page_result['final_url']
        )

        if not contact_links:
            return {**result_base, 'reason': 'Email not found; no contact pages identified'}

        for contact_url, score in contact_links[:2]:
            contact_page_result = await fetcher.fetch_html(contact_url)
            if contact_page_result['success'] and _check_email_domain(contact_page_result['content'], domain):
                logger.info(f"Email domain '{domain}' FOUND on contact page {contact_url}")
                return {**result_base, 'email_found': True, 'reason': f'Found on contact page (score: {score})'}

        return {**result_base, 'reason': 'Email not found after checking main and contact pages'}

    return {**row, 'reason': 'No domains processed'}


async def worker(
    name,
    args,
    fetcher,
    task_queue,
    result_queue
):
    while True:
        row, index = await task_queue.get()
        logger.debug(f"{name} processing row {index}")
        try:
            result = await process_row(row, args, fetcher)
        except Exception as e:
            logger.error(f"FATAL error processing row {index}: {e}", exc_info=True)
            result = {**row, 'reason': f'FATAL worker error: {e}'}

        await result_queue.put((result, index))
        task_queue.task_done()


async def read_tasks(
    args,
    task_queue,
    start_from_index
):
    logger.info(f"Starting CSV read from row {start_from_index}")
    row_count = 0
    async with aiofiles.open(args.input, mode='r', encoding='utf-8', newline='') as f:
        reader = aiocsv.AsyncDictReader(f)

        if start_from_index > 0:
            logger.info(f"Skipping to row {start_from_index}...")
            for _ in range(start_from_index):
                try:
                    await reader.__anext__()
                except StopAsyncIteration:
                    logger.warning(
                        "State file points past the end of the input file. Starting from the end.")
                    return 0

        index = start_from_index
        async for row in reader:
            await task_queue.put((row, index))
            row_count += 1
            index += 1

    return row_count


async def write_results(
    output_file,
    fieldnames,
    result_queue,
    total_rows,
    state_file
):
    processed_count = 0
    results_buffer = []

    async with aiofiles.open(output_file, mode='a', encoding='utf-8', newline='') as f:
        writer = aiocsv.AsyncDictWriter(f, fieldnames=fieldnames, restval="-")
        if await f.tell() == 0:
            await writer.writeheader()

        while processed_count < total_rows:
            result, index = await result_queue.get()
            results_buffer.append(result)
            processed_count += 1

            if len(results_buffer) >= ASYNC_CONFIG['result_buffer_size'] or processed_count == total_rows:
                await writer.writerows(results_buffer)
                logger.info(f"Progress: {processed_count}/{total_rows} ({processed_count/total_rows:.1%}) - Wrote batch of {len(results_buffer)} results.")
                results_buffer.clear()

                with open(state_file, 'w') as sf:
                    json.dump({'last_processed_index': index}, sf)

            result_queue.task_done()


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Asynchronous checker for email domains on websites."
    )
    parser.add_argument("-i", "--input", required=True,
                        help="Input CSV file path")
    parser.add_argument(
        "-o", "--output", default="domains_on_sites_async.csv", help="Output CSV file path")
    parser.add_argument("-d", "--id", default="ror_id", help="ID field name")
    parser.add_argument("-w", "--website", default="website",
                        help="Website field name")
    parser.add_argument("-f", "--field", default="domain",
                        help="Domains field name")
    parser.add_argument("-s", "--sep", default='|',
                        help="Domain separator (use a character like '|' or ',')")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last saved position")
    return parser.parse_args()


async def main():
    args = parse_arguments()
    start_time = time.monotonic()

    state_file = f"{args.output}.state"
    last_processed_index = -1
    if args.resume and os.path.exists(state_file):
        with open(state_file, 'r') as f:
            try:
                state = json.load(f)
                last_processed_index = state.get('last_processed_index', -1)
                logger.info(f"Resuming from after row {last_processed_index + 1}")
            except json.JSONDecodeError:
                logger.warning(
                    "State file is corrupted, starting from the beginning.")

    task_queue = asyncio.Queue(maxsize=ASYNC_CONFIG['queue_size'])
    result_queue = asyncio.Queue()

    with open(args.input, 'r', encoding='utf-8') as f:
        total_rows = sum(1 for line in f) - 1  # Subtract header

    rows_to_process = total_rows - (last_processed_index + 1)
    if rows_to_process <= 0:
        logger.info("Processing is already complete.")
        return

    with open(args.input, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        input_fieldnames = reader.fieldnames
    output_fieldnames = input_fieldnames + [
        'resolved_domain', 'resolved_url', 'status_code', 'resolution_method',
        'email_found', 'robots_txt_blocked', 'reason'
    ]

    with ProcessPoolExecutor(
        max_workers=ASYNC_CONFIG['selenium_workers'],
        initializer=init_selenium_worker,
        initargs=()
    ) as selenium_pool:
        rate_limiter = AsyncDomainRateLimiter(
            ASYNC_CONFIG['requests_per_minute'])

        async with aiohttp.ClientSession(
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'}
        ) as session:

            fetcher = AsyncFetcher(session, rate_limiter, selenium_pool)

            producer_task = asyncio.create_task(
                read_tasks(args, task_queue, last_processed_index + 1)
            )
            writer_task = asyncio.create_task(
                write_results(args.output, output_fieldnames,
                              result_queue, rows_to_process, state_file)
            )
            worker_tasks = []
            for i in range(ASYNC_CONFIG['max_concurrent_tasks']):
                task = asyncio.create_task(
                    worker(f"Worker-{i+1}", args, fetcher, task_queue, result_queue)
                )
                worker_tasks.append(task)

            await producer_task
            logger.info("Producer has finished reading the input file.")

            await task_queue.join()
            logger.info("All tasks have been processed by workers.")

            await result_queue.join()
            logger.info("All results have been written to the output file.")

            for task in worker_tasks:
                task.cancel()
            writer_task.cancel()

            await asyncio.gather(*worker_tasks, writer_task, return_exceptions=True)

    duration = time.monotonic() - start_time
    logger.info(f"Processing of {rows_to_process} rows completed in {duration:.2f} seconds.")
    if os.path.exists(state_file):
        os.remove(state_file)
        logger.info("Removed state file.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nProcess interrupted by user. Exiting.")
