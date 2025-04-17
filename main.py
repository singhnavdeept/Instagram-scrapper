import requests
from bs4 import BeautifulSoup
import time
import random
import urllib.parse
import json
import logging
import os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==============================================================================
# == CONFIGURATION - MODIFY THIS SECTION ==
# ==============================================================================
TARGET_USERNAME = "leanbeefpatty"  # <<<--- SET THE TARGET USERNAME HERE
OUTPUT_FILE = f"{TARGET_USERNAME}_instagram_results.json"  # Output file for results
LOG_FILE = "scraper.log"  # Log file for debugging
USE_PROXIES = False  # Set to True if you have a proxy pool
PROXY_POOL = [
    # Add proxies here, e.g., {"http": "http://proxy1:port", "https": "http://proxy1:port"}
    # Example: {"http": "http://123.45.67.89:8080", "https": "http://123.45.67.89:8080"}
]

# ==============================================================================
# --- Search Query Configuration ---
SEARCH_QUERIES = [
    f'"{TARGET_USERNAME}" site:instagram.com',
    f'from:{TARGET_USERNAME} site:instagram.com',
    f'"{TARGET_USERNAME}" commented on site:instagram.com',
]

# Number of Google Search result pages to fetch per query
PAGES_PER_QUERY = 2  # Keep low (1-3) to avoid blocking

# Time delays (in seconds)
DELAY_BETWEEN_PAGES_MIN = 8
DELAY_BETWEEN_PAGES_MAX = 20
DELAY_BETWEEN_QUERIES_MIN = 20
DELAY_BETWEEN_QUERIES_MAX = 40

# --- Technical Configuration ---
GOOGLE_SEARCH_URL = "https://www.google.com/search"

# Headers to mimic a browser
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

# Additional headers for realism
DEFAULT_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
}

# --- Logging Setup ---
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- Functions ---

def setup_session():
    """Create a requests session with retries."""
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def fetch_search_results(query, pages=1, session=None):
    """Fetches Google search results for a given query."""
    found_links = []
    session = session or setup_session()

    for page in range(pages):
        start_index = page * 10
        params = {
            'q': query,
            'start': start_index,
            'hl': 'en',
        }
        headers = {
            'User-Agent': random.choice(USER_AGENTS),
            **DEFAULT_HEADERS
        }
        proxies = random.choice(PROXY_POOL) if USE_PROXIES and PROXY_POOL else None

        logging.info(f"Searching: '{query}' - Page {page + 1}/{pages}")
        print(f"Searching: '{query}' - Page {page + 1}/{pages}")

        try:
            response = session.get(
                GOOGLE_SEARCH_URL,
                params=params,
                headers=headers,
                proxies=proxies,
                timeout=20
            )
            response.raise_for_status()

            # Check for blocking
            if any(x in response.text.lower() for x in ["captcha", "unusual traffic"]) or response.status_code == 429:
                logging.warning(f"Possible Google block detected for query '{query}', page {page + 1}")
                print("WARN: Possible Google block detected. Stopping this query.")
                break

            soup = BeautifulSoup(response.text, 'html.parser')

            # Flexible parsing with multiple selector attempts
            result_blocks = (
                soup.find_all('div', class_='tF2Cxc') or
                soup.find_all('div', class_='Gx5Zad') or
                soup.find_all('div', class_='g') or
                soup.find_all('div', {'data-ved': True})
            )

            if not result_blocks:
                logging.warning(f"No result blocks found for query '{query}', page {page + 1}. Saving HTML.")
                print("WARN: No result blocks found. Google HTML structure may have changed.")
                with open(f"debug_page_{query}_{page+1}.html", "w", encoding="utf-8") as f:
                    f.write(soup.prettify())
                continue

            page_found_count = 0
            for block in result_blocks:
                link_tag = block.find('a', href=True)
                snippet_tag = (
                    block.find('div', class_='VwiC3b') or
                    block.find('span', class_='aCOpRe') or
                    block.find('div', class_='s3v9rd')
                )

                if link_tag and link_tag['href'].startswith('http'):
                    link = link_tag['href']
                    title_tag = link_tag.find('h3')
                    title_text = title_tag.get_text() if title_tag else "No Title Found"
                    snippet_text = snippet_tag.get_text(separator=" ", strip=True) if snippet_tag else "No Snippet Found"

                    is_post_link = link.startswith(("https://www.instagram.com/p/", "https://instagram.com/p/"))
                    username_mentioned = TARGET_USERNAME.lower() in (title_text.lower() + snippet_text.lower())

                    if is_post_link and annotation_pipes == None:

                        logging.info(f"Found potential hit: {link}")
                        print(f"  [Potential Hit] Title: {title_text}")
                        print(f"  Link: {link}")
                        print(f"  Snippet: {snippet_text[:200]}...")
                        print("-" * 20)
                        found_links.append({
                            'title': title_text,
                            'link': link,
                            'snippet': snippet_text[:200]
                        })
                        page_found_count += 1
                    if is_post_link and username_mentioned:
                        result = {
                            'title': title_text,
                            'link': link,
                            'snippet': snippet_text[:200]
                        }
                        if result not in found_links:
                            logging.info(f"Found potential hit: {result}")
                            print(f"  [Potential Hit] Title: {title_text}")
                            print(f"  Link: {link}")
                            print(f"  Snippet: {snippet_text[:200]}...")
                            print("-" * 20)
                            found_links.append(result)
                            page_found_count += 1

            if page_found_count == 0 and result_blocks:
                logging.info(f"No relevant results found on page {page + 1} for query '{query}'")
                print("  No relevant results found on this page.")
            elif not result_blocks:
                logging.info(f"No result blocks found at all on page {page + 1} for query '{query}'")
                print("  No Google result blocks found.")

        except requests.exceptions.RequestException as e:
            logging.error(f"Request error for query '{query}', page {page + 1}: {e}")
            print(f"ERROR: Request error: {e}")
            break

        if page < pages - 1:
            sleep_time = random.uniform(DELAY_BETWEEN_PAGES_MIN, DELAY_BETWEEN_PAGES_MAX)
            logging.info(f"Sleeping for {sleep_time:.2f} seconds before next page")
            print(f"Sleeping for {sleep_time:.2f} seconds before next page...")
            time.sleep(sleep_time)

    return found_links

# --- Save Results ---
def save_results(results):
    """Save results to a JSON file."""
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logging.info(f"Saved {len(results)} results to {OUTPUT_FILE}")
    print(f"Saved {len(results)} results to {OUTPUT_FILE}")

# --- Main Execution ---
if __name__ == "__main__":
    if not TARGET_USERNAME or TARGET_USERNAME == "replace_with_target_instagram_username":
        logging.error("TARGET_USERNAME not set")
        print("ERROR: Please set the TARGET_USERNAME variable.")
    else:
        logging.info(f"Starting OSINT Comment Search for Instagram User: {TARGET_USERNAME}")
        print(f"--- Starting OSINT Comment Search for Instagram User: {TARGET_USERNAME} ---")
        print("!!! WARNING: This method is NOT reliable for finding ALL comments. !!!")
        print("-" * 60)

        session = setup_session()
        all_potential_links = []

        for i, query in enumerate(SEARCH_QUERIES):
            print(f"\n--- Processing Query {i+1}/{len(SEARCH_QUERIES)} ---")
            logging.info(f"Processing query {i+1}: {query}")
            links = fetch_search_results(query, pages=PAGES_PER_QUERY, session=session)
            all_potential_links.extend(links)

            if i < len(SEARCH_QUERIES) - 1:
                sleep_time = random.uniform(DELAY_BETWEEN_QUERIES_MIN, DELAY_BETWEEN_QUERIES_MAX)
                logging.info(f"Sleeping for {sleep_time:.2f} seconds before next query")
                print(f"\nSwitching query. Sleeping for {sleep_time:.2f} seconds...\n")
                time.sleep(sleep_time)

        print("\n" + "=" * 60)
        print("--- Search Complete ---")
        if all_potential_links:
            logging.info(f"Found {len(all_potential_links)} potential Instagram post links")
            print(f"Found {len(all_potential_links)} potential Instagram post links:")
            for result in all_potential_links:
                print(f"- {result['link']} ({result['title']})")
            save_results(all_potential_links)
        else:
            logging.info(f"No potential comment links found for '{TARGET_USERNAME}'")
            print(f"No potential comment links found for '{TARGET_USERNAME}'.")

        print("\n--- Important Notes ---")
        print("1. Results are limited by Google's indexing and may miss most comments.")
        print("2. Verify links manually to confirm activity.")
        print("3. Consider using Instagram-specific tools (e.g., instaloader) for better results.")
        print("4. Frequent runs may trigger Google CAPTCHAs or blocks.")
        print("=" * 60)