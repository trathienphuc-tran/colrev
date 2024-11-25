from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service

chrome_options = Options()
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--headless')

service = Service(executable_path=r'/home/vscode/bin/chromedriver-linux64/chromedriver')
driver = webdriver.Chrome(options = chrome_options, service=service)
driver.get("http://www.python.org")
assert "Python" in driver.title
elem = driver.find_element(By.NAME, "q")
elem.clear()
elem.send_keys("pypi")
elem.send_keys(Keys.RETURN)
assert "No results found." not in driver.page_source
#driver.close()