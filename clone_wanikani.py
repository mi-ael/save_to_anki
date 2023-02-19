import requests
import sys
import json


WANIKANI_API_KEY = open('wanikani_token').read().strip()
WANIKANI_URL = 'https://api.wanikani.com/v2/'

# main
def main():
    # download all subjects from wanikani and save to file
    all_data = []
    next_url = WANIKANI_URL + 'subjects'
    while next_url is not None:
        request_data = requests.get(next_url, headers={'Authorization': 'Bearer ' + WANIKANI_API_KEY}).json()
        all_data.extend(request_data['data'])
        next_url = request_data['pages']['next_url']
      
    # save all_data to file as json
    with open('wanikani_data.json', mode='w') as file:
        file.write(json.dumps(all_data, indent=2, ensure_ascii=False))



if __name__ == '__main__':
    main()