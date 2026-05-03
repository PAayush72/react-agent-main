# tools/web_tools.py — Web search and page fetching
import requests
from bs4 import BeautifulSoup
from typing import Optional


def web_search(query: str, num_results: int = 5) -> str:
    """
    Search the web using DuckDuckGo.
    Returns formatted search results with titles, URLs, and snippets.
    """
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))

        if not results:
            return f"No results found for: {query}"

        output = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "No title")
            url = r.get("href", r.get("link", ""))
            snippet = r.get("body", r.get("snippet", "No description"))
            output.append(f"{i}. {title}\n   {url}\n   {snippet}")

        return "\n\n".join(output)

    except ImportError:
        # Fallback: scrape DuckDuckGo HTML directly
        return _fallback_search(query, num_results)
    except Exception as e:
        return f"Search error: {str(e)}"


def _fallback_search(query: str, num_results: int = 5) -> str:
    """Fallback search using DuckDuckGo HTML scraping."""
    try:
        url = f"https://duckduckgo.com/html/?q={requests.utils.quote(query)}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        output = []
        for i, result in enumerate(soup.find_all('div', class_='result__body', limit=num_results), 1):
            title_elem = result.find('a', class_='result__url')
            snippet_elem = result.find('a', class_='result__snippet')
            if title_elem:
                title = title_elem.get_text(strip=True)
                link = title_elem.get('href', '')
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                output.append(f"{i}. {title}\n   {link}\n   {snippet}")

        if not output:
            return "No results found or unable to parse search results."

        return "\n\n".join(output)
    except Exception as e:
        return f"Search failed: {str(e)}"


def fetch_page(url: str, max_length: int = 10000) -> str:
    """
    Fetch a web page and convert to readable text.
    Strips scripts, styles, nav, and other non-content elements.
    """
    try:
        response = requests.get(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; AgentBot/1.0)'},
            timeout=10
        )
        response.raise_for_status()
    except Exception as e:
        return f"Error fetching page: {e}"

    soup = BeautifulSoup(response.text, 'html.parser')

    # Remove non-content elements
    for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form']):
        element.decompose()

    # Try to find main content
    main = soup.find('main') or soup.find('article') or soup.find('div', class_='content') or soup
    text = main.get_text(separator='\n', strip=True)

    # Clean up
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    text = '\n'.join(lines)

    if len(text) > max_length:
        text = text[:max_length] + f"\n\n... [truncated — {len(text)} chars total]"

    return text