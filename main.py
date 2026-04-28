'''
github: Mitchellmwf - Book-Diff-Live

This streamlit application allows users to input two URLs, fetches the content of those pages, and highlights the unique content on each page. It uses BeautifulSoup to parse the HTML and difflib to find differences in the text content. The application also provides an option to keep or remove original styles from the pages for easier comparison. Users can also manually input HTML for comparison instead of URLs.

'''
import streamlit as st
import difflib
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import time
import cloudscraper

# Set to true to enable test links and auto-fill 
testMode = False

#Variables
splitChars = r'(?<=[.!?])\s+|\n+'

#Set to true if you want to keep original site look, but adds a scroll bar, when false, page still has css, burt is more plain and easier to compare
global needStyles
needStyles = st.session_state.needStyles if "needStyles" in st.session_state else True


#     functions

# This function uses the cloudscraper library to fetch the content of a URL while bypassing Cloudflare protections. It returns the raw HTML content as bytes.
def fetch(url):
    return cloudscraper.get(url).content

# This function takes raw HTML bytes and a base URL, parses the HTML using BeautifulSoup, and inlines any linked CSS stylesheets. It also removes certain elements (like nav, footer, header) and attributes that are not needed for comparison. It then returns the styled HTML as a string.
def inline_css(html_bytes, base_url):
    soup = BeautifulSoup(html_bytes, "html.parser")

    #remove head if styling setting is enabled
    if needStyles == False:
        for tag in soup.find_all("head"):
            tag.decompose()
    # Remove content we dont want to display
    for tag in soup.find_all(["nav", "footer", "header"]):
        tag.decompose()
    for tag in soup.find_all(class_=re.compile(r'^(menu|skip-link|screen-reader-text|sidebar|toolbar|toc|nav)')):
        tag.decompose()
    for tag in soup.find_all(id=re.compile(r'^(sidebar|toc|nav)')):
        tag.decompose()
    for tag in soup.find_all(True):          # every tag
        for attr in ("alt", "title", "summary", "content", "property"):
            if attr in tag.attrs:
                del tag.attrs[attr]

    if base_url:
        # Add css styles into html as style tags, so the original page look is preserved
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

# This program takes two lists of strings and finds the differences between them with difflib. It then returns the differences as two sets: one for items unique to the first list and one for items unique to the second list.
def get_unique_content(list1, list2):
    matcher = difflib.SequenceMatcher(None, list1, list2)
    unique1 = set()  # in list1 but not list2
    unique2 = set()  # in list2 but not list1
    
    # The get_opcodes() method returns a list of 5-tuples describing how to turn list1 into list2. Each tuple has the form (tag, i1, i2, j1, j2) where:
    # - tag is one of 'replace', 'delete', 'insert', or 'equal'
    # - i1, i2 are the start and end indices in list1
    # - j1, j2 are the start and end indices in list2
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

# Function to check if URL is valid and accessible
def checkURL(url):
    if url is None or not re.match(r'^https?://', url):
        return False

    try:
        response = cloudscraper.get(url)
        return response.status_code == 200
    except Exception:
        return False

# Function to get status code or error message for a URL
def urlResponse(url):
    try:
        response = cloudscraper.get(url)
        return f"Status code: {response.status_code}"
    except Exception as e:
        return str(e)

# This function takes a text string and normalizes it by stripping leading/trailing whitespace, converting to lowercase, and removing certain punctuation characters from the start and end. This helps ensure that minor formatting differences don't prevent matching of similar content.
def normalize(text):
    return re.sub(r'^[.!?,;:\s]+|[.!?,;:\s]+$', '', text.strip().lower())

# This function takes the stylized HTML from the inline_css function and a set of differences (from the get_unique_content function) and adds styled spans around the differences in the HTML. It uses regex to find the differences in the HTML while allowing for variations in whitespace and certain characters. It returns the modified HTML with differences highlighted.
def addDiffStyles(stylizedHTML, diffs):
    filtered_diffs = sorted({d for d in diffs if len(d) > 15}, key=len, reverse=True)
    TAG = r'(?:<[^>]*>)*'
    
    for diff in filtered_diffs:
        #Regex by claude, copilot, and chatgpt, with some of my own modifications.
        diff = re.sub(r'\s+', ' ', diff).strip()
        
        # Escape the diff for regex
        pattern = re.escape(diff)
        
        # Split the pattern into tokens of either escaped characters or normal characters, and join with a regex that allows for HTML tags in between. This allows us to match the diff even if there are HTML tags inside it. (Catches bold, italics, links, etc)
        tokens = re.findall(r'\\.|.', pattern)
        pattern = TAG.join(tokens)
        
        pattern = pattern.replace(r'\ ' + TAG + r'\ ', r'\ ' + TAG + r'\s*' + TAG + r'\ ')
        pattern = pattern.replace(r'\ ', r'\s*' + TAG)
        
        # Fix up special characters
        pattern = pattern.replace(r'\&', r'(?:&amp;|&)')
        pattern = pattern.replace(r"\'", r"(?:&#39;|'|')")
        
        # Add a styled span around the matched diff in the HTML. The regex flags allow for case-insensitive matching and dot matches newlines. 
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

#    Streamlit UI and initialization
st.set_page_config(layout="wide")
st.title("HTML difference highlighter")
cloudscraper = cloudscraper.create_scraper()

# Initialize step which controls the flow of the application
if "step" not in st.session_state:
    st.session_state.step = 1

# Ask for Link 1
if st.session_state.step == 1:
    link1 = st.text_input("Enter Link 1")

    # Add checkbox for needStyles
    st.session_state.needStyles = st.checkbox("Keep original styles?", value=True)
    needStyles = st.session_state.needStyles
    
    # Add button for manual HTML input, which skips the URL steps and goes straight to a modified HTML input flow
    if st.button("Manual HTML input"):
        st.session_state.link1 = None
        st.session_state.link2 = None
        st.session_state.step = 4
        st.rerun()

    # Add button to auto fill links if test mode is enabled
    if testMode:
        if test := st.checkbox("Use test links?"):
            #dropdown with 2 options, one for each test link set
            test_set = st.selectbox("Select test set", ["Set 1", "Set 2", "Set 3"])
            if test_set == "Set 1":
                link1 = "https://ecampusontario.pressbooks.pub/commbusprofcdn/chapter/the-evolution-of-digital-media/"
                link2 = "https://ecampusontario.pressbooks.pub/llsadvcomm/chapter/7-1-the-evolution-of-digital-media/"
            elif test_set == "Set 2":
                link1 = "https://openoregon.pressbooks.pub/comm115/chapter/chapter-3"
                link2 = "https://socialsci.libretexts.org/Bookshelves/Communication/Intercultural_Communication/Book%3A_Intercultural_Communication_for_the_Community_College_(Karen_Krumrey-Fulks)/01%3A_Chapters/1.04%3A_Self_and_Identity"
            elif test_set == "Set 3":
                link1 = "https://ecampusontario.pressbooks.pub/orgbiochemsupplement/chapter/alkanes-alkenes-alkynes/"
                link2 = "https://boisestate.pressbooks.pub/chemistry/chapter/21-1-hydrocarbons/"
            if link1 and link2:
                if st.button("Next"):
                    st.session_state.link1 = link1.strip()
                    st.session_state.link2 = link2.strip()
                    st.session_state.step = 3
                    st.rerun()
        else:
            if st.button("Next") and link1.strip():
                st.session_state.link1 = link1.strip()
                st.session_state.step = 2
                st.rerun()
    # If not in test mode, just show the normal flow with the single link input and next button
    else:
        if st.button("Next") and link1.strip():
            st.session_state.link1 = link1.strip()
            st.session_state.step = 2
            st.rerun()

# STEP 2 — Ask for Link 2
elif st.session_state.step == 2:
    st.write(f"Link 1 saved: {st.session_state.link1}")
    link2 = st.text_input("Enter Link 2")

    # Button to validate then direct the flow to step 3 which does the comparison and highlighting
    if st.button("Compare") and link2.strip():
        st.session_state.link2 = link2.strip()

        # Validate URLs
        result1 = checkURL(st.session_state.link1)
        result2 = checkURL(st.session_state.link2)
        if not result1:
            st.error(f"Link 1 is not valid or accessible. {urlResponse(st.session_state.link1)}")
        if not result2:
            st.error(f"Link 2 is not valid or accessible. {urlResponse(st.session_state.link2)}")
        if result1 and result2:
            st.session_state.step = 3
            st.rerun()

# STEP 3 — Show results
elif st.session_state.step == 3 or st.session_state.step == 5:
    start = time.time()
    # Link mode
    if st.session_state.step == 3:
        st.write("Comparing pages…")
        st.write("Link 1:", st.session_state.link1)
        st.write("Link 2:", st.session_state.link2)
    # Manual html mode
    elif st.session_state.step == 5:
        #needStyles = False
        st.write("Comparing manual HTML input…")
        st.session_state.link1 = None
        st.session_state.link2 = None

    # Add spinning animation while processing
    with st.spinner("Highlighting differences..."):
        link1 = st.session_state.link1
        link2 = st.session_state.link2

        # Fetch, parse, and split the text content into lists after normalizing. This is used for the difflib comparison to find unique content. Also keep the raw HTML for styling and display later.
        if link1:
            data = fetch(link1)
        else:
            data = st.session_state.data
        soupifiedData = BeautifulSoup(data, "html.parser")
        displayedText = soupifiedData.get_text().lower()
        displayedList = re.split(splitChars, displayedText)
        displayStrip1 = [line.strip() for line in displayedList]

        if link2:
            data2 = fetch(link2)
        else:
            data2 = st.session_state.data2
        soupifiedData2 = BeautifulSoup(data2, "html.parser")
        displayedText2 = soupifiedData2.get_text().lower()
        displayedList2 = re.split(splitChars, displayedText2)
        displayStrip2 = [line.strip() for line in displayedList2]

        # Style/clean the page and add inlined css so the original look is preserved.
        inlined1 = inline_css(data, link1)
        inlined2 = inline_css(data2, link2)

        # Use difflib to find unique content between the two pages. Convert to sets for comparison and filtering, and only keep differences longer than 3 characters.
        unique1, unique2 = get_unique_content(displayStrip1, displayStrip2)
        diffs1 = {d.strip().lower() for d in unique1 if len(d.strip()) > 3}
        diffs2 = {d.strip().lower() for d in unique2 if len(d.strip()) > 3}

        # Add highlights to html
        highlighted1 = addDiffStyles(inlined1, diffs1)
        highlighted2 = addDiffStyles(inlined2, diffs2)

        # Open html template that displays the two pages side by side, and insert the highlighted html into the template. The template also has a placeholder for custom styles that can be used to simplify the page look if the user chooses to remove original styles.
        highlighted_html = open("template.html", "r", encoding="utf-8").read()
        highlighted_html = highlighted_html.replace("{{page1}}", highlighted1)
        highlighted_html = highlighted_html.replace("{{page2}}", highlighted2)
        if not needStyles:
            highlighted_html = highlighted_html.replace("{{customStyles}}", """
                body div div {
                            overflow: hidden;
                            width: auto;
                        }
                figcaption, img {
                    max-width: 30vw;
                    height: auto;
                }
            """)

    # Display the final highlighted HTML in a scrollable container, and show the time taken for the comparison. Also provide buttons to reset the flow or switch between styled and plain views, which re-runs step 3 with the new setting.
    st.iframe(highlighted_html, height=800)
    st.write(f"Time taken: {time.time() - start:.2f} seconds")
    if st.button("Reset"):
        st.session_state.step = 1
        st.rerun()
    # If the user wants to switch between styled and plain, we can just re-run step 3 with the new setting
    if st.button(f"Compare {'without' if needStyles else 'with'} styles"):
        st.session_state.needStyles = not needStyles
        st.session_state.step = 3
        st.rerun()

# Manual HTML input flow, which skips the URL input and fetching steps, and just takes raw HTML input for comparison. Back up for websites with anti scrape/bot measures that aren't bypassed by cloudscraper.
elif st.session_state.step == 4:
    st.write("Manual HTML input mode")
    html1 = st.text_area("Enter HTML for Page 1")
    html2 = st.text_area("Enter HTML for Page 2")
    needStyles = st.checkbox("Keep original styles?", value=True)

    if st.button("Compare") and html1.strip() and html2.strip():
        st.session_state.link1 = "Manual Input 1"
        st.session_state.link2 = "Manual Input 2"
        st.session_state.data = html1.encode("utf-8")
        st.session_state.data2 = html2.encode("utf-8")
        st.session_state.step = 5
        st.rerun()

