import os
import re

from typing import List

import openai
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from bs4 import BeautifulSoup

import pandas as pd

openai.api_key = os.environ['OPENAI']

BLOCKED_DOMAINS = ['facebook', 'fredastaire', 'canadianswingchampions', 'xdance', 'google',
                   'accessdance', 'wikipedia', 'dancingfads', 'youtube', 'instagram', 'meetup']
MAX_LINKS = 5

options = Options()
options.headless = True
driver = webdriver.Chrome(options=options)


# Define the structure of a Social
class Social:
    def __init__(self, raw_row: str, state: str, source_url: str):
        columns = raw_row.split(',')
        self.state = state
        self.title = columns[0]
        self.source_url = source_url
        self.day_of_week = columns[1]

    def to_string(self):
        print(f"{self.state}, {self.title}, {self.day_of_week}, {self.source_url}")

    def to_dict(self):
        return {
            "state": self.state,
            "day_of_week": self.day_of_week,
            "title": self.title,
            "source_url": self.source_url
        }


# List of US states
states = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming", "Washington DC"
]
states = ['New York']


def wait_for_element(by, value, timeout=10):
    return WebDriverWait(driver, timeout).until(ec.presence_of_element_located((by, value)))


def get_page_html(url, recursive: bool = True) -> List[str]:
    domain = get_domain(url)
    try:
        driver.get(url)

        # An example: wait for body tag to ensure page is loaded
        wait_for_element(By.TAG_NAME, 'body')

        # Parse page source with BeautifulSoup
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        ret = [soup.body.get_text(separator=' ', strip=True)]
    except Exception as e:
        print(f"Error getting text for {url}: {e}")
        raise e
    if recursive:
        links = filter_domain_links_for_socials([a['href'] for a in soup.find_all('a', href=True)
                                                 if get_domain(a['href']) == domain])
        links_formatted = '\n' + '\n\t'.join(links)
        print(f"Found additional sub-pages to search: {links_formatted}")
        for link in links:
            ret.extend(get_page_html(link, False))
    return ret


def filter_domain_links_for_socials(links: List[str]):
    system_msg = """
    You are a master of webpage navigation. 
    When given a list of links, you will return the links matching the prompt provided.
    You will only return a comma separated list of links. 
    EX: If you are given 
    http://a.com,http://b.com,http://c.com
    and you are asked to return links to everywhere but c.com, you will return
    http://a.com,http://b.com
    """
    user_msg = f"""
    Return the top 3 links that are likely to contain information about weekly social dances.
    Examples (DO NOT INCLUDE THESE IN OUTPUT):
    https://superwesties.com/tuesday-night-wcs/
    https://www.azwestcoastswing.com/local-dances
    https://dancemagicproduction.com/fridays/
    
    Real Links:
    {','.join(links)}
    """
    raw = openai.ChatCompletion.create(model="gpt-4",
                                       messages=[{"role": "system", "content": system_msg},
                                                 {"role": "user", "content": user_msg}])
    response: str = raw["choices"][0]["message"]["content"]
    return response.split(',')


def get_socials_from_page(webpage, state, source_url):
    # Define the system message
    system_msg = """
    You are a CSV generator. You do nothing but generate CSVs. All of your ouptuts are 
    a comma separated list of strings to represent rows and newlines. 
    If you output any other text, I will be sad and you do not want me sad.
    You do not print header rows, only data rows.
    """

    # Define the user message
    user_msg = f"""
    Below is the output of a website about West Coast Swing. 
    Parse the site and output a CSV with all the known West Coast Swing socials. 
    If there are no socials, return no text. If you find any socials, output rows of the form
    Title, DayOfWeek
    Samples (DO NOT USE THESE IN OUTPUT):
    "Every first Saturday, join the Gotham Swing Club for their monthly dance." -> Gotham Swing, Saturday
    "Tuesday Night West Coast Swing The Electric Belle in Stovehouse @ 6:30 PM | Social Dancing @ 7:15 PM"\
     -> Electric Belle in StoveHouse, Tuesday 
    Page:
    {webpage}
    """

    # Create a dataset using GPT
    raw = openai.ChatCompletion.create(model="gpt-4",
                                       messages=[{"role": "system", "content": system_msg},
                                                 {"role": "user", "content": user_msg}])
    response = raw["choices"][0]["message"]["content"]
    return [Social(raw_row, state, source_url)
            for raw_row in response.splitlines()]


def filter_blocked_domains(urls, blocked_domains):
    filtered_urls = []
    for url in urls:
        if url is None:
            continue
        blocked = False
        for domain in blocked_domains:
            if domain in url:
                blocked = True
                break
        if not blocked:
            filtered_urls.append(url)
    return filtered_urls


def get_domain(url):
    match = re.search(r'https?://([^/]+)/', url)
    if match:
        return match.group(1)
    else:
        return None


def process_state(state):
    file_name = f'socials/{state}_socials.csv'
    visited_domains = set()
    if os.path.isfile(file_name):
        print(f"Skipping State: {state}")
        return
    print(f"Processing State: {state}")
    state_socials = []
    search_url = f'https://www.google.com/search?q=west+coast+swing+socials+in+{state}'
    driver.get(search_url)

    # Wait for search results
    wait_for_element(By.CSS_SELECTOR, 'h3')

    # Get links from Google
    results = driver.find_elements(By.CSS_SELECTOR, 'h3')

    google_links = filter_blocked_domains(
        [result.find_element(By.XPATH, '..').get_attribute('href') for result in results], BLOCKED_DOMAINS)[:MAX_LINKS]
    for website in google_links:
        domain = get_domain(website)
        if domain in visited_domains:
            print(f"Skipping Website {website}")
            continue
        else:
            visited_domains.add(domain)
        try:
            contents = get_page_html(website)
            for html_content in contents:
                socials_to_add = get_socials_from_page(html_content, state, website)
                state_socials.extend(socials_to_add)
        except Exception as e:
            print(f"Error processing link {website} for state {state}: {e}")
    df = pd.DataFrame([social.to_dict() for social in state_socials])
    df.to_csv(file_name, index=False)


def main():
    for state in states:
        process_state(state)
    driver.quit()


main()
