import base64
import sys
import requests
from jisho_api.word import Word
from jisho_api.word.cfg import WordConfig
from jisho_api.kanji import Kanji
from jisho_api.kanji.cfg import KanjiConfig
import json

from typing import Dict, List

ANKI_ADDRESS = 'http://127.0.0.1:8765'
ANKI_DECK_KANJIS = 'TenTen::Kanjis'
ANKI_DECK_VOCABS = 'TenTen::Vocabs'

wanikani_data_all = json.loads(open('wanikani_data.json', 'r').read())

def separate_character_type_groups(vocab: str) -> str:
    """Separate groups of kanji and kana with dashes"""
    separated = ''
    was_kanji = False
    for char in vocab:
        if separated != '' and (is_kanji(char) or was_kanji):
            separated += ' - '
        separated += char
        was_kanji = is_kanji(char)
    return separated


def unique(list1):
    return list(dict.fromkeys(list1))

def replace_kanjis_by_meaning(seperated_name: str, wanikani_data: List[Dict]) -> str:
    """Replace kanjis by their meaning"""
    for kanji_data in wanikani_data:
        seperated_name = seperated_name.replace(kanji_data['data']['characters'], kanji_data['data']['meanings'][0]['meaning'])
    return seperated_name

def create_vocab_card(vocab: str, data: WordConfig, kanjis_data: Dict[str, KanjiConfig], wanikani_data: List[Dict]):
    """Create a new vocab card in anki"""
    seperated_name = separate_character_type_groups(vocab)
    # create card in anki
    r = requests.post(ANKI_ADDRESS, json={
        'action': 'addNote',
        'version': 6,
        'params': {
            'note': {
                'deckName': ANKI_DECK_VOCABS,
                'modelName': 'TenTen_Vocab',
                'fields': {
                    'meanings': ", ".join(data.senses[0].english_definitions),
                    'vocab': vocab,
                    'readings': ", ".join(unique([reading.reading for reading in data.japanese])),
                    'kanjis': seperated_name,
                    'kanjis_names': replace_kanjis_by_meaning(seperated_name, wanikani_data),
                    'type': ", ".join(data.senses[0].parts_of_speech),
                    'sound': ''
                },
                'options': {
                    'allowDuplicate': False
                },
                'tags': []
            }
        }
    })
    # print result
    if r.json()['result'] is None:
        print(f'Vocab {vocab} already exists')
    else:
        print(f'Created vocab {vocab}')


def format_readings(wanikani_data: Dict, reading: str) -> str:
    readings = filter(lambda x: x['type'] == reading, wanikani_data['data']['readings'])
    readings_lst_str = []

    # add <u> around primary readings
    for reading in readings:
        if reading['primary']:
            readings_lst_str += [f'<u>{reading["reading"]}</u>']
        else:
            readings_lst_str += [reading['reading']]

    return ", ".join(readings_lst_str)


def get_radicals_data(wanikani_data: Dict) -> List:
    radicals = []
    for radical_id in wanikani_data['data']['component_subject_ids']:
        radical = next((radical for radical in wanikani_data_all if radical['id'] == radical_id), None)
        assert radical is not None
        radicals += [radical]
    return radicals

def get_radical_character(radical: Dict) -> str:
    character = radical['data']['characters']
    if character is not None:
        return character
    url = list(filter(
        lambda x: x['content_type'] == 'image/png' and 
        x['metadata']['style_name'] == '32px', 
        radical['data']['character_images']))[0]['url']
    # download image from url
    r = requests.get(url)
    # get image data
    image_bytes = r.content
    # convert image data to base64 string
    image_as_b64 = base64.b64encode(image_bytes).decode('utf-8')
    return f'<img class="encoded_radical" src="data:image/png;base64,{image_as_b64}">'

def get_similar_kanji_data(wanikani_data: Dict) -> List:
    similar_kanji = []
    for similar_kanji_id in wanikani_data['data']['visually_similar_subject_ids']:
        similar_kanji += [next((kanji for kanji in wanikani_data_all if kanji['id'] == similar_kanji_id), None)]
    return similar_kanji

def create_kanji_card(kanji: str, jisho_data: KanjiConfig, wanikani_data: Dict):
    """Create a new kanji card in anki"""
    # get radicals data
    radicals = get_radicals_data(wanikani_data)
    similar_kanjis = get_similar_kanji_data(wanikani_data)

    # create card in anki
    r = requests.post(ANKI_ADDRESS, json={
        'action': 'addNote',
        'version': 6,
        'params': {
            'note': {
                'deckName': ANKI_DECK_KANJIS,
                'modelName': 'TenTen_Kanji',
                'fields': {
                    'kanji': wanikani_data['data']['characters'],
                    'name': ", ".join([meaning['meaning'] for meaning in wanikani_data['data']['meanings']]),
                    'readings_on': format_readings(wanikani_data, 'onyomi'),
                    'readings_kun': format_readings(wanikani_data, 'kunyomi'),
                    'meaning_mnemonic': wanikani_data['data']['meaning_mnemonic'],
                    'meaning_hint': wanikani_data['data']['meaning_hint'],
                    'reading_mnemonic': wanikani_data['data']['reading_mnemonic'],
                    'reading_hint': wanikani_data['data']['reading_hint'],
                    'radicals': " - ".join([get_radical_character(radical) for radical in radicals]),
                    'radicals_names': " - ".join(radical['data']['meanings'][0]['meaning'] for radical in radicals),
                    'simmilar_kanji': ', '.join([similar_kanji['data']['characters'] for similar_kanji in similar_kanjis]),
                    'simmilar_kanji_names': ", ".join([similar_kanji['data']['meanings'][0]['meaning'] for similar_kanji in similar_kanjis]),
                },
                'options': {
                    'allowDuplicate': False
                },
                'tags': []
            }
        }
    })

    # print result
    if r.json()['result'] is None:
        print(f'Kanji {kanji} already in deck')
    else:
        print(f'Kanji {kanji} added to deck')

def main():
    
    # get vocab from command line and catch error
    try:
        vocab = sys.argv[1]
    except IndexError:
        print('No vocab given')
        return


    # get data for vocab from jisho.org API
    data = get_vocab_data(vocab)

    # search ankis database using ankiconnect for notes in deck
    r = requests.post(ANKI_ADDRESS, json={
        'action': 'findNotes',
        'version': 6,
        'params': {
            'query': f'deck:{ANKI_DECK_VOCABS} front:{vocab}'
        }
    })

    # # if yes, terminate  TODO: FIX
    # if r.json()['result']:
    #     print('Vocab already in deck')
    #     return

    kanjis = get_kanji_from_word(vocab)
    kanjis_data_jisho = []

    for kanji in kanjis:
        kanjis_data_jisho += get_kanji_data(kanji)
    
    
    data_wanikani_kanjis_all = filter(lambda x: x['object'] == 'kanji', wanikani_data_all)
    kanji_data_wanikani = list(filter(lambda x: x['data']['characters'] in kanjis, data_wanikani_kanjis_all))
        
    create_vocab_card(vocab, data, kanjis_data_jisho, kanji_data_wanikani)

    # then search ankis database for each kanji in vocab
    for kanji, jisho_data in zip(kanjis, kanjis_data_jisho):
        # if not exists, create new card for each kanji
        r = requests.post(ANKI_ADDRESS, json={
            'action': 'findNotes',
            'version': 6,
            'params': {
                'query': f'deck:{ANKI_DECK_KANJIS} front:{kanji}'
            }
        }) 
        if not r.json()['result']:
            wanikani_data = list(filter(lambda x: x['data']['characters'] == kanji, kanji_data_wanikani))[0]
            create_kanji_card(kanji, jisho_data, wanikani_data)

      


def get_kanji_data(kanji: str) -> Dict:
    """Get data for kanji from jisho.org API"""
    return Kanji.request(kanji, cache=True).data

def get_vocab_data(vocab: str) -> Dict:
    """Get data for words from jisho.org API"""
    data = Word.request(vocab, cache=True).data
    # Ensure the match is exact
    if data[0].slug != vocab:
        raise ValueError('No exact match found')
    return data[0]


def get_kanji_from_word(word: str) -> list:
    """Get kanji from word"""
    kanjis = []
    for char in word:
        if is_kanji(char):
            kanjis.append(char)
    return kanjis

def is_kanji(char: str) -> bool:
    """Check if char is kanji with detailed explanation"""
    if len(char) != 1:
        raise ValueError('char must be a single character')
    return 0x4E00 <= ord(char) <= 0x9FFF

    
#Example: 食い止める

if __name__ == '__main__':
    main()