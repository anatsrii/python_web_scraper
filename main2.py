# Improved Stock Scraper with Error Handling & Rate Limiting

import requests
from bs4 import BeautifulSoup
import json
import os
import re
import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
import time
import logging
from functools import wraps

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('stock_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Rate Limiting Decorator
def rate_limit(delay=1):
    """Rate limiting decorator to add delay between function calls"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger.info(f"Rate limiting: waiting {delay} seconds before {func.__name__}")
            time.sleep(delay)
            return func(*args, **kwargs)
        return wrapper
    return decorator

# Safe Request Function
def safe_request(url, headers=None, params=None, max_retries=3, timeout=10):
    """Make HTTP request with retry logic and error handling"""
    if headers is None:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Making request to {url} (attempt {attempt + 1})")
            response = requests.get(url, headers=headers, params=params, timeout=timeout)
            response.raise_for_status()  # Raise exception for bad status codes
            return response
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.info(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                logger.error(f"All {max_retries} attempts failed for {url}")
                return None

# Safe Selenium Driver
def get_safe_driver(headless=True, max_retries=3):
    """Create Selenium driver with error handling"""
    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Creating Chrome driver (attempt {attempt + 1})")
            driver = webdriver.Chrome(options=options)
            return driver
        except WebDriverException as e:
            logger.warning(f"Driver creation attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                logger.error("Failed to create Chrome driver after all attempts")
                return None

@rate_limit(delay=2)
def fetch_factsheet_selenium(symbol):
    """Fetch factsheet data using Selenium with error handling"""
    url = f"https://www.set.or.th/th/market/product/stock/quote/{symbol}/factsheet"
    driver = None
    
    try:
        driver = get_safe_driver()
        if not driver:
            return {"symbol": symbol, "error": "Failed to create driver"}
        
        logger.info(f"Fetching factsheet for {symbol}")
        driver.get(url)
        
        # Wait longer and check if page loaded
        time.sleep(5)
        
        # Check if page loaded properly
        if "ไม่พบข้อมูล" in driver.page_source or len(driver.page_source) < 1000:
            logger.warning(f"Page may not have loaded properly for {symbol}")
            # Try refreshing once
            driver.refresh()
            time.sleep(5)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        data = {"symbol": symbol}

        # 1. Company Name - ลองหลาย selector
        try:
            company_name_tag = (soup.select_one(".security-symbol") or 
                              soup.select_one(".company-name") or 
                              soup.select_one("h1") or
                              soup.find("span", string=re.compile(symbol, re.I)))
            data["company_name"] = company_name_tag.text.strip() if company_name_tag else None
            logger.info(f"Found company name: {data['company_name']}")
        except Exception as e:
            logger.warning(f"Error getting company name for {symbol}: {e}")
            data["company_name"] = None

        # 2. Price - ลองหลาย selector
        try:
            price_tag = (soup.select_one(".last-price") or 
                        soup.select_one(".price") or
                        soup.select_one("[data-testid*='price']") or
                        soup.find("span", string=re.compile(r'\d+\.\d{2}')))
            if price_tag:
                price_text = re.sub(r'[^\d.]', '', price_tag.text)
                data["price"] = float(price_text) if price_text else None
            else:
                data["price"] = None
            logger.info(f"Found price: {data['price']}")
        except Exception as e:
            logger.warning(f"Error getting price for {symbol}: {e}")
            data["price"] = None

        # 3. Market Cap
        data["market_cap"] = None
        try:
            for div in soup.find_all("div"):
                if div.text and "มูลค่าหลักทรัพย์ตามราคาตลาด" in div.text:
                    try:
                        cap = div.find_next("div").text.strip().replace(",", "").replace("ล้านบาท", "")
                        data["market_cap"] = float(cap) * 1e6
                        break
                    except:
                        continue
        except Exception as e:
            logger.warning(f"Error getting market cap for {symbol}: {e}")

        # 4. All Table Data - ลองหลายแบบ
        table_data = {}
        try:
            # ลองหลาย selector สำหรับตาราง
            tables = (soup.select("table.table-info") or 
                     soup.select("table") or 
                     soup.select(".table"))
            
            for table in tables:
                for row in table.find_all("tr"):
                    cols = row.find_all(["td", "th"])
                    if len(cols) >= 2:
                        key = cols[0].text.strip()
                        value = cols[1].text.strip()
                        if key and value:  # ไม่เก็บถ้าว่าง
                            table_data[key] = value
            
            logger.info(f"Found {len(table_data)} table entries")
        except Exception as e:
            logger.warning(f"Error getting table data for {symbol}: {e}")
        
        data["factsheet_table"] = table_data
        
        # Debug: Print page source length to see if we got content
        logger.info(f"Page source length: {len(driver.page_source)} characters")
        
        # Debug: Save HTML for inspection
        if logger.level <= logging.DEBUG:
            with open(f"debug_{symbol}_factsheet.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
        logger.info(f"Successfully fetched factsheet for {symbol}")
        return data

    except Exception as e:
        logger.error(f"Unexpected error in fetch_factsheet_selenium for {symbol}: {e}")
        return {"symbol": symbol, "error": str(e)}
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

@rate_limit(delay=1)
def fetch_company_highlights(symbol):
    """Fetch company highlights with error handling"""
    url = f"https://www.set.or.th/th/market/product/stock/quote/{symbol}/financial-statement/company-highlights"
    
    try:
        logger.info(f"Fetching company highlights for {symbol}")
        response = safe_request(url)
        if not response:
            return {"symbol": symbol, "error": "Failed to fetch highlights page"}

        soup = BeautifulSoup(response.text, "html.parser")
        data = {
            "symbol": symbol,
            "highlights": {
                "financials": []
            }
        }

        tables = soup.find_all("table")
        for table in tables:
            if "ปี" in table.text and "รายได้รวม" in table.text:
                rows = table.find_all("tr")[1:]
                for row in rows:
                    try:
                        cols = [td.get_text(strip=True).replace(",", "") for td in row.find_all("td")]
                        if len(cols) >= 9:
                            item = {
                                "year": int(cols[0]) if cols[0] else None,
                                "revenue": float(cols[1]) if cols[1] and cols[1] != '-' else None,
                                "net_profit": float(cols[2]) if cols[2] and cols[2] != '-' else None,
                                "eps": float(cols[3]) if cols[3] and cols[3] != '-' else None,
                                "bvps": float(cols[4]) if cols[4] and cols[4] != '-' else None,
                                "roe": float(cols[5]) if cols[5] and cols[5] != '-' else None,
                                "net_profit_margin": float(cols[6]) if cols[6] and cols[6] != '-' else None,
                                "pe": float(cols[7]) if cols[7] and cols[7] != '-' else None,
                                "pbv": float(cols[8]) if cols[8] and cols[8] != '-' else None,
                            }
                            data["highlights"]["financials"].append(item)
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Error parsing financial row for {symbol}: {e}")
                        continue
        
        logger.info(f"Successfully fetched highlights for {symbol}")
        return data

    except Exception as e:
        logger.error(f"Unexpected error in fetch_company_highlights for {symbol}: {e}")
        return {"symbol": symbol, "error": str(e)}

@rate_limit(delay=1)
def fetch_rights_benefits(symbol):
    """Fetch rights and benefits with error handling"""
    url = f"https://www.set.or.th/api/set/company-rights-and-benefits/{symbol}?type=financial"
    
    try:
        logger.info(f"Fetching rights & benefits for {symbol}")
        response = safe_request(url)
        if not response:
            return {"symbol": symbol, "error": "Failed to fetch rights & benefits", "dividends": []}

        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON response for {symbol}: {e}")
            return {"symbol": symbol, "error": "Invalid JSON response", "dividends": []}

        dividend_data = []
        for item in data.get("data", []):
            try:
                if item.get("rightsType") == "เงินปันผล":
                    dividend_data.append({
                        "year": item.get("entitlementYear"),
                        "type": item.get("benefitType"),
                        "announce_date": item.get("signPostDate"),
                        "xd_date": item.get("xdDate"),
                        "payment_date": item.get("paymentDate"),
                        "amount_per_share": item.get("amount"),
                        "note": item.get("remark")
                    })
            except Exception as e:
                logger.warning(f"Error parsing dividend data for {symbol}: {e}")
                continue

        logger.info(f"Successfully fetched {len(dividend_data)} dividend records for {symbol}")
        return {"symbol": symbol, "dividends": dividend_data}

    except Exception as e:
        logger.error(f"Unexpected error in fetch_rights_benefits for {symbol}: {e}")
        return {"symbol": symbol, "error": str(e), "dividends": []}

@rate_limit(delay=1)
def fetch_financial_statements(symbol):
    """Fetch financial statement links with error handling"""
    url = f"https://www.set.or.th/th/market/product/stock/quote/{symbol}/financial-statement/financial-position"
    
    try:
        logger.info(f"Fetching financial statements for {symbol}")
        response = safe_request(url)
        if not response:
            return {"symbol": symbol, "error": "Failed to fetch financial statements page", "financial_statements": []}

        soup = BeautifulSoup(response.content, "html.parser")
        file_links = []
        
        for link in soup.find_all("a", href=True):
            try:
                href = link["href"]
                if re.search(r"\.(pdf|xls|xlsx)$", href, re.IGNORECASE):
                    if symbol.lower() in href.lower():
                        file_url = href if href.startswith("http") else "https://www.set.or.th" + href
                        file_name = file_url.split("/")[-1].lower()
                        
                        year_match = re.search(r"(20\d{2})", file_name)
                        period_match = re.search(r"q[1-4]|y(?:early)?", file_name)
                        
                        file_links.append({
                            "url": file_url,
                            "year": year_match.group(1) if year_match else None,
                            "period": period_match.group(0).upper() if period_match else "UNKNOWN",
                            "language": "th" if "th" in file_name else "en" if "en" in file_name else "unknown",
                            "type": file_url.split(".")[-1].upper()
                        })
            except Exception as e:
                logger.warning(f"Error parsing file link for {symbol}: {e}")
                continue

        logger.info(f"Successfully found {len(file_links)} financial statement files for {symbol}")
        return {"symbol": symbol, "financial_statements": file_links}

    except Exception as e:
        logger.error(f"Unexpected error in fetch_financial_statements for {symbol}: {e}")
        return {"symbol": symbol, "error": str(e), "financial_statements": []}

@rate_limit(delay=1)
def fetch_historical_prices(symbol, months=60):
    """Fetch historical prices with error handling"""
    url = "https://www.set.or.th/api/set/stock/price-chart"
    
    try:
        logger.info(f"Fetching historical prices for {symbol}")
        end_date = datetime.datetime.today()
        start_date = end_date - datetime.timedelta(days=30 * months)

        params = {
            "symbol": symbol,
            "type": "month",
            "range": f"{start_date.strftime('%Y-%m-%d')}_{end_date.strftime('%Y-%m-%d')}"
        }

        response = safe_request(url, params=params)
        if not response:
            return {"symbol": symbol, "error": "Failed to fetch historical prices", "historical_prices": []}

        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON response for historical prices {symbol}: {e}")
            return {"symbol": symbol, "error": "Invalid JSON response", "historical_prices": []}

        prices = data.get("price", [])
        logger.info(f"Successfully fetched {len(prices)} price records for {symbol}")
        return {"symbol": symbol, "historical_prices": prices}

    except Exception as e:
        logger.error(f"Unexpected error in fetch_historical_prices for {symbol}: {e}")
        return {"symbol": symbol, "error": str(e), "historical_prices": []}

def save_stock_data(symbol):
    """Save all stock data for a symbol with comprehensive error handling"""
    try:
        logger.info(f"Starting data collection for {symbol}")
        
        data = {
            "symbol": symbol,
            "timestamp": datetime.datetime.now().isoformat(),
            "factsheet": fetch_factsheet_selenium(symbol),
            "company_highlights": fetch_company_highlights(symbol),
            "rights_benefits": fetch_rights_benefits(symbol),
            "financial_statements": fetch_financial_statements(symbol),
            "historical_trading": fetch_historical_prices(symbol),
        }
        
        # Create data directory
        os.makedirs("data", exist_ok=True)
        
        # Save to JSON file
        filename = f"data/{symbol}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Successfully saved data for {symbol} to {filename}")
        return data

    except Exception as e:
        logger.error(f"Critical error saving data for {symbol}: {e}")
        return {"symbol": symbol, "error": f"Critical error: {str(e)}"}

def batch_scrape(symbols, delay=3):
    """Scrape multiple symbols with rate limiting"""
    results = {}
    failed_symbols = []
    
    logger.info(f"Starting batch scrape for {len(symbols)} symbols")
    
    for i, symbol in enumerate(symbols, 1):
        try:
            logger.info(f"Processing {symbol} ({i}/{len(symbols)})")
            result = save_stock_data(symbol)
            results[symbol] = result
            
            # Check if scraping was successful
            if "error" in result:
                failed_symbols.append(symbol)
                logger.warning(f"Failed to scrape {symbol}")
            else:
                logger.info(f"Successfully scraped {symbol}")
            
            # Rate limiting between symbols
            if i < len(symbols):
                logger.info(f"Waiting {delay} seconds before next symbol...")
                time.sleep(delay)
                
        except Exception as e:
            logger.error(f"Critical error processing {symbol}: {e}")
            failed_symbols.append(symbol)
            results[symbol] = {"symbol": symbol, "error": f"Critical error: {str(e)}"}
    
    logger.info(f"Batch scrape completed. Success: {len(symbols)-len(failed_symbols)}, Failed: {len(failed_symbols)}")
    if failed_symbols:
        logger.warning(f"Failed symbols: {failed_symbols}")
    
    return results, failed_symbols

if __name__ == "__main__":
    # Single symbol example
    symbol = "24CS"
    result = save_stock_data(symbol)
    
    # Multiple symbols example
    # symbols = ["24CS", "KBANK", "SCB", "PTT", "CPALL"]
    # results, failed = batch_scrape(symbols, delay=3)
    # print(f"Completed scraping. Failed symbols: {failed}")