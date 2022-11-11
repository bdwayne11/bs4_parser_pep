import logging
import re
from collections import defaultdict
from urllib.parse import urljoin

import requests_cache
from bs4 import BeautifulSoup
from tqdm import tqdm

from configs import configure_argument_parser, configure_logging
from constants import BASE_DIR, EXPECTED_STATUS, MAIN_DOC_URL, MAIN_PEP_URL
from outputs import control_output
from utils import find_tag, get_response


def whats_new(session):
    """Собирает информацию об обновлениях Python."""
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')
    response = get_response(session, whats_new_url)

    soup = BeautifulSoup(response.text, features='lxml')

    main_div = find_tag(soup, 'section', attrs={'id': 'what-s-new-in-python'})
    div_with_ul = find_tag(main_div, 'div', attrs={'class': 'toctree-wrapper'})
    sections_by_python = div_with_ul.find_all('li',
                                              attrs={'class': 'toctree-l1'})

    results = [('Ссылка на статью', 'Заголовок', 'Редактор, Автор')]
    for section in tqdm(sections_by_python):
        version_a_tag = section.find('a')

        href = version_a_tag['href']
        version_link = urljoin(whats_new_url, href)

        response = get_response(session, version_link)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, features='lxml')
        h1 = find_tag(soup, 'h1')
        dl = find_tag(soup, 'dl')
        dl_text = dl.text.replace('\n', ' ')
        results.append(
            (version_link, h1.text, dl_text)
        )

    return results


def latest_versions(session):
    """Собирается информация о последних версиях Python."""
    response = get_response(session, MAIN_DOC_URL)
    soup = BeautifulSoup(response.text, features='lxml')

    sidebar = find_tag(soup, 'div', attrs={'class': 'sphinxsidebarwrapper'})
    ul_tags = sidebar.find_all('ul')

    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
    else:
        raise Exception('Ничего не нашлось')

    results = [('Ссылка на документацию', 'Версия', 'Статус')]
    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        link = a_tag['href']
        text_match = re.search(pattern, a_tag.text)
        if text_match:
            version = text_match.group(1)
            status = text_match.group(2)
        else:
            version = a_tag.text
            status = ''
        results.append(
            (link, version, status)
        )

    return results


def download(session):
    """Скачивает документацию."""
    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')
    response = get_response(session, downloads_url)
    soup = BeautifulSoup(response.text, features='lxml')

    table_tag = find_tag(soup, 'table', attrs={'class': 'docutils'})
    pdf_a4_tag = find_tag(table_tag, 'a',
                          {'href': re.compile(r'.+pdf-a4\.zip$')})
    pdf_a4_link = pdf_a4_tag['href']
    archive_url = urljoin(downloads_url, pdf_a4_link)
    filename = archive_url.split('/')[-1]

    downloads_dir = BASE_DIR / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / filename
    response_2 = session.get(archive_url)
    with open(archive_path, 'wb') as file:
        file.write(response_2.content)
    logging.info(f'Архив был загружен и сохранён: {archive_path}')


def pep(session):
    """Парсинг PEP стандартов."""
    results = [('Статус', 'Количество')]
    status_count = defaultdict(int)
    total_count = 0
    response = get_response(session, MAIN_PEP_URL)
    soup = BeautifulSoup(response.text, features='lxml')

    all_tables = find_tag(soup, 'section', attrs={'id': 'numerical-index'})
    t_body = find_tag(all_tables, 'tbody')
    trs = t_body.find_all('tr')

    for tr in tqdm(trs):
        status_id = find_tag(tr, 'td').text[1:]
        expected_status = EXPECTED_STATUS.get(status_id, [])
        pep_card_link = urljoin(MAIN_PEP_URL, tr.find('a')['href'])
        response = session.get(pep_card_link)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, features='lxml')
        status = find_tag(soup, text='Status').find_next('dd').text
        if status not in expected_status:
            logging.info(
                'Несовпадающие статусы: '
                f'{pep_card_link}. '
                f'Статус в карточке: {status}. '
                f'Ожидаемые статусы: {expected_status}.'
            )
        total_count += 1
        status_count[status] += 1

    results.extend((status_count.items()))
    results.append(('Total', total_count))

    return results


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep,
}


def main():
    """Main-функция."""
    configure_logging()
    logging.info('Парсер запущен!')
    arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    args = arg_parser.parse_args()
    logging.info(f'Аргументы командной строки: {args}')

    session = requests_cache.CachedSession()

    if args.clear_cache:
        session.cache.clear()

    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)

    if results is not None:
        control_output(results, args)
    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
