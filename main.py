# fetch_factsheet 
import requests
from bs4 import BeautifulSoup
import json
import os
import re
import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

symbol = "24CS"
def fetch_factsheet(symbol):
    url = f"https://www.set.or.th/th/market/product/stock/quote/{symbol}/factsheet"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Bot/1.0)"
    }
    resp = requests.get(url, headers=headers)
    resp.encoding = 'utf-8'

    soup = BeautifulSoup(resp.text, "html.parser")
    
    data = {"symbol": symbol}

    # 1. Company Name
    company_name_tag = soup.select_one(".header-1")
    data["company_name"] = company_name_tag.text.strip() if company_name_tag else None

    # 2. Price & Market Cap
    price_tag = soup.select_one("div.quote-summary .price")
    data["price"] = float(price_tag.text.replace(",", "")) if price_tag else None

    market_cap_tag = soup.find("th", string="มูลค่าตลาด (ล้านบาท)")
    if market_cap_tag:
        market_cap_value = market_cap_tag.find_next_sibling("td").text.strip().replace(",", "")
        try:
            data["market_cap"] = float(market_cap_value) * 1e6  # ล้านบาท -> บาท
        except:
            data["market_cap"] = None
    else:
        data["market_cap"] = None

    # 3. Financial Ratios Section
    # (เช่น P/E, P/BV, Dividend Yield, EPS, ROE, Beta, etc.)
    ratios = {}
    ratio_table = soup.find("table", {"class": "table-info"})
    if ratio_table:
        for row in ratio_table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) == 2:
                key = cols[0].text.strip()
                val = cols[1].text.strip()
                try:
                    val = float(val.replace("%", "").replace(",", ""))
                except:
                    pass
                ratios[key] = val
    data["financial_ratios"] = ratios

    # 4. Dividend Info (จาก Factsheet มักจะมีบอก dividend yield และ dividend ล่าสุด)
    # ตัวอย่างดึงจาก ratios ที่มีคำว่า "Dividend"
    dividend_info = {}
    for k, v in ratios.items():
        if "Dividend" in k or "ปันผล" in k:
            dividend_info[k] = v
    data["dividend_info"] = dividend_info

    # 5. Price Range 52 Weeks
    price_52w = {}
    price_52w_tags = soup.select("table.table-info tr")
    for tr in price_52w_tags:
        tds = tr.find_all("td")
        if len(tds) == 2:
            label = tds[0].text.strip()
            val = tds[1].text.strip()
            if "สูงสุด 52 สัปดาห์" in label:
                price_52w["high_52w"] = float(val.replace(",", ""))
            elif "ต่ำสุด 52 สัปดาห์" in label:
                price_52w["low_52w"] = float(val.replace(",", ""))
    data["price_52w"] = price_52w

    # 6. Average Volume 10 Days
    avg_vol_tag = soup.find("th", string="ปริมาณซื้อขายเฉลี่ย 10 วัน (หุ้น)")
    if avg_vol_tag:
        avg_vol_val = avg_vol_tag.find_next_sibling("td").text.strip().replace(",", "")
        try:
            data["avg_volume_10d"] = int(avg_vol_val)
        except:
            data["avg_volume_10d"] = None

    return data

# fetch_company

def fetch_company_highlights(symbol):
    url = f"https://www.set.or.th/th/market/product/stock/quote/{symbol}/financial-statement/company-highlights"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers)
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
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            rows = table.find_all("tr")[1:]

            for row in rows:
                cols = [td.get_text(strip=True).replace(",", "") for td in row.find_all("td")]
                if len(cols) < 2:
                    continue
                try:
                    item = {
                        "year": int(cols[0]),
                        "revenue": float(cols[1]) if cols[1] else None,
                        "net_profit": float(cols[2]) if cols[2] else None,
                        "eps": float(cols[3]) if cols[3] else None,
                        "bvps": float(cols[4]) if cols[4] else None,
                        "roe": float(cols[5]) if cols[5] else None,
                        "net_profit_margin": float(cols[6]) if cols[6] else None,
                        "pe": float(cols[7]) if cols[7] else None,
                        "pbv": float(cols[8]) if cols[8] else None,
                    }
                    data["highlights"]["financials"].append(item)
                except:
                    continue

    return data
  
  
  # fetch_rights_and_benefits
def fetch_rights_benefits(symbol):
    url = f"https://www.set.or.th/api/set/company-rights-and-benefits/{symbol}?type=financial"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    res = requests.get(url, headers=headers)
    try:
        data = res.json()
    except Exception:
        # ถ้าไม่ใช่ json หรือ error ให้คืนค่าเปล่า
        return {
            "symbol": symbol,
            "dividends": []
        }

    # ดึงเฉพาะสิทธิ์ที่เป็น “เงินปันผล"
    dividend_data = []
    for item in data.get("data", []):
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

    result = {
        "symbol": symbol,
        "dividends": dividend_data
    }
    return result
  
# fetch_historical_prices

def fetch_historical_prices(symbol, months=60):
    url = "https://www.set.or.th/api/set/stock/price-chart"
    end_date = datetime.datetime.today()
    start_date = end_date - datetime.timedelta(days=30 * months)

    params = {
        "symbol": symbol,
        "type": "month",  # ใช้ "day", "month", หรือ "year" ได้
        "range": f"{start_date.strftime('%Y-%m-%d')}_{end_date.strftime('%Y-%m-%d')}"
    }

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    res = requests.get(url, params=params, headers=headers)
    try:
        data = res.json()
    except Exception:
        return {
            "symbol": symbol,
            "historical_prices": []
        }

    result = {
        "symbol": symbol,
        "historical_prices": data.get("price", [])
    }

    return result
  
# fetch_final_statement
def fetch_financial_statements(symbol):
    url = f"https://www.set.or.th/th/market/product/stock/quote/{symbol}/financial-statement/financial-position"
    headers = { "User-Agent": "Mozilla/5.0" }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, "html.parser")
    
    file_links = []

    # กรองเฉพาะลิงก์ที่มีชื่อ symbol ใน url หรือชื่อไฟล์
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if re.search(r"\.(pdf|xls|xlsx)$", href, re.IGNORECASE):
            if symbol.lower() in href.lower():
                file_url = href if href.startswith("http") else "https://www.set.or.th" + href
                file_name = file_url.split("/")[-1].lower()
                file_links.append({
                    "url": file_url,
                    "year": re.search(r"(20\d{2})", file_name).group(1) if re.search(r"(20\d{2})", file_name) else None,
                    "period": re.search(r"q[1-4]|y(?:early)?", file_name).group(0).upper() if re.search(r"q[1-4]|y(?:early)?", file_name) else "UNKNOWN",
                    "language": "th" if "th" in file_name else "en" if "en" in file_name else "unknown",
                    "type": file_url.split(".")[-1].upper()
                })

    return {
        "symbol": symbol,
        "financial_statements": file_links
    }


# save to json
def save_stock_data(symbol):
    data = {
        "symbol": symbol,
        "factsheet": fetch_factsheet(symbol),
        "company_highlights": fetch_company_highlights(symbol),
        "rights_benefits": fetch_rights_benefits(symbol),  # เปลี่ยนชื่อ key
        "financial_statements": fetch_financial_statements(symbol),
        "historical_trading": fetch_historical_prices(symbol),  # เปลี่ยนชื่อ key
    }
    os.makedirs("data", exist_ok=True)  # สร้างโฟลเดอร์ถ้ายังไม่มี
    with open(f"data/{symbol}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    save_stock_data(symbol)
    # หรือจะ print ข้อมูลออกหน้าจอด้วยก็ได้
    # print(json.dumps(fetch_factsheet(symbol), ensure_ascii=False, indent=2))

def fetch_factsheet_selenium(symbol):
    url = f"https://www.set.or.th/th/market/product/stock/quote/{symbol}/factsheet"
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    time.sleep(3)  # รอ JS โหลดข้อมูล

    soup = BeautifulSoup(driver.page_source, "html.parser")
    driver.quit()

    # ตัวอย่างการดึงข้อมูล
    company_name = soup.select_one("h1[class*=security-symbol]").text.strip() if soup.select_one("h1[class*=security-symbol]") else None
    price = soup.select_one("span[class*=last-price]").text.strip() if soup.select_one("span[class*=last-price]") else None
    market_cap = None
    for div in soup.find_all("div"):
        if div.text and "มูลค่าหลักทรัพย์ตามราคาตลาด" in div.text:
            market_cap = div.find_next("div").text.strip()
            break

    return {
        "symbol": symbol,
        "company_name": company_name,
        "price": price,
        "market_cap": market_cap
    }

print(fetch_factsheet_selenium("24CS"))

