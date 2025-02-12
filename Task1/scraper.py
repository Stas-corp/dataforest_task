import threading
import queue
import requests
from bs4 import BeautifulSoup
from db import save_product

BASE_URL = "https://www.vendr.com"
CATEGORIES = ["devops", "it-infrastructure", "data-analytics-and-management"]

scrap_queue = queue.Queue()
db_queue = queue.Queue()

MAX_WORKERS_SCRAP = 15
MAX_WORKERS_DB = 1

def db_worker() -> None:
    while True:
        product = db_queue.get()
        if product is None:
            db_queue.task_done()
            break
        save_product(product)
        db_queue.task_done()
        
def scrape_product_worker():
    while True:
        item = scrap_queue.get()
        if item is None:
            scrap_queue.task_done()
            break
        url, category = item
        scrape_product(url, category)
        scrap_queue.task_done()

def check_response(url: str) -> tuple[BeautifulSoup, requests.Response]:
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "lxml")
        none_page = soup.find('div', class_='rt-Flex rt-r-fd-column rt-r-ai-center _noResults_j928a_80')
        if none_page:
            response.status_code = 404
            return (None, response)
        return (soup, response)
    return (None, response)

def scrape_product(url: str, category: str) -> None:
    soup, response = check_response(url)
    if response.status_code == 200:
        name = soup.find('h1', class_='rt-Heading rt-r-size-6 xs:rt-r-size-8').text
        try:
            price = soup.find('div', class_='rt-Flex rt-r-fd-column rt-r-w rt-r-max-w').text
            price = price.split('$') # ['Median:\xa0', '36,000', '12,500', '165,000LowHigh']
            price_range = f'{price[2]}; {price[1]}; {price[3][:-7]}'
        except Exception as e:
            price_range = ''
        description = soup.find('div', class_='rt-Flex rt-r-fd-column rt-r-gap-2').text
    
        product_data = {
            "name": name,
            "category": category,
            "price_range": price_range,
            "description": description,
            }
        db_queue.put(product_data)

def scrape_subcategorys(url: str) -> None:
    try:
        pagination = True
        page = 1
        category = url.split('/')[2]
        while pagination:
            full_url = BASE_URL + url[:-1] + str(page)
            soup, response = check_response(full_url)
            if response.status_code == 200:
                section = soup.find_all('section')
                product_card = section[1].find_all('a')
                for p_url in product_card:
                    product_url = BASE_URL + p_url.get('href')
                    scrap_queue.put((product_url, category))
                page += 1
                print(response, full_url.split('/')[-1])
            else:
                print(response, full_url.split('/')[-1])
                pagination = False
    except Exception as e:
        print(f"Processing error {full_url}: {e}")


def start_scraping() -> None:
    """Main function"""
    threads = []
    
    for _ in range(MAX_WORKERS_SCRAP):
        thr = threading.Thread(target=scrape_product_worker, daemon=True)
        thr.start()
        threads.append(thr)
        
    db_thr = threading.Thread(target=db_worker)
    db_thr.start()
    
    for category in CATEGORIES:
        category_url = f"{BASE_URL}/categories/{category}"
        soup, response = check_response(category_url)
        if response.status_code == 200:
            all_subcategory = soup.find('h2', class_='rt-Heading rt-r-size-4', string='Browse all categories').parent
            subcategory_links = all_subcategory.find_all("a", href=lambda x: x and f"/categories/{category}" in x)
            for link in subcategory_links:
                print(link.get('href'))
                thread = threading.Thread(target=scrape_subcategorys, args=(link.get('href'),), daemon=True)
                thread.start()

    scrap_queue.join()
    
    for _ in range(MAX_WORKERS_SCRAP):
        scrap_queue.put(None)
    
    for thread in threads:
        thread.join()
        
    db_queue.join()
    db_queue.put(None)
    db_thr.join()
    
if __name__ == '__main__':
    import db
    db.init_db()
    start_scraping()