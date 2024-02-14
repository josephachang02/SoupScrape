import urllib.request, urllib.parse, urllib.error
from bs4 import BeautifulSoup

url = input("Enter the URL: ")

response = urllib.request.urlopen(url)
html_content = response.read()

# Parse the HTML content
soup = BeautifulSoup(html_content, 'html.parser')

# Find all <span> tags with the class "comments"
span_tags = soup.find_all('span', class_='comments')

total_comments = 0
for span in span_tags:
    total_comments += int(span.text)

print("Total comments:", total_comments)