from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time # อาจจะใช้สำหรับ time.sleep ถ้าต้องการรอแบบง่ายๆ

# 1. กำหนดค่า WebDriver
# ถ้า ChromeDriver อยู่ใน PATH อยู่แล้ว ก็ไม่ต้องระบุ executable_path
# ถ้าไม่ได้อยู่ใน PATH ให้ระบุพาธเต็มของ ChromeDriver.exe/chromedriver
# driver = webdriver.Chrome(executable_path='/path/to/chromedriver') # ตัวอย่าง
driver = webdriver.Chrome() # สำหรับกรณีที่ ChromeDriver อยู่ใน PATH แล้ว

url = "https://www.set.or.th/th/market/product/stock/quote/24CS/factsheet"
driver.get(url)

# 2. รอให้ element ที่ต้องการโหลดจนเสร็จ
# นี่คือส่วนสำคัญ: เราจะรอจนกว่า tag h1 ที่มี class "company-name" จะปรากฏและมีข้อความที่ไม่ใช่แค่ "-"
try:
    # รอ 10 วินาที เพื่อให้ h1 ที่มี class company-name โหลดเสร็จและมีข้อความที่ต้องการ
    # (หรืออย่างน้อยก็ไม่ใช่แค่ "-")
    # เราใช้ EC.text_to_be_present_in_element เพื่อให้แน่ใจว่ามีข้อความจริงๆ ไม่ใช่แค่โครงเปล่า
    WebDriverWait(driver, 10).until(
        EC.text_to_be_present_in_element((By.CLASS_NAME, "company-name"), "บริษัท")
    )
    # หรือถ้ามั่นใจว่ามันจะโหลดเร็ว อาจจะแค่รอให้ element ปรากฏ
    # WebDriverWait(driver, 10).until(
    #     EC.presence_of_element_located((By.CLASS_NAME, "company-name"))
    # )

except Exception as e:
    print(f"Error waiting for element: {e}")
    # ถ้าหานานแล้วยังไม่เจอ อาจจะต้องปรับเงื่อนไขการรอ หรือ URL/Selector ผิด

# 3. ดึง HTML ที่ render แล้วจาก Selenium
rendered_html = driver.page_source

# 4. ใช้ BeautifulSoup ประมวลผล HTML นั้น
soup = BeautifulSoup(rendered_html, "html.parser")

# 5. ดึงข้อมูลเหมือนเดิม โดยใช้ .strip()
symbol_name_tag = soup.find('div', class_="company-code")
company_name_tag = soup.find('h1', class_="company-name")

symbol_name = symbol_name_tag.text.strip() if symbol_name_tag else "N/A"
company_name = company_name_tag.text.strip() if company_name_tag else "N/A"


print(symbol_name, company_name)

# ปิดเบราว์เซอร์เมื่อเสร็จสิ้น
driver.quit()