# Third-party notices

Beetser is distributed under the MIT license (see [LICENSE](LICENSE)).

The container image and this repository build on third-party software. Most of
it is permissively licensed; a few components are **GPL** or **LGPL**, which
means their source code must remain available when the image is redistributed.
Nothing here changes the license of Beetser's own code.

## Bundled applications

### beets 2.14.1 — MIT

Beetser drives the real beets importer (as a subprocess and through its Python
API). beets is redistributed unmodified.

```
The MIT License

Copyright (c) 2010-2016 Adrian Sampson

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Source: <https://github.com/beetbox/beets>

## GPL / LGPL components

These components are redistributed **unmodified**, installed from their
upstream releases (PyPI or Debian). The image ships their Python sources (or
binaries plus Debian copyright files) and the license texts under
`/usr/share/doc/<package>/copyright`, so the corresponding source travels with
the image. Upstream sources:

| Component | License | Source |
| --- | --- | --- |
| mutagen (tags read/write, via beets/mediafile) | GPL-2.0-or-later | <https://github.com/quodlibet/mutagen> |
| Unidecode (transliteration, via beets) | GPL-2.0-or-later | <https://github.com/avian2/unidecode> |
| FFmpeg (Debian `ffmpeg`, used by beets for unsupported formats) | GPL-2.0-or-later (Debian build enables `--enable-gpl`) | <https://ffmpeg.org/download.html> |
| Chromaprint (`libchromaprint-tools`, AcoustID fingerprints) | LGPL-2.1-or-later | <https://github.com/acoustid/chromaprint> |

If you redistribute the Beetser image, keep these notices and offer the
corresponding sources. Beetser itself is not derivative of these programs: they
are separate, unmodified dependencies invoked by beets.

## System packages

| Package | License |
| --- | --- |
| Debian slim base image | various (DFSG-free), see `/usr/share/doc/*/copyright` |
| Python 3.12 runtime | PSF-2.0 |
| gosu | Apache-2.0 |
| tini | MIT |

## Python dependencies

Installed from PyPI without modification.

| Package | License |
| --- | --- |
| annotated-doc, annotated-types, anyio, beautifulsoup4, charset-normalizer, confuse, fastapi, filetype, h11, httptools, jellyfish, mediafile, packaging (dual), platformdirs, pydantic, pydantic-core, pydantic-settings, pyrate-limiter, python-dotenv (BSD-3-Clause option), PyYAML, requests-ratelimiter, soupsieve, SQLAlchemy, typing-inspection, urllib3, watchfiles | MIT / BSD / Apache-2.0 (per package) |
| click, httpcore, httpx, idna, python-dotenv, starlette, uvicorn, websockets | BSD-3-Clause |
| certifi | MPL-2.0 |
| itsdangerous | BSD-3-Clause |
| lap | BSD-2-Clause |
| numpy | BSD-3-Clause (bundles 0BSD, MIT, Zlib, CC0-1.0 parts) |
| opentelemetry-api, python-multipart, requests, watchdog | Apache-2.0 |
| Pillow | MIT-CMU (HPND) |
| typing_extensions | PSF-2.0 |
| uvloop | MIT |
| mutagen, Unidecode | GPL-2.0-or-later |

Exact versions are pinned in [backend/pyproject.toml](backend/pyproject.toml)
and resolved in the image build. Each installed distribution keeps its own
license file inside the container (`.../dist-info/licenses/`).

## Frontend libraries

| Package | License |
| --- | --- |
| React, React DOM, React Router, TanStack Query, Tailwind CSS, clsx, tailwind-merge, sonner | MIT |
| lucide-react | ISC |
| Vite, TypeScript (build time only) | MIT / Apache-2.0 |

## Upstream metadata

Beetser queries MusicBrainz and the Cover Art Archive at runtime. No data from
those services is redistributed with the software; check their terms if you
operate a public instance.
