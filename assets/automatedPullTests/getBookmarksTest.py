from AO3 import Session
import time
import pandas as pd
import getpass
import random

# ------------------------
# Create session
# ------------------------
password = getpass.getpass("Enter your AO3 password: ")

# Replace with your actual info
username = "willowphile"

# Create session
session = Session(username, password)

# ------------------------
# Get total bookmark pages
# ------------------------
# Clear any cached bookmarks
session._bookmarks = []

# Get total pages
max_retries = 5
retries = 0
while retries < max_retries:
    try:
        total_pages = session._bookmark_pages
        print(f"Total bookmark pages: {total_pages}")
        break  # success, exit retry loop
    except Exception as e:
        retries += 1
        wait = 5 * (2 ** retries) + random.uniform(0, 3)
        print(f"Failed to get pagination (attempt {retries}): {e}")
        if retries < max_retries:
            print(f"Retrying in {wait:.1f}s...")
            time.sleep(wait)
        else:
            print("Giving up on pagination after max retries.")
            total_pages = 1

# ------------------------
# Get all bookmark IDs
# ------------------------
# Load all pages
for page in range(1, total_pages + 1):
    print(f"Loading page {page}...")
    retries = 0
    while retries < 5:
        try:
            session._load_bookmarks(page=page)
            time.sleep(2 + random.uniform(0, 2))  # wait 2–4s between pages
            break  # success → move to next page
        except Exception as e:
            print(f"Error loading page {page} (attempt {retries+1}): {e}")
            retries += 1
            wait = 5 * (2 ** retries) + random.uniform(0, 3)
            print(f"Retrying in {wait:.1f}s...")
            time.sleep(wait)
    else:
        print(f"Failed to load page {page} after {retries} retries.")

# Get the full list
all_bookmarks = session._bookmarks

# Build DataFrame
df = pd.DataFrame([{"id": w.id, "title": w.title} for w in all_bookmarks])
print(df)

df.to_csv('allIds.csv')

# Debug save of the first page
try:
    soup = session.request(session._bookmarks_url.format(session.username, 1))
    with open("debug_bookmarks_page1.html", "w", encoding="utf-8") as f:
        f.write(str(soup))
except Exception as e:
    print("Failed to save debug HTML:", e) 
    
"""

# ------------------------------------------------
# Iterate through dataframe to retrieve fics
# ------------------------------------------------

# import test df from csv
df = pd.read_csv("testDf.csv")

print(df)

url = "https://archiveofourown.org/works/"

cssSelector = '#main > ul.work.navigation.actions > li.download > ul > li:nth-child(5) > a'
# document.querySelector('#main > ul.work.navigation.actions > li.download > ul > li:nth-child(5) > a').click()

""" 