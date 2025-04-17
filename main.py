import requests
from bs4 import BeautifulSoup
import time
import random
import urllib.parse
import json
import logging
import os
import re # <--- Added for filename sanitizing
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
    # {"http": "http://proxy1:port", "https": "http://proxy1:port"}
]

# ==============================================================================
# --- Search Query Configuration ---
SEARCH_QUERIES = [
    f'"{TARGET_USERNAME}" site:instagram.com',
    f'from:{TARGET_USERNAME} site:instagram.com', # Note: 'from:' might not work well with Google search
    f'"{TARGET_USERNAME}" commented on site:instagram.com',
]

# Number of Google Search result pages to fetch per query
PAGES_PER_QUERY = 1  # <<<--- Start with 1 page during debugging

# Time delays (in seconds)
DELAY_BETWEEN_PAGES_MIN = 10 # Be generous during testing
DELAY_BETWEEN_PAGES_MAX = 25
DELAY_BETWEEN_QUERIES_MIN = 25
DELAY_BETWEEN_QUERIES_MAX = 50

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
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8', # Updated Accept
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br', # Added encoding
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1', # Common header
    'Sec-Fetch-Dest': 'document', # Common fetch metadata
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin', # Or 'cross-site' if coming from elsewhere
    'TE': 'trailers' # Added TE
}

# --- Logging Setup ---
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w' # Overwrite log each run
)
# Also log to console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING) # Show warnings and errors on console
formatter = logging.Formatter('%(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logging.getLogger().addHandler(console_handler)


# --- Functions ---

def setup_session():
    """Create a requests session with retries."""
    session = requests.Session()
    # Retry on 429 (Too Many Requests) and server errors
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def fetch_search_results(query, pages=1, session=None):
    """Fetches Google search results for a given query."""
    found_results = [] # Store dicts {title, link, snippet}
    session = session or setup_session()
    added_links = set() # Keep track of links added to avoid duplicates

    for page in range(pages):
        start_index = page * 10
        params = {
            'q': query,
            'start': start_index,
            'hl': 'en', # Force English results
            'num': 10, # Explicitly request 10 results
            'filter': 0 # Try disabling duplicate filtering by Google
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
                timeout=25 # Increased timeout slightly
            )
            logging.info(f"Request URL: {response.url}") # Log the exact URL requested
            logging.info(f"Response Status Code: {response.status_code}")

            # Check for blocking indicators *before* raising for status
            if any(x in response.text.lower() for x in ["/recaptcha/", "/sorry/"]) or response.status_code == 429:
                logging.warning(f"Google block detected for query '{query}', page {page + 1}. Status: {response.status_code}")
                print(f"WARN: Google block detected (Status: {response.status_code}). Stopping this query.")
                 # Save HTML on block
                with open(f"blocked_page_{page+1}.html", "w", encoding="utf-8") as f:
                    f.write(response.text)
                break

            response.raise_for_status() # Raise error for other bad status codes (4xx, 5xx)

            soup = BeautifulSoup(response.text, 'html.parser')

            # --- SELECTOR UPDATE AREA ---
            # YOU MUST UPDATE THESE SELECTORS BASED ON CURRENT GOOGLE HTML
            # Use browser dev tools (F12 -> Inspect) on Google Search results
            # Common patterns observed late 2023 / early 2024 (WILL CHANGE):
            result_blocks = soup.find_all('div', class_='MjjYud') # Often contains organic results
            if not result_blocks:
                 result_blocks = soup.find_all('div', class_='kvH3mc') # Another potential container
            # Add more attempts based on inspection...
            # Example: result_blocks = soup.find_all('div', {'jscontroller': True, 'data-cid': True})

            # --- END SELECTOR UPDATE AREA ---

            if not result_blocks:
                logging.warning(f"No result blocks found for query '{query}', page {page + 1} using current selectors. Saving HTML.")
                print("WARN: No result blocks found. Google HTML structure may have changed. Check selectors!")
                # --- Filename Sanitizing ---
                safe_query_part = re.sub(r'[\\/*?:"<>|]', "", query)
                safe_query_part = safe_query_part.replace(" ", "_")[:50]
                debug_filename = f"debug_page_{safe_query_part}_{page+1}.html"
                try:
                    with open(debug_filename, "w", encoding="utf-8") as f:
                        f.write(soup.prettify())
                    print(f"Saved debug HTML to: {debug_filename}")
                    logging.info(f"Saved debug HTML to: {debug_filename}")
                except Exception as e_write:
                    logging.error(f"Could not write debug file {debug_filename}: {e_write}")
                    print(f"ERROR: Could not write debug file {debug_filename}: {e_write}")
                continue # Go to next page or end loop

            page_found_count = 0
            for block in result_blocks:
                # --- SELECTOR UPDATE AREA (Link, Title, Snippet) ---
                link_tag = block.find('a', href=True)
                title_tag = None
                snippet_element = None

                if link_tag:
                     # Title is often within an h3 inside the link
                     title_tag = link_tag.find('h3', class_=re.compile(r'LC20lb')) # Example class, UPDATE!
                     if not title_tag: # Fallback: maybe title is elsewhere?
                          title_tag = block.find('h3', class_=re.compile(r'title-class')) # UPDATE!

                # Snippet location varies greatly. Look for divs/spans containing the text description.
                # Often requires inspecting multiple potential classes.
                snippet_container = block.find('div', class_=re.compile(r'VwiC3b|IsZvec')) # Example classes, UPDATE!
                if snippet_container:
                    # Sometimes snippet text is directly within, sometimes nested spans
                    snippet_element = snippet_container.find('span') # Or might be snippet_container itself
                    if not snippet_element:
                         snippet_element = snippet_container # Use the container if no span inside

                # --- END SELECTOR UPDATE AREA ---


                if link_tag and link_tag['href'].startswith('http'):
                    link = link_tag['href']
                    title_text = title_tag.get_text(strip=True) if title_tag else "No Title Found"
                    snippet_text = snippet_element.get_text(separator=" ", strip=True) if snippet_element else "No Snippet Found"

                    is_post_link = link.startswith(("https://www.instagram.com/p/", "https://instagram.com/p/"))
                    text_to_check = (title_text + " " + snippet_text).lower()
                    username_mentioned = TARGET_USERNAME.lower() in text_to_check

                    if is_post_link and username_mentioned:
                        result = {
                            'title': title_text,
                            'link': link,
                            'snippet': snippet_text[:250] # Store slightly longer snippet
                        }
                        # Add result only if the link hasn't been added before
                        if result['link'] not in added_links:
                            logging.info(f"Found potential hit: {result['link']}")
                            print(f"  [Potential Hit] Title: {result['title']}")
                            print(f"  Link: {result['link']}")
                            print(f"  Snippet: {result['snippet']}...")
                            print("-" * 20)
                            found_results.append(result)
                            added_links.add(result['link']) # Track added link
                            page_found_count += 1

            if page_found_count == 0 and result_blocks:
                logging.info(f"No relevant Instagram post results found on page {page + 1} for query '{query}'")
                print("  No relevant Instagram post results found on this page (mentioning username).")

        except requests.exceptions.RequestException as e:
            logging.error(f"Request error for query '{query}', page {page + 1}: {e}")
            # Don't print stack trace for common errors like timeouts
            print(f"ERROR: Request error processing query '{query}': {e}")
            break # Stop processing this query on significant error
        except Exception as e_main:
             logging.exception(f"Unexpected error processing query '{query}', page {page + 1}: {e_main}")
             print(f"ERROR: An unexpected error occurred: {e_main}")
             # Optionally save HTML on unexpected error
             try:
                 with open(f"error_page_{page+1}.html", "w", encoding="utf-8") as f:
                    f.write(response.text if 'response' in locals() else "No response object available")
             except: pass
             break # Stop query on unexpected error


        # --- Delay ---
        if page < pages - 1:
            sleep_time = random.uniform(DELAY_BETWEEN_PAGES_MIN, DELAY_BETWEEN_PAGES_MAX)
            logging.info(f"Sleeping for {sleep_time:.2f} seconds before next page")
            print(f"Sleeping for {sleep_time:.2f} seconds before next page...")
            time.sleep(sleep_time)

    return found_results

# --- Save Results ---
def save_results(results):
    """Save results to a JSON file."""
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logging.info(f"Saved {len(results)} unique results to {OUTPUT_FILE}")
        print(f"\nSaved {len(results)} unique results to {OUTPUT_FILE}")
    except Exception as e:
        logging.error(f"Failed to save results to {OUTPUT_FILE}: {e}")
        print(f"ERROR: Failed to save results to {OUTPUT_FILE}: {e}")

# --- Main Execution ---
if __name__ == "__main__":
    if not TARGET_USERNAME or TARGET_USERNAME == "replace_with_target_instagram_username":
        logging.critical("TARGET_USERNAME not set in script.")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! ERROR: Please set the TARGET_USERNAME variable in the   !!!")
        print("!!!        script before running.                           !!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    else:
        print(f"--- Starting OSINT Google Search for Instagram User: {TARGET_USERNAME} ---")
        print(f"--- Logging to: {LOG_FILE} ---")
        print(f"--- Results will be saved to: {OUTPUT_FILE} ---")
        print("!!! WARNING: This method is NOT reliable or comprehensive. Relies on fragile selectors. !!!")
        print("-" * 60)
        logging.info(f"Script started. Target: {TARGET_USERNAME}")

        session = setup_session()
        all_potential_results = []
        processed_links = set() # Track links across all queries

        for i, query in enumerate(SEARCH_QUERIES):
            print(f"\n--- Processing Query {i+1}/{len(SEARCH_QUERIES)}: [{query}] ---")
            logging.info(f"Processing query {i+1}: {query}")

            query_results = fetch_search_results(query, pages=PAGES_PER_QUERY, session=session)

            new_results_count = 0
            for result in query_results:
                if result['link'] not in processed_links:
                    all_potential_results.append(result)
                    processed_links.add(result['link'])
                    new_results_count += 1

            print(f"--- Query {i+1} finished. Found {len(query_results)} potential results ({new_results_count} new unique links). ---")
            logging.info(f"Query {i+1} finished. Found {len(query_results)} results, {new_results_count} new unique.")


            # Delay between different queries
            if i < len(SEARCH_QUERIES) - 1:
                sleep_time = random.uniform(DELAY_BETWEEN_QUERIES_MIN, DELAY_BETWEEN_QUERIES_MAX)
                logging.info(f"Sleeping for {sleep_time:.2f} seconds before next query")
                print(f"\nSwitching query. Sleeping for {sleep_time:.2f} seconds...\n")
                time.sleep(sleep_time)

        print("\n" + "=" * 60)
        print("--- Search Complete ---")
        logging.info("All queries processed.")

        if all_potential_results:
            print(f"Found a total of {len(all_potential_results)} potential unique Instagram post links where '{TARGET_USERNAME}' might be mentioned:")
            # Optional: Print links at the end
            # for result in all_potential_results:
            #      print(f"- {result['link']}")
            save_results(all_potential_results)
        else:
            logging.warning(f"No potential links found for '{TARGET_USERNAME}' across all queries with current selectors.")
            print(f"No potential links found for '{TARGET_USERNAME}'. This likely means:")
            print("  a) The selectors need updating due to Google HTML changes.")
            print("  b) Google hasn't indexed public posts mentioning the user recently.")
            print("  c) The user has low public activity indexed by Google.")

        print("\n--- Important Notes ---")
        print("1. Verify links manually. Mention != Comment by user.")
        print("2. Selectors in the script WILL break over time. Update them using browser dev tools.")
        print("3. Check the log file ({LOG_FILE}) for detailed information and errors.")
        print("4. Avoid running too frequently to prevent Google blocks.")
        print("=" * 60)
        logging.info("Script finished.")