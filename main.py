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
ANKI_DECK_RADICALS = 'TenTen::Radicals'
ANKI_DECK_KANJIS = 'TenTen::Kanjis'
ANKI_DECK_VOCABS = 'TenTen::Vocabs'

WANIKANI_API_KEY = open('wanikani_token').read().strip()
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

def download_audio(vocab: str):
    # find vokab in wanikani_data_all
    vocab_data = next(filter(lambda x: x['data']['characters'] == vocab and x['object'] == 'vocabulary', wanikani_data_all), None)
    if vocab_data is None:
        print(f'Vocab {vocab} not found in wanikani data')
        return None
    # get male audio url
    audio_urls = vocab_data['data']['pronunciation_audios']
    audio_urls_male = list(filter(lambda x: x['metadata']['gender'] == 'male' and x['content_type'] == 'audio/mp3', audio_urls))
    audio_url = audio_urls_male[0]['url'] if len(audio_urls_male) > 0 else None
    if audio_url is None:
        audio_url = audio_urls[0]['url'] if len(audio_urls) > 0 else None
    if audio_url is None:
        return None
    
    # download audio from url
    r = requests.get(audio_url, headers={'Authorization': 'Bearer ' + WANIKANI_API_KEY})
    if r.status_code != 200:
        print(f"Error: {r.content}")
        exit(1)
    # get audio data
    audio_bytes = r.content
    return audio_bytes
    

def create_vocab_card(vocab: str, data: WordConfig, kanjis_data: Dict[str, KanjiConfig], wanikani_data: List[Dict], add_furigana_for_kanji: List[str]):
    """Create a new vocab card in anki"""

    seperated_name = separate_character_type_groups(vocab)
    audio = download_audio(vocab)

    assert len(add_furigana_for_kanji) <= 1 # only one kanji can have furigana right now
    for kanji in add_furigana_for_kanji:
        assert kanji in vocab
        reading = data.japanese[0].reading if data.japanese[0].reading is None else data.japanese[0].reading
        vocab_without_kaji = ''.join([c for c in vocab if not is_kanji(c)])
        furigana = reading.replace(vocab_without_kaji, '')
        vocab = vocab.replace(kanji, f'{kanji}[{furigana}]')

    # upload audio to anki
    audio_name = None
    if audio is not None:
        r = requests.post(ANKI_ADDRESS, json={
            'action': 'storeMediaFile',
            'version': 6,
            'params': {
                'filename': f'{ANKI_DECK_VOCABS}_{base64.b64encode(vocab.encode("utf-8")).decode()}.mp3',
                'data': base64.b64encode(audio).decode('utf-8')
            }
        })
        audio_name = r.json()['result']
        if audio_name is None:
            print(f'Audio for {vocab} already exists')
        else:
            print(f'Created audio for {vocab}')

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
                    'kanjis': seperated_name if len(wanikani_data) > 0 else '',
                    'kanjis_names': replace_kanjis_by_meaning(seperated_name, wanikani_data) if len(wanikani_data) > 0 else '',
                    'type': ", ".join(data.senses[0].parts_of_speech),
                    'sound': f'[sound:{audio_name}]' if audio_name is not None else '',
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

def get_radical_character(radical: Dict, smol: bool = False) -> str:
    character = radical['data']['characters']
    if character is not None:
        return character
    url = list(filter(
        lambda x: x['content_type'] == 'image/svg+xml',
        radical['data']['character_images']))[0]['url']
    # download image from url
    r = requests.get(url)
    # get image data
    image_bytes = r.content
    name = radical['data']['meanings'][0]['meaning']
    if r.status_code != 200:
        assert false
    filename = f"{ANKI_DECK_RADICALS}_{name}.svg"
    r = requests.post(ANKI_ADDRESS, json={
        'action': 'storeMediaFile',
        'version': 6,
        'params': {
            'filename': filename,
            'data': base64.b64encode(image_bytes).decode('utf-8')
        }
    })
    image_name = r.json()['result']
    print(f"img_name: {image_name}")
    if image_name is None:
        print(f'image for radical {name} already exists')
    else:
        print(f'Created radical img for {name}')

    if smol:
        return f'<img src="{image_name}" class="smol" >'
    else:
        return f'<img src="{image_name}">'
    

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
                    'radicals': " ".join([get_radical_character(radical, True) for radical in radicals]),
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

def get_radical_by_id(radical_id: int) -> Dict:
    return next((radical for radical in wanikani_data_all if radical['id'] == radical_id), None)

def create_radical_card(radical: Dict, wanikani_data: Dict):
    """Create a new kanji card in anki"""
    # get radicals data

    # create card in anki
    r = requests.post(ANKI_ADDRESS, json={
        'action': 'addNote',
        'version': 6,
        'params': {
            'note': {
                'deckName': ANKI_DECK_RADICALS,
                'modelName': 'TenTen_Radicals',
                'fields': {
                    'radical': get_radical_character(radical, False),
                    'name': ", ".join([meaning['meaning'] for meaning in radical['data']['meanings']]),
                    'meaning_mnemonic': radical['data']['meaning_mnemonic'],
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
        print(f'Radical {radical["data"]["characters"]} already in deck')
    else:
        print(f'Radical {radical["data"]["characters"]} added to deck')

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
        kanjis_data_jisho += [get_kanji_data(kanji)]
    
    
    data_wanikani_kanjis_all = filter(lambda x: x['object'] == 'kanji', wanikani_data_all)
    kanji_data_wanikani = list(filter(lambda x: x['data']['characters'] in kanjis, data_wanikani_kanjis_all))

    add_furigana_for_kanji = []

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
            wanikani_data = None
            try:
                wanikani_data = list(filter(lambda x: x['data']['characters'] == kanji, kanji_data_wanikani))[0]
            except IndexError:
                print(f'Kanji {kanji} not found in wanikani data')
                add_furigana_for_kanji += [kanji]
                continue
            create_kanji_card(kanji, jisho_data, wanikani_data)

            # create card for each radical in kanji
            for radical_id in wanikani_data['data']['component_subject_ids']:
                radical = next((radical for radical in wanikani_data_all if radical['id'] == radical_id), None)
                if radical is not None:
                  r = requests.post(ANKI_ADDRESS, json={
                      'action': 'findNotes',
                      'version': 6,
                      'params': {
                          'query': f'deck:{ANKI_DECK_RADICALS} front:{radical["data"]["characters"]}'
                      }
                  }) 
                  if not r.json()['result']:
                      create_radical_card(radical, wanikani_data_all)

    create_vocab_card(vocab, data, kanjis_data_jisho, kanji_data_wanikani, add_furigana_for_kanji)


      


def get_kanji_data(kanji: str) -> Dict:
    """Get data for kanji from jisho.org API"""
    return Kanji.request(kanji, cache=False).data

def get_vocab_data(vocab: str) -> Dict:
    """Get data for words from jisho.org API"""
    data = Word.request(vocab, cache=False).data

    # remove -1 from slug (weird bug)
    data[0].slug = data[0].slug.replace('-1', '')

    # Ensure the match is exact
    if (data[0].japanese[0].word != vocab and data[0].japanese[0].reading != vocab) and not '〜' in vocab:
        raise ValueError(f'No exact match found. But found {data[0].slug}')
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
