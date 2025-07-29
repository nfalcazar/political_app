from googlesearch import search

# Limited searching, need proper custom search API from google
# est perplex pricing 5c for 7 req -> $35 for 1000 req
# google custom pricing 100 free, $5 per 1000

#ChatGPT search queries

query = "U.S. Supreme Court emergency injunction PDF Alien Enemies Act Venezuelans northern Texas order"
print(f"query: {query}\n")
for url in search(query, num_results=5):
    print(url)

query = "site:supremecourt.gov emergency injunction alien enemies act Venezuelan Texas PDF"
print(f"\n\nquery: {query}\n")
for url in search(query, num_results=5):
    print(url)


query = '"Supreme Court" "blocking deportations" "Venezuelans" "Texas" "18th century wartime law" site:.gov OR site:.us OR site:supremecourt.gov'
print(f"\n\nquery: {query}\n")
for url in search(query, num_results=5):
    print(url)


#query = 'site:supremecourt.gov inurl:/opinions/ filetype:pdf "Venezuelans" "Alien Enemies Act" Texas OR site:supremecourt.gov inurl:/docket/ "Alien Enemies Act" OR site:.gov "Alien Enemies Act" Venezuelans deportation OR site:heritage.org OR site:brookings.edu OR site:urban.org "Alien Enemies Act" Venezuelans OR site:.edu "Alien Enemies Act" Venezuelans filetype:pdf'
#query = 'site:supremecourt.gov filetype:pdf "Venezuelans" "Alien Enemies Act" Texas OR site:supremecourt.gov inurl:/docket/ "Alien Enemies Act" OR site:.gov "Alien Enemies Act" Venezuelans deportation'
query = 'site:supremecourt.gov inurl:/opinions/ "Alien Enemies Act" OR Venezuelans OR Texas filetype:pdf'
print(f"\n\nquery: {query}\n")
for url in search(query, num_results=5):
    print(url)