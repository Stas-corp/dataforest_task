from db import init_db
from scraper import start_scraping

if __name__ == "__main__":
    init_db()
    start_scraping()