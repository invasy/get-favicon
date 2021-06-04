#!/usr/bin/env python
import logging
import os
import os.path
import re
from argparse import ArgumentParser
from io import BytesIO
from typing import List
from urllib.parse import urlparse

import requests
from PIL import Image
from bs4 import BeautifulSoup


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/47.0.2526.111 Safari/537.36',
}
EXCLUDED_DOMAINS = ['www', 'com', 'org', 'net', 'ru']


def get_favicon_url(url: str) -> str:
    favicon_url = ''
    parsed_url = urlparse(url)

    response = requests.get(url, headers=HEADERS)
    if response.status_code == requests.codes.ok:
        # Try to get favicon URL from LINK tag
        soup = BeautifulSoup(response.content, 'lxml')
        link = soup.find('link', rel='icon')
        if link and 'href' in link.attrs:
            favicon_url = link['href']

    if not favicon_url:
        # Try to get favicon URL from default locations
        basename = '{url.scheme}://{url.netloc}/favicon.'.format(url=parsed_url)
        for ext in ['png', 'ico']:
            response = requests.head(basename + ext, headers=HEADERS)
            if response.is_redirect:
                favicon_url = response.headers['Location']
                break
            elif response.status_code == requests.codes.ok:
                favicon_url = response.url
                break

    if favicon_url:
        if favicon_url.startswith('//'):  # Protocol-relative URL
            favicon_url = parsed_url.scheme + ':' + favicon_url
        elif favicon_url.startswith('/'):  # Absolute path (relative to the domain)
            favicon_url = parsed_url.scheme + '://' + parsed_url.netloc + favicon_url
        elif not favicon_url.startswith('http'):  # Relative path
            path, filename = os.path.split(parsed_url.path)
            favicon_url = parsed_url.scheme + '://' + parsed_url.netloc + '/' + path + '/' + favicon_url

    return favicon_url


def get_filename(url: str, favicon_url: str, png: bool = False) -> str:
    ext = '.png' if png else os.path.splitext(urlparse(favicon_url).path)[1]
    return '-'.join(filter(lambda d: d not in EXCLUDED_DOMAINS, urlparse(url).netloc.split('.'))) + ext


def get_favicon(url: str, filename: str = '', resize: int = 0) -> None:
    logging.debug("trying to get favicon from '%s'…", url)
    response = requests.get(url, headers=HEADERS)
    if response.status_code != requests.codes.ok:
        response.raise_for_status()

    favicon = Image.open(BytesIO(response.content))
    logging.debug("%s %d×%d at '%s'", favicon.format, favicon.width, favicon.height, response.url)
    if resize > 0:
        size = (resize, resize)
        if favicon.format == 'ICO' and size in favicon.ico.sizes():
            favicon = favicon.ico.getimage(size)
        else:
            favicon = favicon.resize(size, resample=Image.BICUBIC)
        logging.debug("resized to %d×%d", favicon.width, favicon.height)

    favicon.save(filename)
    logging.debug("saved as '%s'", filename)


def get_favicons(urls: List[str], output_dir: str = '', png: bool = True, resize: int = 0, get: bool = True) -> None:
    for url in urls:
        try:
            if not url.startswith('http'):
                url = 'https://' + url

            favicon_url = get_favicon_url(url)
            if not favicon_url:
                raise Exception(f"cannot find favicon for URL '{url}'")

            if get:
                if not output_dir:
                    output_dir = os.path.curdir
                filename = os.path.join(output_dir, get_filename(url, favicon_url, png))
                get_favicon(favicon_url, filename, resize)
            else:
                print(favicon_url)
        except requests.ConnectionError:
            logging.error("cannot connect to '%s'", url)
        except requests.RequestException as ex:
            logging.error("requests: %s", ex)
        except Exception as ex:
            logging.error(ex)


def get_dokuwiki_interwiki_icons(dokuwiki_home: str, force: bool = False) -> None:
    dokuwiki_home = os.path.abspath(dokuwiki_home)
    images_dir = os.path.join(dokuwiki_home, 'lib', 'images', 'interwiki')
    os.makedirs(images_dir, mode=0o770, exist_ok=True)

    with open(os.path.join(dokuwiki_home, 'conf', 'interwiki.local.conf')) as f:
        for line in f:
            try:
                m = re.fullmatch(r'([-0-9.a-z_]+)\s+(.*)', line.strip(), flags=re.ASCII)
                if not m:
                    continue
                name = m.group(1)
                filename = os.path.join(images_dir, name + '.png')
                if os.path.isfile(filename) and not force:
                    logging.info("%s: icon exists - skip", name)
                    continue
                url = '{url.scheme}://{url.netloc}/'.format(url=urlparse(m.group(2)))
                favicon_url = get_favicon_url(url)
                if not favicon_url:
                    logging.error("%s: cannot find favicon for URL '%s'", name, url)
                    continue
                get_favicon(favicon_url, filename, resize=16)
            except requests.ConnectionError:
                logging.error("cannot connect to '%s'", args.url)
                continue
            except requests.RequestException as ex:
                logging.error("requests: %s", ex)
                continue
            except Exception as ex:
                logging.error('%s', ex)
                continue
            logging.info("%s: icon saved as '%s'", name, filename)


if __name__ == '__main__':
    parser = ArgumentParser(description='Get favicons for URLs')
    parser.add_argument('url', metavar='URL', nargs='*', help='URLs to get favicons for')
    parser.add_argument('-@', '--args-file', metavar='FILENAME', help='read URLs from file')
    parser.add_argument('-d', '--dir', default='', help='save favicon in directory DIR')
    parser.add_argument('-r', '--resize', metavar='SIZE', type=int, default=0, help='resize favicon to SIZE×SIZE')
    parser.add_argument('-p', '--png', action='store_true', help='convert favicon to PNG format')
    parser.add_argument('-n', '--no-get', action='store_false', dest='get', help='just print favicon URL')
    parser.add_argument('-v', '--verbose', action='store_true', help='show info messages')
    dokuwiki_group = parser.add_argument_group('dokuwiki', 'Get favicons for DokuWiki interwikis')
    dokuwiki_group.add_argument('-D', '--dokuwiki', metavar='PATH', help='path to DokuWiki instance')
    dokuwiki_group.add_argument('-f', '--force', action='store_true', help='rewrite interwiki icon if it exists')
    args = parser.parse_args()

    logging.basicConfig(
        format="favicon: %(levelname)s: %(message)s",
        level=(logging.INFO if args.verbose else logging.WARNING),
    )

    if args.dokuwiki:
        get_dokuwiki_interwiki_icons(args.dokuwiki, force=args.force)
    else:
        if args.args_file:
            with open(args.args_file) as f:
                args.url = f.read().splitlines()
        get_favicons(args.url, output_dir=args.dir, png=args.png, resize=args.resize, get=args.get)
