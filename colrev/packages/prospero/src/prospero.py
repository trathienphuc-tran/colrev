#! /usr/bin/env python
"""SearchSource: Prospero"""
from pydantic import Field
import zope.interface
import colrev.loader
import colrev.loader.load_utils
import colrev.ops
import colrev.ops.load
import colrev.package_manager.interfaces
import colrev.package_manager.package_manager
import colrev.package_manager.package_settings
from colrev.constants import SearchType
from colrev.constants import SearchSourceHeuristicStatus
from colrev.settings import SearchSource
from colrev.ops.search import Search
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bwriter import BibTexWriter
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException

""""
from pydantic import Field
import json
from pathlib import Path
from colrev.ops.search import Search
chrome_options = Options()
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--headless')
"""

@zope.interface.implementer(colrev.package_manager.interfaces.SearchSourceInterface)
class ProsperoSearchSource:
    """Prospero Search Source for retrieving protocol data"""

    # Default settings and attributes for the source
    settings_class = colrev.package_manager.package_settings.DefaultSourceSettings
    endpoint = "colrev.prospero"
    source_identifier = "url"
    search_types = [SearchType.API]
    heuristic_status = SearchSourceHeuristicStatus.supported
    ci_supported: bool = Field(default=True)
    db_url = "https://www.crd.york.ac.uk/prospero/"

    """"
    def __init__(
        self, *, source_operation: colrev.process.operation.Operation, settings: dict
    ) -> None:
        self.search_source = self.settings_class(**settings)
        self.review_manager = source_operation.review_manager
        self.operation = source_operation
   """

    @classmethod
    def add_endpoint(
        cls,
        operation: Search,
        params: str,
    ) -> SearchSource:
        """Adds Prospero as a search source endpoint"""

        # Parse parameters into a dictionary
        params_dict = {}
        if params:
            if params.startswith("http"):  # Handle URL-based parameters
                params_dict = {"url": params}
            else:  # Handle key-value parameter strings
                for item in params.split(";"):
                    if "=" in item:
                        key, value = item.split("=", 1)  # Only split on the first '='
                        params_dict[key] = value
                    else:
                        raise ValueError(f"Invalid parameter format: {item}")

        # Generate a unique filename for storing Prospero search results
        # Keep the filename local to the prospero directory but simulate the required prefix
        filename = f"data/search/{operation.get_unique_filename(file_path_string='prospero_results')}"

        # Create the SearchSource object
        search_source = SearchSource(
            endpoint=cls.endpoint,
            filename=filename,
            search_type=SearchType.API,
            search_parameters=params_dict,
            comment="Search source for Prospero protocols",
        )

        # Register the search source
        operation.add_source_and_search(search_source)
        return search_source
    
    """"
    def _load_bib(self) -> dict: 
        records = colrev.loader.load_utils.load(
            filename = self.search_source.filename,
            logger = self.review_manager.logger,
            unique_id_field = "ID",
        )
        return records

    def load(self,load_operation: colrev.ops.load.Load) -> dict:
        \"\"\"Load the records from the SearchSource file\"\"\"
        if self.search_source.filename.suffix == ".bib":
            return self._load_bib()
        
        raise NotImplementedError
    """
    
    def get_search_word(self):
        """Retrieve the search word for the query."""
        if hasattr(self, "search_word") and self.search_word is not None:
            return self.search_word
        try:
            self.search_word = self.search_source.search_parameters.get("query", "cancer1")
        except AttributeError:
            user_input = input("Enter your search query (default: cancer1): ").strip()
            self.search_word = user_input if user_input else "cancer1"
        return self.search_word
    
    def search(self, rerun: bool) -> None:
        print("Starting search method...", flush=True)
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--remote-debugging-port=9222')

        driver = webdriver.Chrome(options=chrome_options)

        try:
            # Navigate to Prospero homepage and search
            driver.get("https://www.crd.york.ac.uk/prospero/")
            driver.implicitly_wait(5)
            assert "PROSPERO" in driver.title

            search_word = self.get_search_word()
            search_bar = driver.find_element(By.ID, "txtSearch")
            search_bar.clear()
            search_bar.send_keys(search_word)
            search_bar.send_keys(Keys.RETURN)

            # Wait for results or no results
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//table[@id='myDataTable']"))
                )
            except TimeoutException:
                print("No results found for this query.")
                return

            matches = driver.find_element(By.XPATH, "//table[@id='myDataTable']")
            rows = matches.find_elements(By.XPATH, ".//tr[@class='myDataTableRow']")
            # Remove header row if present
            if rows and rows[0].find_elements(By.XPATH, ".//th"):
                rows.pop(0)

            total_rows = len(rows)
            if total_rows == 0:
                print("No results found for this query.")
                return

            print(f"Found {total_rows} element(s)")

            # collect record IDs and basic info
            record_ids = []
            registered_dates_array = []
            titles_array = []
            review_status_array = []

            for i, row in enumerate(rows):
                tds = row.find_elements(By.XPATH, "./td")
                if len(tds) < 5:
                    print(f"Row {i} does not have enough columns.")
                    registered_dates_array.append("N/A")
                    titles_array.append("N/A")
                    review_status_array.append("N/A")
                    record_ids.append(None)
                    continue

                registered_date = tds[1].text.strip()
                title = tds[2].text.strip()
                review_status = tds[4].text.strip()

                registered_dates_array.append(registered_date)
                titles_array.append(title)
                review_status_array.append(review_status)

                checkbox = tds[0].find_element(By.XPATH, ".//input[@type='checkbox']")
                record_id = checkbox.get_attribute("data-checkid")
                record_ids.append(record_id)

            # for each record, load detail page and extract authors/language
            language_array = []
            authors_array = []
            for i, record_id in enumerate(record_ids):
                if record_id is None:
                    # Already handled these as N/A
                    language_array.append("N/A")
                    authors_array.append("N/A")
                    continue

                detail_url = f"https://www.crd.york.ac.uk/prospero/display_record.php?RecordID={record_id}"
                driver.get(detail_url)

                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.XPATH, "//div[@id='documentfields']"))
                    )
                    # Extract language
                    try:
                        WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.XPATH, "//h1[text()='Language']"))
                        )
                        language_paragraph = driver.find_element(By.XPATH, "//h1[text()='Language']/following-sibling::p[1]")
                        language_details = language_paragraph.text.strip()
                    except (TimeoutException, NoSuchElementException):
                        language_details = "N/A"

                    # Extract authors
                    try:
                        authors_div = driver.find_element(By.ID, "documenttitlesauthor")
                        authors_text = authors_div.text.strip()
                        authors_details = authors_text if authors_text else "N/A"
                    except NoSuchElementException:
                        authors_details = "N/A"
                except TimeoutException:
                    language_details = "N/A"
                    authors_details = "N/A"

                language_array.append(language_details)
                authors_array.append(authors_details)
                print(f"Row {i}: {titles_array[i]}, Language: {language_details}, Authors: {authors_details}", flush=True)

            # Print summary
            print("Registered Dates:")
            for d in registered_dates_array:
                print(d)
            print("Titles:")
            for t in titles_array:
                print(t)
            print("Review status:")
            for r in review_status_array:
                print(r)
            print("Language Details:")
            for l in language_array:
                print(l)
            print("Authors:")
            for a in authors_array:
                print(a)

            print("Done.", flush=True)

        finally:
            driver.quit()


        """
        def search(self, rerun: bool) -> None:

        \"\"\"Run a search on Prospero\"\"\"

        driver = webdriver.Chrome(options = chrome_options)
        driver.get("https://www.crd.york.ac.uk/prospero/")
        driver.implicitly_wait(5)
        print(driver.title) #browser opened properly
        assert "PROSPERO" in driver.title

        search_bar = driver.find_element(By.ID, "txtSearch")
        search_bar.clear()
        search_bar.send_keys("inverted-T") #TODO: keyword input from user
        search_bar.send_keys(Keys.RETURN)
        print(driver.current_url) #browser navigated to search results web page successfully

        matches = driver.find_element(By.XPATH, "//table[@id='myDataTable']")
        matches1 = matches.find_elements(By.XPATH, "//tr[@class='myDataTableRow']")
        matches1.pop(0)
        print(matches1)

        #validate that matches are not empty
        if not matches1:  # This evaluates to True if the list is empty
            print("No elements found")
        else:
            print(f"Found {len(matches1)} elements")

        #TODO: handle stale element exception
        def retry_find_elem(web_elem: WebElement, byXpath: str) -> bool:
            result = False
            attempts = 0
            while(attempts < 3):
                try:
                    web_elem.find_element(By.XPATH, byXpath)
                    result = True
                except StaleElementReferenceException:
                    attempts += 1
            return result 

        #create empty array for articles' data
        registered_date = []
        title =[]
        review_status = []
        registered_dates_array = []
        titles_array = []
        review_status_array = []

        registered_date_elem = None
        title_elem = None
        review_status_elem = None
        
        matches1 = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.XPATH, "//table[@id='myDataTable']//tr[@class='myDataTableRow']")))

        for row in matches1:
            try:
                registered_date = row.find_element(By.XPATH, "./td[2]").text
                registered_dates_array.append(registered_date)
                title = row.find_element(By.XPATH, "./td[3]").text
                titles_array.append(title)
                review_status = row.find_element(By.XPATH, "./td[5]").text
                registered_dates_array.append(review_status)
            except Exception as e:
                print(f"Error extracting content for a row: {e}")

        print("Registered Dates:")
        for date in registered_dates_array:
            print(date)

        print("Titles: ")
        for titles in titles_array:
            print(titles)

        print("Review status: ")
        for review in review_status_array:
            print(review)
        
        #extract register date, title and review status of each paper into arrays
        for match in matches:
            if retry_find_elem(match,'./td[2]'):
                registered_date.append(match.find_element(By.XPATH, './td[2]').text)
            else:
                registered_date_elem = match.find_element(By.XPATH, './td[2]')
                registered_date.append(registered_date_elem.text)
            if retry_find_elem(match,'./td[3]'):
                title.append(match.find_element(By.XPATH, './td[3]').text)    
            else:
                title_elem = match.find_element(By.XPATH, './td[3]')
                title.append(title_elem.text)
            if retry_find_elem(match, '.td[5]'):
                review_status.append(match.find_element(By.XPATH, './td[5]').text)
            else:
                review_status_elem = match.find_element(By.XPATH, './td[5]')
                review_status.append(review_status_elem.text)
    
                
        print(registered_date)
        print(title)
        print(review_status)


        #assert "No results found." not in driver.page_source
        driver.close()
    search(self=1,rerun=bool)



    if __name__ == "__main__":
    # Mock a Search operation
    class MockSearchOperation:
        def get_unique_filename(self, file_path_string: str) -> str:
            return f"{file_path_string}.json"

        def add_source_and_search(self, search_source):
            print(f"Search source added: {search_source}")

    # Create a test case for add_endpoint()
    search_op = MockSearchOperation()
    params = "url=https://www.crd.york.ac.uk/prospero/?search=cancer"

    # Call add_endpoint
    try:
        endpoint = ProsperoSearchSource.add_endpoint(search_op, params)
        print(f"Generated Search Source: {endpoint}")
    except ValueError as e:
        print(f"Error in add_endpoint: {e}")
     # Test the load method
    try:
        prospero_source = ProsperoSearchSource()
        filename = Path("colrev/packages/prospero/bin/prospero_results.json")
        loaded_data = prospero_source.load(filename)
        print(f"Loaded Data: {loaded_data}")
    except Exception as e:
        print(f"Error in load: {e}")
        """
        
    def prep_link_md(self, prep_operation, record, save_feed=True, timeout=10):
        """Given a record with ID, fetch authors and language from Prospero."""
        record_id = record.get('ID')
        if not record_id:
            print("No ID provided in record, cannot link masterdata.")
            return record

        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--remote-debugging-port=9222')

        driver = webdriver.Chrome(options=chrome_options)
        detail_url = f"https://www.crd.york.ac.uk/prospero/display_record.php?RecordID={record_id}"
        try:
            driver.get(detail_url)
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, "//div[@id='documentfields']"))
            )

            # Extract language
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//h1[text()='Language']"))
                )
                language_paragraph = driver.find_element(By.XPATH, "//h1[text()='Language']/following-sibling::p[1]")
                record['language'] = language_paragraph.text.strip()
            except (TimeoutException, NoSuchElementException):
                record['language'] = "N/A"

            # Extract authors
            try:
                authors_div = driver.find_element(By.ID, "documenttitlesauthor")
                authors_text = authors_div.text.strip()
                record['authors'] = authors_text if authors_text else "N/A"
            except NoSuchElementException:
                record['authors'] = "N/A"

            print(f"Masterdata linked for ID {record_id}: Language={record['language']}, Authors={record['authors']}")

            if save_feed:
                print("Record updated and would be saved to feed.")
        except TimeoutException:
            print(f"Timeout while linking masterdata for ID {record_id}")
        finally:
            driver.quit()

        return record

    def prepare(self, record, source):
        """Map fields to standardized fields."""
        field_mapping = {
            'title': 'article_title',
            'registered_date': 'registration_date',
            'review_status': 'status',
            'language': 'record_language',
            'authors': 'author_list',
        }
        for original_field, standard_field in field_mapping.items():
            if original_field in record:
                record[standard_field] = record.pop(original_field)
    @property
    def heuristic_status(self) -> SearchSourceHeuristicStatus:
        return self.__class__.heuristic_status

    @property
    def search_types(self):
        return self.__class__.search_types

    @property
    def settings_class(self):
        return self.__class__.settings_class

    @property
    def source_identifier(self):
        return self.__class__.source_identifier

if __name__ == "__main__":
    prospero_source = ProsperoSearchSource()
    prospero_source.search(rerun=False)