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
states = ['Texas']

known_dances = {
    'New York': ['Flow Fridays']
}


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
        ret = [soup.body.get_text(separator='---', strip=True)]
    except Exception as e:
        print(f"Error getting text for {url}: {e}")
        raise e
    if recursive:
        links = filter_domain_links_for_socials([a['href'] for a in soup.find_all('a', href=True)
                                                 if get_domain(a['href']) == domain])
        links_formatted = '\n\t' + '\n\t'.join(links)
        print(f"Found additional sub-pages to search: {links_formatted}")
        for link in links:
            ret.extend(get_page_html(link, False))
    return ret


def filter_domain_links_for_socials(links: List[str]):
    system_msg = """
    You are a master of webpage navigation. 
    When given a list of links, you will return the links matching the prompt provided.
    After explaining your reasoning write on a new line STARTING_OUTPUT and output links starting on \
    the next line.
    EX: If you are given 
    http://a.com,http://b.com,http://c.com
    and you are asked to return links to everywhere but c.com, you will return
    {Reasoning}...
    STARTING_OUTPUT
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
    response: str = raw["choices"][0]["message"]["content"].split('STARTING_OUTPUT\n')[1]
    return response.split(',')


def get_socials_from_page(webpage, state, source_url):
    if state in known_dances:
        state_dances = known_dances[state]
    else:
        state_dances = []
    # Define the system message
    system_msg = """
    You are great at parsing website output from beautiful soup. 
    The separator used to concatenate text is "---".
    You are great at generating CSVs rows; you do not output headings.
    Based on the prompt about the website, you will generate a CSV output.
    You explain your reasoning for rows generated based on quotes from the website text.
    After explaining your reasoning write on a new line STARTING_OUTPUT and output rows starting on the next line.
    If are no rows to output, write NO_OUTPUT instead of STARTING_OUTPUT. Do not write both at the same time.
    """

    # Define the user message
    user_msg = f"""
    Below is the output of a website about West Coast Swing that may contain information about social dances.
    We want all the social dances we can find with an organizing group or name of event, location, and day of the week.
    If we do not know either of those pieces of information, do not add a row.
    Information about the lesson (EX Advanced, Beginner, etc) should not be included.
    The first column is the organizing group or name of the event (there's generally only one or the other), \
    the second is the name of the location, the third is the day of the week. 
    Only output the day of the week (EX Monday), not which days of the month (EX: Every 3rd Monday).
    If there is both an organizing group and name of event, only output a single row using the organizing group.
    If the name of the location is not present, leave a ?
    The known organizers in this area are: {','.join(state_dances)}. \
    There are likely to be additional organizers we don't know about.
    If there is no organizer, treat the name of the event as the organizer.
    If there is no day of the week, but there is a date (EX October 7) put the date in the form MM/DD/YY instead.\
    If there is no year EXPLICITLY stated, output the date in terms of MM/DD.
    If two events are on the same day of the week and have similar names, assume they are referring to the same event.
    In the world of west coast swing there are weekend long events (generally Thurs/Fri to Sunday). \
    Do not include these or any social dancing that occurs as a part of this event. 
    Samples (DO NOT USE THESE IN OUTPUT):
    "Every first Saturday, join the Gotham Swing Club at Best Dance Studio, for their monthly dance." ->\
     Gotham Swing, Best Dance Studio, Saturday
    "Tuesday Night West Coast Swing The Electric Belle in Stovehouse @ 6:30 PM | Social Dancing @ 7:15 PM"\
     -> ?, Electric Belle, Tuesday 
    Negative Examples: 
    Page:
    {webpage}
    """

    # Create a dataset using GPT
    raw = openai.ChatCompletion.create(model="gpt-4",
                                       messages=[{"role": "system", "content": system_msg},
                                                 {"role": "user", "content": user_msg}])
    print(f'get_socials_from_page\n{raw["choices"][0]["message"]["content"]}')
    res = raw["choices"][0]["message"]["content"].split('STARTING_OUTPUT\n')
    if len(res) != 2:
        return []
    else:
        response = raw["choices"][0]["message"]["content"].split('STARTING_OUTPUT\n')[1]
        return [f"{state},{raw_row},{source_url}" for raw_row in response.splitlines()]


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


def remove_duplicates(csv_string):
    system_msg = """
    You are great at removing duplicate rows from CSVs. People give you CSVs with some prompt, and you answer the \
    prompt, returning a CSV at the end with removed duplicate rows. Every time you remove a row, you explain your \
    logic, pointing at the row that it is a duplicate of.
    """
    user_msg = f"""
    Below is a CSV of west coast swing socials. Columns are: State, Organizer, Location, Day of Week, Source URL. \
    We consider something a duplicate if an event is run by the same organizer on the same day. 
    Sometimes, we may have organizer names typed differently (EX: MDJ WCS, MDJ, Millenium Dance Jam, Lori Brizzi's \
    MDJ) are all the same. In our output row, we want to use the shortest organizer name.
    If we don't know information, we may put a ? or a MANUAL_INTERVENTION_NEEDED token. If rows are \
    duplicated, we want to make sure to combine data from all rows to maximize the amount of data we have.
    After explaining your reasoning write on a new line STARTING_OUTPUT and output the filtered CSV starting on \
    the next line.
    CSV:
    {csv_string}
    """
    raw = openai.ChatCompletion.create(model="gpt-4",
                                       messages=[{"role": "system", "content": system_msg},
                                                 {"role": "user", "content": user_msg}])
    print(f'get_socials_from_page\n{raw["choices"][0]["message"]["content"]}')
    res = raw["choices"][0]["message"]["content"].split('STARTING_OUTPUT\n')
    if len(res) == 1:
        return []
    else:
        return raw["choices"][0]["message"]["content"].split('STARTING_OUTPUT\n')[1]


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
            print(f'Visiting {website}')
            visited_domains.add(domain)
        try:
            contents = get_page_html(website, False)
        except Exception as e:
            print(f"Error processing link {website} for state {state}: {e}")
            continue

        for html_content in contents:
            try:
                socials_to_add = get_socials_from_page(html_content, state, website)
                if len(socials_to_add) > 0:
                    state_socials.extend(socials_to_add)
            except Exception as e:
                print(f"Error processing contents {contents} for state {state}: {e}")
    output = remove_duplicates('\n'.join(state_socials))
    with open(file_name, 'w') as f:
        f.write(output)


def main():
    for state in states:
        process_state(state)
    driver.quit()


main()
