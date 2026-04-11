import streamlit as st
import difflib
import urllib.request
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import time

#Variables
splitChars = r'(?<=[.!?])\s+|\n+'
#Set to true if you want to keep original site look, but adds a scroll bar
# When false, page still has css, burt is more plain and easier to compare
needStyles = False

#functions
def fetch(url):
    return urllib.request.urlopen(url).read()

def inline_css(html_bytes, base_url):
    soup = BeautifulSoup(html_bytes, "html.parser")

    #remove head if setting is enabled
    if needStyles == False:
        for tag in soup.find_all("header"):
            tag.decompose()
    # Remove content we dont want to display
    for tag in soup.find_all(["nav", "footer", "header", "h1", "h2", "h3","script"]):
        tag.decompose()
    for tag in soup.find_all(class_=re.compile(r'^(menu|skip-link|screen-reader-text|sidebar|toolbar|toc|nav)')):
        tag.decompose()
    for tag in soup.find_all(id=re.compile(r'^(sidebar|toc|nav)')):
        tag.decompose()
    for tag in soup.find_all(True):          # every tag
        for attr in ("alt", "title", "summary", "content", "property"):
            if attr in tag.attrs:
                del tag.attrs[attr]

    for link in soup.find_all("link", rel="stylesheet"):
        href = link.get("href")
        if not href:
            continue
        css_url = urljoin(base_url, href)
        try:
            css = fetch(css_url).decode("utf-8")
            style_tag = soup.new_tag("style")
            style_tag.string = css
            link.replace_with(style_tag)
        except Exception as e:
            print(f"Skipped {css_url}: {e}")
    return str(soup)

def get_unique_content(list1, list2):
    matcher = difflib.SequenceMatcher(None, list1, list2)
    unique1 = set()  # in list1 but not list2
    unique2 = set()  # in list2 but not list1
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'delete':    # only in list1
            unique1.update(list1[i1:i2])
        elif tag == 'insert':  # only in list2
            unique2.update(list2[j1:j2])
        elif tag == 'replace': # different in both
            unique1.update(list1[i1:i2])
            unique2.update(list2[j1:j2])
        # 'equal' blocks are shared, skip them
    
    return unique1, unique2

def normalize(text):
    return re.sub(r'^[.!?,;:\s]+|[.!?,;:\s]+$', '', text.strip().lower())

def addDiffStyles(stylizedHTML, diffs):
    filtered_diffs = sorted({d for d in diffs if len(d) > 15}, key=len, reverse=True)
    TAG = r'(?:<[^>]*>)*'
    
    for diff in filtered_diffs:
        #Regex by claude, copilot, and chatgpt, with some of my own modifications.
        diff = re.sub(r'\s+', ' ', diff).strip()
        
        # Step 1: escape the raw diff text
        pattern = re.escape(diff)
        
        # Step 2: insert TAG between every character of the escaped pattern
        # BUT we must treat multi-char escape sequences (like \() as single units
        # Split into tokens: escaped sequences (\X) or single chars
        tokens = re.findall(r'\\.|.', pattern)
        pattern = TAG.join(tokens)
        
        # Step 3: now apply semantic replacements on the joined pattern
        # Replace escaped space+TAG+escaped space sequences with whitespace pattern  
        pattern = pattern.replace(r'\ ' + TAG + r'\ ', r'\ ' + TAG + r'\s*' + TAG + r'\ ')
        # Simpler: just replace the escaped-space token
        pattern = pattern.replace(r'\ ', r'\s*' + TAG)
        
        # Fix up special characters
        pattern = pattern.replace(r'\&', r'(?:&amp;|&)')
        pattern = pattern.replace(r"\'", r"(?:&#39;|'|')")


        
        try:
            new_html = re.sub(
                pattern,
                r'<span class="diff" style="background-color: yellow">\g<0></span>',
                stylizedHTML,
                flags=re.IGNORECASE | re.DOTALL
            )
            stylizedHTML = new_html
        except re.error as e:
            print(f"Regex error for diff: {diff[:50]}... {e}")
            continue

    return stylizedHTML


st.set_page_config(layout="wide")
st.title("Book Diff Tool")

# Initialize step
if "step" not in st.session_state:
    st.session_state.step = 1

# STEP 1 — Ask for Link 1
if st.session_state.step == 1:
    link1 = st.text_input("Enter Link 1")
    #add button to auto fill links
    if st.button("Fill Test Links"):
        link1 = "https://ecampusontario.pressbooks.pub/orgbiochemsupplement/chapter/alkanes-alkenes-alkynes/"
        st.session_state.link1 = link1
        link2 = "https://boisestate.pressbooks.pub/chemistry/chapter/21-1-hydrocarbons/"
        st.session_state.link2 = link2
        st.session_state.step = 3
        st.rerun()

    if st.button("Next") and link1.strip():
        st.session_state.link1 = link1
        st.session_state.step = 2
        st.rerun()

# STEP 2 — Ask for Link 2
elif st.session_state.step == 2:
    st.write(f"Link 1 saved: {st.session_state.link1}")
    link2 = st.text_input("Enter Link 2")

    if st.button("Compare") and link2.strip():
        st.session_state.link2 = link2
        st.session_state.step = 3
        st.rerun()

# STEP 3 — Show results
elif st.session_state.step == 3:
    start = time.time()
    st.write("Comparing pages…")
    st.write("Link 1:", st.session_state.link1)
    st.write("Link 2:", st.session_state.link2)
    link1 = st.session_state.link1
    link2 = st.session_state.link2

    data = fetch(link1)
    soupifiedData = BeautifulSoup(data, "html.parser")
    displayedText = soupifiedData.get_text().lower()
    displayedList = re.split(splitChars, displayedText)
    displayStrip1 = [line.strip() for line in displayedList]


    data2 = fetch(link2)
    soupifiedData2 = BeautifulSoup(data2, "html.parser")
    displayedText2 = soupifiedData2.get_text().lower()
    displayedList2 = re.split(splitChars, displayedText2)
    displayStrip2 = [line.strip() for line in displayedList2]

    inlined1 = inline_css(data, link1)
    inlined2 = inline_css(data2, link2)


    # then replace your set subtraction with:
    unique1, unique2 = get_unique_content(displayStrip1, displayStrip2)
    diffs1 = {d.strip().lower() for d in unique1 if len(d.strip()) > 2}
    diffs2 = {d.strip().lower() for d in unique2 if len(d.strip()) > 2}


    highlighted1 = addDiffStyles(inlined1, diffs1)
    highlighted2 = addDiffStyles(inlined2, diffs2)


    highlighted_html = open("template.html", "r", encoding="utf-8").read()
    highlighted_html = highlighted_html.replace("{{page1}}", highlighted1)
    highlighted_html = highlighted_html.replace("{{page2}}", highlighted2)

    st.components.v1.html(highlighted_html, scrolling=True, height=1500)
    st.write(f"Time taken: {time.time() - start:.2f} seconds")
    if st.button("Reset"):
        st.session_state.step = 1
        st.rerun()
