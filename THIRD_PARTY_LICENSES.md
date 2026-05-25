# Third-Party Licenses

> **Generated**: 2026-05-23 via the reproduction command below.
> **Scope**: every Python package present in the active venv at the time of generation.
> **Refresh policy**: re-generate at every minor JAMES version (v0.4, v0.5, …) and whenever a dep is added.

## Reproduction

```bash
pip install pip-licenses                    # one-time
python scripts/gen_third_party_licenses.py
```

Anything that differs between fresh-run output and this committed file is a dep change since the last refresh.

## Summary

**Total packages**: 204

| License | Count |
|---|---|
| MIT | 83 |
| Apache-2.0 | 56 |
| BSD | 30 |
| BSD-3-Clause | 23 |
| BSD-2-Clause | 3 |
| PSF-2.0 | 3 |
| MPL-2.0 | 2 |
| MIT AND PSF-2.0 | 1 |
| GNU Library or Lesser General Public License (LGPL) | 1 |
| ISC | 1 |
| Apache Software License; MIT License | 1 |

### JAMES-vs-deps license compatibility note

JAMES itself is **MIT** (see [`LICENSE`](LICENSE)). The deps inventoried below are all under permissive licenses (MIT / Apache-2.0 / BSD family / MPL / PSF) compatible with MIT redistribution. Any future GPL / AGPL dep would need an explicit architectural review — see [`docs/LICENSE_PLAN.md`](docs/LICENSE_PLAN.md) for the project license policy.

## Per-package detail

| Package | Version | License |
|---|---|---|
| [aiohappyeyeballs](https://github.com/aio-libs/aiohappyeyeballs) | 2.6.1 | PSF-2.0 |
| [aiohttp](https://github.com/aio-libs/aiohttp) | 3.13.5 | Apache-2.0 |
| [aiosignal](https://github.com/aio-libs/aiosignal) | 1.4.0 | Apache-2.0 |
| [annotated-doc](https://github.com/fastapi/annotated-doc) | 0.0.4 | MIT |
| [annotated-types](https://github.com/annotated-types/annotated-types) | 0.7.0 | MIT |
| [anyio](https://anyio.readthedocs.io/en/stable/versionhistory.html) | 4.13.0 | MIT |
| [appdirs](http://github.com/ActiveState/appdirs) | 1.4.4 | MIT |
| [attrs](https://www.attrs.org/en/stable/changelog.html) | 26.1.0 | MIT |
| [bcrypt](https://github.com/pyca/bcrypt/) | 5.0.0 | Apache-2.0 |
| [beautifulsoup4](https://www.crummy.com/software/BeautifulSoup/bs4/) | 4.14.3 | MIT |
| [build](https://build.pypa.io) | 1.5.0 | MIT |
| [certifi](https://github.com/certifi/python-certifi) | 2026.4.22 | MPL-2.0 |
| [cffi](https://cffi.readthedocs.io/en/latest/whatsnew.html) | 2.0.0 | MIT |
| [charset-normalizer](https://github.com/jawah/charset_normalizer/blob/master/CHANGELOG.md) | 3.4.7 | MIT |
| [chromadb](https://github.com/chroma-core/chroma) | 1.5.8 | Apache-2.0 |
| [click](https://github.com/pallets/click/) | 8.3.3 | BSD-3-Clause |
| [cobble](http://github.com/mwilliamson/python-cobble) | 0.1.4 | BSD |
| [colorama](https://github.com/tartley/colorama) | 0.4.6 | BSD |
| [cryptography](https://github.com/pyca/cryptography) | 47.0.0 | Apache-2.0 |
| [dataclasses-json](https://github.com/lidatong/dataclasses-json) | 0.6.7 | MIT |
| [datasets](https://github.com/huggingface/datasets) | 4.8.5 | Apache-2.0 |
| [defusedxml](https://github.com/tiran/defusedxml) | 0.7.1 | PSF-2.0 |
| [dill](https://github.com/uqfoundation/dill) | 0.4.1 | BSD |
| [diskcache](http://www.grantjenks.com/docs/diskcache/) | 5.6.3 | Apache-2.0 |
| [distro](https://github.com/python-distro/distro) | 1.9.0 | Apache-2.0 |
| [docstring_parser](https://github.com/rr-/docstring_parser) | 0.18.0 | MIT |
| [duckduckgo_search](https://github.com/deedy5/duckduckgo_search) | 8.1.1 | MIT |
| [durationpy](https://github.com/icholy/durationpy) | 0.10 | MIT |
| [easyocr](https://github.com/jaidedai/easyocr) | 1.7.2 | Apache-2.0 |
| [ecdsa](http://github.com/tlsfuzzer/python-ecdsa) | 0.19.2 | MIT |
| [et_xmlfile](https://foss.heptapod.net/openpyxl/et_xmlfile) | 2.0.0 | MIT |
| [fastapi](https://github.com/fastapi/fastapi) | 0.136.1 | MIT |
| [ffmpeg-python](https://github.com/kkroening/ffmpeg-python) | 0.2.0 | Apache-2.0 |
| [filelock](https://github.com/tox-dev/py-filelock) | 3.29.0 | MIT |
| [flatbuffers](https://google.github.io/flatbuffers/) | 25.12.19 | Apache-2.0 |
| [frozenlist](https://github.com/aio-libs/frozenlist) | 1.8.0 | Apache-2.0 |
| [fsspec](https://github.com/fsspec/filesystem_spec) | 2026.2.0 | BSD-3-Clause |
| [future](https://python-future.org) | 1.0.0 | MIT |
| [googleapis-common-protos](https://github.com/googleapis/google-cloud-python/tree/main/packages/googleapis-common-protos) | 1.74.0 | Apache-2.0 |
| [greenlet](https://greenlet.readthedocs.io) | 3.5.0 | MIT AND PSF-2.0 |
| [grpcio](https://grpc.io) | 1.80.0 | Apache-2.0 |
| [h11](https://github.com/python-hyper/h11) | 0.16.0 | MIT |
| [hf-xet](https://github.com/huggingface/xet-core) | 1.4.3 | Apache-2.0 |
| [httpcore](https://www.encode.io/httpcore/) | 1.0.9 | BSD-3-Clause |
| [httptools](https://github.com/MagicStack/httptools) | 0.7.1 | MIT |
| [httpx](https://github.com/encode/httpx) | 0.28.1 | BSD |
| [httpx-sse](https://github.com/florimondmanca/httpx-sse) | 0.4.3 | MIT |
| [huggingface_hub](https://github.com/huggingface/huggingface_hub) | 1.13.0 | Apache-2.0 |
| [idna](https://github.com/kjd/idna) | 3.15 | BSD-3-Clause |
| [ImageIO](https://github.com/imageio/imageio) | 2.37.3 | BSD-2-Clause |
| [importlib_metadata](https://github.com/python/importlib_metadata) | 8.7.1 | Apache-2.0 |
| [importlib_resources](https://github.com/python/importlib_resources) | 7.1.0 | Apache-2.0 |
| [iniconfig](https://github.com/pytest-dev/iniconfig) | 2.3.0 | MIT |
| [instructor](https://github.com/instructor-ai/instructor) | 1.15.1 | MIT |
| [Jinja2](https://github.com/pallets/jinja/) | 3.1.6 | BSD |
| [jiter](https://github.com/pydantic/jiter/) | 0.13.0 | MIT |
| [joblib](https://joblib.readthedocs.io) | 1.5.3 | BSD-3-Clause |
| [jsonpatch](https://github.com/stefankoegl/python-json-patch) | 1.33 | BSD |
| [jsonpointer](https://github.com/stefankoegl/python-json-pointer) | 3.1.1 | BSD |
| [jsonschema](https://github.com/python-jsonschema/jsonschema) | 4.26.0 | MIT |
| [jsonschema-specifications](https://github.com/python-jsonschema/jsonschema-specifications) | 2025.9.1 | MIT |
| [kubernetes](https://github.com/kubernetes-client/python) | 35.0.0 | Apache-2.0 |
| [langchain](https://docs.langchain.com/) | 1.2.17 | MIT |
| [langchain-classic](https://docs.langchain.com/) | 1.0.6 | MIT |
| [langchain-community](https://github.com/langchain-ai/langchain-community) | 0.4.1 | MIT |
| [langchain-core](https://docs.langchain.com/) | 1.3.3 | MIT |
| [langchain-openai](https://docs.langchain.com/oss/python/integrations/providers/openai) | 1.2.1 | MIT |
| [langchain-protocol](https://github.com/langchain-ai/agent-protocol/tree/main/streaming) | 0.0.15 | MIT |
| [langchain-text-splitters](https://docs.langchain.com/) | 1.1.2 | MIT |
| [langgraph](https://docs.langchain.com/oss/python/langgraph/overview) | 1.1.10 | MIT |
| [langgraph-checkpoint](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint) | 4.0.3 | MIT |
| [langgraph-prebuilt](https://github.com/langchain-ai/langgraph/tree/main/libs/prebuilt) | 1.0.13 | MIT |
| [langgraph-sdk](https://github.com/langchain-ai/langgraph/tree/main/libs/sdk-py) | 0.3.14 | MIT |
| [langsmith](https://smith.langchain.com/) | 0.8.2 | MIT |
| [lazy-loader](https://github.com/scientific-python/lazy-loader) | 0.5 | BSD-3-Clause |
| [llvmlite](http://llvmlite.readthedocs.io) | 0.47.0 | Apache-2.0 |
| [lxml](https://lxml.de/) | 6.1.0 | BSD-3-Clause |
| [magika](https://github.com/google/magika) | 0.6.2 | Apache-2.0 |
| [mammoth](https://github.com/mwilliamson/python-mammoth) | 1.11.0 | BSD |
| [markdown-it-py](https://github.com/executablebooks/markdown-it-py) | 4.0.0 | MIT |
| [markdown2](https://github.com/trentm/python-markdown2) | 2.5.5 | MIT |
| [markdownify](http://github.com/matthewwithanm/python-markdownify) | 1.2.2 | MIT |
| [markitdown](https://github.com/microsoft/markitdown) | 0.1.5 | MIT |
| [MarkupSafe](https://github.com/pallets/markupsafe/) | 3.0.3 | BSD-3-Clause |
| [marshmallow](https://github.com/marshmallow-code/marshmallow) | 3.26.2 | MIT |
| [mdurl](https://github.com/executablebooks/mdurl) | 0.1.2 | MIT |
| [mmh3](https://pypi.org/project/mmh3/) | 5.2.1 | MIT |
| [more-itertools](https://github.com/more-itertools/more-itertools) | 11.0.2 | MIT |
| [mpmath](http://mpmath.org/) | 1.3.0 | BSD |
| [multidict](https://github.com/aio-libs/multidict) | 6.7.1 | Apache-2.0 |
| [multiprocess](https://github.com/uqfoundation/multiprocess) | 0.70.19 | BSD |
| [mypy_extensions](https://github.com/python/mypy_extensions) | 1.1.0 | MIT |
| [nest-asyncio](https://github.com/erdewit/nest_asyncio) | 1.6.0 | BSD |
| [networkx](https://networkx.org/) | 3.6.1 | BSD-3-Clause |
| [ninja](http://ninja-build.org/) | 1.13.0 | BSD |
| [numba](https://numba.pydata.org) | 0.65.1 | BSD |
| [numpy](https://numpy.org) | 2.4.4 | BSD-3-Clause |
| [nvidia-ml-py](https://forums.developer.nvidia.com) | 13.595.45 | BSD |
| [oauthlib](https://github.com/oauthlib/oauthlib) | 3.3.1 | BSD-3-Clause |
| [onnxruntime](https://onnxruntime.ai) | 1.25.1 | MIT |
| [openai](https://github.com/openai/openai-python) | 2.35.1 | Apache-2.0 |
| [openai-whisper](https://github.com/openai/whisper) | 20250625 | MIT |
| [opencv-python](https://github.com/opencv/opencv-python) | 4.13.0.92 | Apache-2.0 |
| [opencv-python-headless](https://github.com/opencv/opencv-python) | 4.13.0.92 | Apache-2.0 |
| [openpyxl](https://openpyxl.readthedocs.io) | 3.1.5 | MIT |
| [opentelemetry-api](https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-api) | 1.41.1 | Apache-2.0 |
| [opentelemetry-exporter-otlp-proto-common](https://github.com/open-telemetry/opentelemetry-python/tree/main/exporter/opentelemetry-exporter-otlp-proto-common) | 1.41.1 | Apache-2.0 |
| [opentelemetry-exporter-otlp-proto-grpc](https://github.com/open-telemetry/opentelemetry-python/tree/main/exporter/opentelemetry-exporter-otlp-proto-grpc) | 1.41.1 | Apache-2.0 |
| [opentelemetry-proto](https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-proto) | 1.41.1 | Apache-2.0 |
| [opentelemetry-sdk](https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-sdk) | 1.41.1 | Apache-2.0 |
| [opentelemetry-semantic-conventions](https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-semantic-conventions) | 0.62b1 | Apache-2.0 |
| [orjson](https://github.com/ijl/orjson) | 3.11.8 | Apache-2.0 |
| [ormsgpack](https://github.com/ormsgpack/ormsgpack) | 1.12.2 | Apache-2.0 |
| [overrides](https://github.com/mkorpela/overrides) | 7.7.0 | Apache-2.0 |
| [packaging](https://github.com/pypa/packaging) | 26.2 | Apache-2.0 |
| [pandas](https://pandas.pydata.org) | 3.0.2 | BSD |
| [passlib](https://passlib.readthedocs.io) | 1.7.4 | BSD |
| [pdf2image](https://github.com/Belval/pdf2image) | 1.17.0 | MIT |
| [pdfminer.six](https://github.com/pdfminer/pdfminer.six) | 20251230 | MIT |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | 0.11.9 | MIT |
| [piexif](https://github.com/hMatoba/Piexif) | 1.1.3 | MIT |
| [pillow](https://python-pillow.github.io) | 12.2.0 | MIT |
| [playwright](https://github.com/Microsoft/playwright-python) | 1.59.0 | Apache-2.0 |
| pluggy | 1.6.0 | MIT |
| [primp](https://github.com/deedy5/primp) | 1.2.3 | MIT |
| [propcache](https://github.com/aio-libs/propcache) | 0.4.1 | Apache-2.0 |
| [protobuf](https://developers.google.com/protocol-buffers/) | 6.33.6 | BSD-3-Clause |
| [psutil](https://github.com/giampaolo/psutil) | 7.2.2 | BSD-3-Clause |
| [pyarrow](https://arrow.apache.org/) | 24.0.0 | Apache-2.0 |
| [pyasn1](https://github.com/pyasn1/pyasn1) | 0.6.3 | BSD-2-Clause |
| [pybase64](https://github.com/mayeut/pybase64) | 1.4.3 | BSD |
| [pyclipper](https://github.com/fonttools/pyclipper) | 1.4.0 | MIT |
| [pycparser](https://github.com/eliben/pycparser) | 3.0 | BSD-3-Clause |
| [pydantic](https://github.com/pydantic/pydantic) | 2.13.3 | MIT |
| [pydantic-settings](https://github.com/pydantic/pydantic-settings) | 2.14.0 | MIT |
| [pydantic_core](https://github.com/pydantic) | 2.46.3 | MIT |
| [pyee](https://github.com/jfhbrook/pyee) | 13.0.1 | MIT |
| [Pygments](https://pygments.org) | 2.20.0 | BSD-2-Clause |
| [pynvml](https://github.com/gpuopenanalytics/pynvml) | 13.0.1 | BSD |
| [PyPDF2](https://github.com/py-pdf/PyPDF2) | 3.0.1 | BSD |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | 5.8.0 | Apache-2.0 |
| [PyPika](https://github.com/kayak/pypika) | 0.51.1 | Apache-2.0 |
| [pyproject_hooks](https://github.com/pypa/pyproject-hooks) | 1.2.0 | MIT |
| [pytesseract](https://github.com/madmaze/pytesseract) | 0.3.13 | Apache-2.0 |
| [pytest](https://docs.pytest.org/en/latest/) | 9.0.3 | MIT |
| [python-bidi](https://github.com/MeirKriheli/python-bidi) | 0.6.7 | GNU Library or Lesser General Public License (LGPL) |
| [python-dateutil](https://github.com/dateutil/dateutil) | 2.9.0.post0 | BSD |
| [python-docx](https://github.com/python-openxml/python-docx) | 1.2.0 | MIT |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | 1.2.2 | BSD-3-Clause |
| [python-jose](http://github.com/mpdavis/python-jose) | 3.5.0 | MIT |
| [python-multipart](https://github.com/Kludex/python-multipart) | 0.0.27 | Apache-2.0 |
| [python-pptx](https://github.com/scanny/python-pptx) | 1.0.2 | MIT |
| [PyYAML](https://pyyaml.org/) | 6.0.3 | MIT |
| [ragas](https://github.com/vibrantlabsai/ragas) | 0.4.3 | Apache-2.0 |
| [rank-bm25](https://github.com/dorianbrown/rank_bm25) | 0.2.2 | Apache-2.0 |
| [referencing](https://github.com/python-jsonschema/referencing) | 0.37.0 | MIT |
| [regex](https://github.com/mrabarnett/mrab-regex) | 2026.4.4 | Apache-2.0 |
| [requests](https://github.com/psf/requests) | 2.33.1 | Apache-2.0 |
| [requests-oauthlib](https://github.com/requests/requests-oauthlib) | 2.0.0 | BSD |
| [requests-toolbelt](https://toolbelt.readthedocs.io/) | 1.0.0 | Apache-2.0 |
| [rich](https://github.com/Textualize/rich) | 14.3.4 | MIT |
| [rpds-py](https://github.com/crate-py/rpds) | 0.30.0 | MIT |
| [rsa](https://stuvel.eu/rsa) | 4.9.1 | Apache-2.0 |
| [ruff](https://docs.astral.sh/ruff) | 0.15.12 | MIT |
| [safetensors](https://github.com/huggingface/safetensors) | 0.7.0 | Apache-2.0 |
| [scikit-image](https://scikit-image.org) | 0.26.0 | BSD |
| [scikit-learn](https://scikit-learn.org) | 1.8.0 | BSD-3-Clause |
| [scikit-network](https://github.com/sknetwork-team/scikit-network) | 0.12.1 | BSD |
| [scipy](https://scipy.org/) | 1.17.1 | BSD |
| [sentence-transformers](https://www.SBERT.net) | 5.4.1 | Apache-2.0 |
| [shapely](https://github.com/shapely/shapely) | 2.1.2 | BSD |
| [shellingham](https://github.com/sarugaku/shellingham) | 1.5.4 | ISC |
| [six](https://github.com/benjaminp/six) | 1.17.0 | MIT |
| [sniffio](https://github.com/python-trio/sniffio) | 1.3.1 | Apache Software License; MIT License |
| [soupsieve](https://github.com/facelessuser/soupsieve) | 2.8.3 | MIT |
| [SQLAlchemy](https://www.sqlalchemy.org) | 2.0.49 | MIT |
| [starlette](https://github.com/Kludex/starlette) | 1.0.0 | BSD-3-Clause |
| [sympy](https://sympy.org) | 1.14.0 | BSD |
| [tavily-python](https://github.com/tavily-ai/tavily-python) | 0.7.24 | MIT |
| [tenacity](https://github.com/jd/tenacity) | 9.1.4 | Apache-2.0 |
| [threadpoolctl](https://github.com/joblib/threadpoolctl) | 3.6.0 | BSD |
| [tifffile](https://www.cgohlke.com) | 2026.4.11 | BSD-3-Clause |
| [tiktoken](https://github.com/openai/tiktoken) | 0.12.0 | MIT |
| [tokenizers](https://github.com/huggingface/tokenizers) | 0.22.2 | Apache-2.0 |
| [torch](https://pytorch.org) | 2.11.0 | BSD-3-Clause |
| [torchvision](https://github.com/pytorch/vision) | 0.26.0 | BSD |
| [tqdm](https://tqdm.github.io) | 4.67.3 | MPL-2.0 |
| [transformers](https://github.com/huggingface/transformers) | 5.7.0 | Apache-2.0 |
| [typer](https://github.com/fastapi/typer) | 0.25.1 | MIT |
| [typing-inspect](https://github.com/ilevkivskyi/typing_inspect) | 0.9.0 | MIT |
| [typing-inspection](https://github.com/pydantic/typing-inspection) | 0.4.2 | MIT |
| [typing_extensions](https://github.com/python/typing_extensions) | 4.15.0 | PSF-2.0 |
| [tzdata](https://github.com/python/tzdata) | 2026.2 | Apache-2.0 |
| [urllib3](https://github.com/urllib3/urllib3/blob/main/CHANGES.rst) | 2.7.0 | MIT |
| [uuid_utils](https://github.com/aminalaee/uuid-utils) | 0.14.1 | BSD-3-Clause |
| [uvicorn](https://uvicorn.dev/) | 0.46.0 | BSD-3-Clause |
| [watchfiles](https://github.com/samuelcolvin/watchfiles) | 1.1.1 | MIT |
| [websocket-client](https://github.com/websocket-client/websocket-client.git) | 1.9.0 | Apache-2.0 |
| [websockets](https://github.com/python-websockets/websockets) | 16.0 | BSD-3-Clause |
| [xlsxwriter](https://github.com/jmcnamara/XlsxWriter) | 3.2.9 | BSD |
| [xxhash](https://github.com/ifduyue/python-xxhash) | 3.7.0 | BSD |
| [yarl](https://github.com/aio-libs/yarl) | 1.23.0 | Apache-2.0 |
| [zipp](https://github.com/jaraco/zipp) | 3.23.1 | MIT |
| [zstandard](https://github.com/indygreg/python-zstandard) | 0.25.0 | BSD-3-Clause |
