# Third-Party Licenses

> **Generated**: 2026-05-13
> **Source**: `requirements_pinned.txt` (production dependencies)
> **Tool**: `pip-licenses --format=markdown --with-urls --from=mixed`

본 문서는 JAMES 가 의존하는 외부 패키지들의 라이선스 인벤토리입니다. 
라이선스 강도(MIT / AGPL 등)와 무관하게 모든 OSS 프로젝트가 갖춰야 할 위생 문서이며, 
분기 1회 또는 `requirements_pinned.txt` 변경 시 재생성합니다.

## Regenerate

```bash
pip install pip-licenses
pip-licenses --format=markdown --with-urls --order=license --from=mixed > THIRD_PARTY_LICENSES.md
```

복수 라이선스(예: `Apache-2.0 OR BSD-2-Clause`)는 SPDX 표기를 그대로 보존합니다. 
라이선스 본문 전체가 메타데이터에 임베드된 패키지(`ragas`, `tiktoken`)는 
본 표에서 첫 줄만 보존하고, 본문은 해당 패키지의 PyPI 페이지를 참조하세요.

## Inventory

Total packages: **201**

| Name | Version | License | URL |
|---|---|---|---|
| protobuf | 6.33.6 | 3-Clause BSD License | [https://developers.google.com/protocol-buffers/](https://developers.google.com/protocol-buffers/) |
| transformers | 5.7.0 | Apache 2.0 License | [https://github.com/huggingface/transformers](https://github.com/huggingface/transformers) |
| ragas | 0.4.3 | Apache License | [https://github.com/vibrantlabsai/ragas](https://github.com/vibrantlabsai/ragas) |
| easyocr | 1.7.2 | Apache License 2.0 | [https://github.com/jaidedai/easyocr](https://github.com/jaidedai/easyocr) |
| multidict | 6.7.1 | Apache License 2.0 | [https://github.com/aio-libs/multidict](https://github.com/aio-libs/multidict) |
| overrides | 7.7.0 | Apache License, Version 2.0 | [https://github.com/mkorpela/overrides](https://github.com/mkorpela/overrides) |
| aiosignal | 1.4.0 | Apache Software License | [https://github.com/aio-libs/aiosignal](https://github.com/aio-libs/aiosignal) |
| bcrypt | 5.0.0 | Apache Software License | [https://github.com/pyca/bcrypt/](https://github.com/pyca/bcrypt/) |
| chromadb | 1.5.8 | Apache Software License | [https://github.com/chroma-core/chroma](https://github.com/chroma-core/chroma) |
| datasets | 4.8.5 | Apache Software License | [https://github.com/huggingface/datasets](https://github.com/huggingface/datasets) |
| diskcache | 5.6.3 | Apache Software License | [http://www.grantjenks.com/docs/diskcache/](http://www.grantjenks.com/docs/diskcache/) |
| distro | 1.9.0 | Apache Software License | [https://github.com/python-distro/distro](https://github.com/python-distro/distro) |
| ffmpeg-python | 0.2.0 | Apache Software License | [https://github.com/kkroening/ffmpeg-python](https://github.com/kkroening/ffmpeg-python) |
| flatbuffers | 25.12.19 | Apache Software License | [https://google.github.io/flatbuffers/](https://google.github.io/flatbuffers/) |
| googleapis-common-protos | 1.74.0 | Apache Software License | [https://github.com/googleapis/google-cloud-python/tree/main/packages/googleapis-common-protos](https://github.com/googleapis/google-cloud-python/tree/main/packages/googleapis-common-protos) |
| huggingface_hub | 1.13.0 | Apache Software License | [https://github.com/huggingface/huggingface_hub](https://github.com/huggingface/huggingface_hub) |
| kubernetes | 35.0.0 | Apache Software License | [https://github.com/kubernetes-client/python](https://github.com/kubernetes-client/python) |
| magika | 0.6.2 | Apache Software License | [https://github.com/google/magika](https://github.com/google/magika) |
| openai | 2.35.1 | Apache Software License | [https://github.com/openai/openai-python](https://github.com/openai/openai-python) |
| opencv-python | 4.13.0.92 | Apache Software License | [https://github.com/opencv/opencv-python](https://github.com/opencv/opencv-python) |
| opencv-python-headless | 4.13.0.92 | Apache Software License | [https://github.com/opencv/opencv-python](https://github.com/opencv/opencv-python) |
| propcache | 0.4.1 | Apache Software License | [https://github.com/aio-libs/propcache](https://github.com/aio-libs/propcache) |
| PyPika | 0.51.1 | Apache Software License | [https://github.com/kayak/pypika](https://github.com/kayak/pypika) |
| pytesseract | 0.3.13 | Apache Software License | [https://github.com/madmaze/pytesseract](https://github.com/madmaze/pytesseract) |
| requests | 2.33.1 | Apache Software License | [https://github.com/psf/requests](https://github.com/psf/requests) |
| requests-toolbelt | 1.0.0 | Apache Software License | [https://toolbelt.readthedocs.io/](https://toolbelt.readthedocs.io/) |
| rsa | 4.9.1 | Apache Software License | [https://stuvel.eu/rsa](https://stuvel.eu/rsa) |
| safetensors | 0.7.0 | Apache Software License | [https://github.com/huggingface/safetensors](https://github.com/huggingface/safetensors) |
| sentence-transformers | 5.4.1 | Apache Software License | [https://www.SBERT.net](https://www.SBERT.net) |
| tenacity | 9.1.4 | Apache Software License | [https://github.com/jd/tenacity](https://github.com/jd/tenacity) |
| tokenizers | 0.22.2 | Apache Software License | [https://github.com/huggingface/tokenizers](https://github.com/huggingface/tokenizers) |
| websocket-client | 1.9.0 | Apache Software License | [https://github.com/websocket-client/websocket-client.git](https://github.com/websocket-client/websocket-client.git) |
| ninja | 1.13.0 | Apache Software License; BSD License | [http://ninja-build.org/](http://ninja-build.org/) |
| python-dateutil | 2.9.0.post0 | Apache Software License; BSD License | [https://github.com/dateutil/dateutil](https://github.com/dateutil/dateutil) |
| sniffio | 1.3.1 | Apache Software License; MIT License | [https://github.com/python-trio/sniffio](https://github.com/python-trio/sniffio) |
| frozenlist | 1.8.0 | Apache-2.0 | [https://github.com/aio-libs/frozenlist](https://github.com/aio-libs/frozenlist) |
| grpcio | 1.80.0 | Apache-2.0 | [https://grpc.io](https://grpc.io) |
| hf-xet | 1.4.3 | Apache-2.0 | [https://github.com/huggingface/xet-core](https://github.com/huggingface/xet-core) |
| importlib_metadata | 8.7.1 | Apache-2.0 | [https://github.com/python/importlib_metadata](https://github.com/python/importlib_metadata) |
| importlib_resources | 7.1.0 | Apache-2.0 | [https://github.com/python/importlib_resources](https://github.com/python/importlib_resources) |
| opentelemetry-api | 1.41.1 | Apache-2.0 | [https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-api](https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-api) |
| opentelemetry-exporter-otlp-proto-common | 1.41.1 | Apache-2.0 | [https://github.com/open-telemetry/opentelemetry-python/tree/main/exporter/opentelemetry-exporter-otlp-proto-common](https://github.com/open-telemetry/opentelemetry-python/tree/main/exporter/opentelemetry-exporter-otlp-proto-common) |
| opentelemetry-exporter-otlp-proto-grpc | 1.41.1 | Apache-2.0 | [https://github.com/open-telemetry/opentelemetry-python/tree/main/exporter/opentelemetry-exporter-otlp-proto-grpc](https://github.com/open-telemetry/opentelemetry-python/tree/main/exporter/opentelemetry-exporter-otlp-proto-grpc) |
| opentelemetry-proto | 1.41.1 | Apache-2.0 | [https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-proto](https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-proto) |
| opentelemetry-sdk | 1.41.1 | Apache-2.0 | [https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-sdk](https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-sdk) |
| opentelemetry-semantic-conventions | 0.62b1 | Apache-2.0 | [https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-semantic-conventions](https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-semantic-conventions) |
| playwright | 1.59.0 | Apache-2.0 | [https://github.com/Microsoft/playwright-python](https://github.com/Microsoft/playwright-python) |
| pyarrow | 24.0.0 | Apache-2.0 | [https://arrow.apache.org/](https://arrow.apache.org/) |
| python-multipart | 0.0.27 | Apache-2.0 | [https://github.com/Kludex/python-multipart](https://github.com/Kludex/python-multipart) |
| tzdata | 2026.2 | Apache-2.0 | [https://github.com/python/tzdata](https://github.com/python/tzdata) |
| yarl | 1.23.0 | Apache-2.0 | [https://github.com/aio-libs/yarl](https://github.com/aio-libs/yarl) |
| regex | 2026.4.4 | Apache-2.0 AND CNRI-Python | [https://github.com/mrabarnett/mrab-regex](https://github.com/mrabarnett/mrab-regex) |
| aiohttp | 3.13.5 | Apache-2.0 AND MIT | [https://github.com/aio-libs/aiohttp](https://github.com/aio-libs/aiohttp) |
| packaging | 26.2 | Apache-2.0 OR BSD-2-Clause | [https://github.com/pypa/packaging](https://github.com/pypa/packaging) |
| cryptography | 47.0.0 | Apache-2.0 OR BSD-3-Clause | [https://github.com/pyca/cryptography](https://github.com/pyca/cryptography) |
| ormsgpack | 1.12.2 | Apache-2.0 OR MIT | [https://github.com/ormsgpack/ormsgpack](https://github.com/ormsgpack/ormsgpack) |
| rank-bm25 | 0.2.2 | Apache2.0 | [https://github.com/dorianbrown/rank_bm25](https://github.com/dorianbrown/rank_bm25) |
| passlib | 1.7.4 | BSD | [https://passlib.readthedocs.io](https://passlib.readthedocs.io) |
| torchvision | 0.26.0 | BSD | [https://github.com/pytorch/vision](https://github.com/pytorch/vision) |
| cobble | 0.1.4 | BSD License | [http://github.com/mwilliamson/python-cobble](http://github.com/mwilliamson/python-cobble) |
| colorama | 0.4.6 | BSD License | [https://github.com/tartley/colorama](https://github.com/tartley/colorama) |
| dill | 0.4.1 | BSD License | [https://github.com/uqfoundation/dill](https://github.com/uqfoundation/dill) |
| httpx | 0.28.1 | BSD License | [https://github.com/encode/httpx](https://github.com/encode/httpx) |
| Jinja2 | 3.1.6 | BSD License | [https://github.com/pallets/jinja/](https://github.com/pallets/jinja/) |
| jsonpatch | 1.33 | BSD License | [https://github.com/stefankoegl/python-json-patch](https://github.com/stefankoegl/python-json-patch) |
| jsonpointer | 3.1.1 | BSD License | [https://github.com/stefankoegl/python-json-pointer](https://github.com/stefankoegl/python-json-pointer) |
| mammoth | 1.11.0 | BSD License | [https://github.com/mwilliamson/python-mammoth](https://github.com/mwilliamson/python-mammoth) |
| mpmath | 1.3.0 | BSD License | [http://mpmath.org/](http://mpmath.org/) |
| multiprocess | 0.70.19 | BSD License | [https://github.com/uqfoundation/multiprocess](https://github.com/uqfoundation/multiprocess) |
| nest-asyncio | 1.6.0 | BSD License | [https://github.com/erdewit/nest_asyncio](https://github.com/erdewit/nest_asyncio) |
| numba | 0.65.1 | BSD License | [https://numba.pydata.org](https://numba.pydata.org) |
| nvidia-ml-py | 13.595.45 | BSD License | [https://forums.developer.nvidia.com](https://forums.developer.nvidia.com) |
| pandas | 3.0.2 | BSD License | [https://pandas.pydata.org](https://pandas.pydata.org) |
| pybase64 | 1.4.3 | BSD License | [https://github.com/mayeut/pybase64](https://github.com/mayeut/pybase64) |
| pynvml | 13.0.1 | BSD License | [https://github.com/gpuopenanalytics/pynvml](https://github.com/gpuopenanalytics/pynvml) |
| PyPDF2 | 3.0.1 | BSD License | [https://github.com/py-pdf/PyPDF2](https://github.com/py-pdf/PyPDF2) |
| requests-oauthlib | 2.0.0 | BSD License | [https://github.com/requests/requests-oauthlib](https://github.com/requests/requests-oauthlib) |
| scikit-image | 0.26.0 | BSD License | [https://scikit-image.org](https://scikit-image.org) |
| scikit-network | 0.12.1 | BSD License | [https://github.com/sknetwork-team/scikit-network](https://github.com/sknetwork-team/scikit-network) |
| scipy | 1.17.1 | BSD License | [https://scipy.org/](https://scipy.org/) |
| shapely | 2.1.2 | BSD License | [https://github.com/shapely/shapely](https://github.com/shapely/shapely) |
| sympy | 1.14.0 | BSD License | [https://sympy.org](https://sympy.org) |
| threadpoolctl | 3.6.0 | BSD License | [https://github.com/joblib/threadpoolctl](https://github.com/joblib/threadpoolctl) |
| xlsxwriter | 3.2.9 | BSD License | [https://github.com/jmcnamara/XlsxWriter](https://github.com/jmcnamara/XlsxWriter) |
| xxhash | 3.7.0 | BSD License | [https://github.com/ifduyue/python-xxhash](https://github.com/ifduyue/python-xxhash) |
| ImageIO | 2.37.3 | BSD-2-Clause | [https://github.com/imageio/imageio](https://github.com/imageio/imageio) |
| pyasn1 | 0.6.3 | BSD-2-Clause | [https://github.com/pyasn1/pyasn1](https://github.com/pyasn1/pyasn1) |
| Pygments | 2.20.0 | BSD-2-Clause | [https://pygments.org](https://pygments.org) |
| llvmlite | 0.47.0 | BSD-2-Clause AND Apache-2.0 WITH LLVM-exception | [http://llvmlite.readthedocs.io](http://llvmlite.readthedocs.io) |
| click | 8.3.3 | BSD-3-Clause | [https://github.com/pallets/click/](https://github.com/pallets/click/) |
| fsspec | 2026.2.0 | BSD-3-Clause | [https://github.com/fsspec/filesystem_spec](https://github.com/fsspec/filesystem_spec) |
| httpcore | 1.0.9 | BSD-3-Clause | [https://www.encode.io/httpcore/](https://www.encode.io/httpcore/) |
| idna | 3.13 | BSD-3-Clause | [https://github.com/kjd/idna](https://github.com/kjd/idna) |
| joblib | 1.5.3 | BSD-3-Clause | [https://joblib.readthedocs.io](https://joblib.readthedocs.io) |
| lazy-loader | 0.5 | BSD-3-Clause | [https://github.com/scientific-python/lazy-loader](https://github.com/scientific-python/lazy-loader) |
| lxml | 6.1.0 | BSD-3-Clause | [https://lxml.de/](https://lxml.de/) |
| MarkupSafe | 3.0.3 | BSD-3-Clause | [https://github.com/pallets/markupsafe/](https://github.com/pallets/markupsafe/) |
| networkx | 3.6.1 | BSD-3-Clause | [https://networkx.org/](https://networkx.org/) |
| oauthlib | 3.3.1 | BSD-3-Clause | [https://github.com/oauthlib/oauthlib](https://github.com/oauthlib/oauthlib) |
| psutil | 7.2.2 | BSD-3-Clause | [https://github.com/giampaolo/psutil](https://github.com/giampaolo/psutil) |
| pycparser | 3.0 | BSD-3-Clause | [https://github.com/eliben/pycparser](https://github.com/eliben/pycparser) |
| python-dotenv | 1.2.2 | BSD-3-Clause | [https://github.com/theskumar/python-dotenv](https://github.com/theskumar/python-dotenv) |
| scikit-learn | 1.8.0 | BSD-3-Clause | [https://scikit-learn.org](https://scikit-learn.org) |
| starlette | 1.0.0 | BSD-3-Clause | [https://github.com/Kludex/starlette](https://github.com/Kludex/starlette) |
| tifffile | 2026.4.11 | BSD-3-Clause | [https://www.cgohlke.com](https://www.cgohlke.com) |
| torch | 2.11.0 | BSD-3-Clause | [https://pytorch.org](https://pytorch.org) |
| uuid_utils | 0.14.1 | BSD-3-Clause | [https://github.com/aminalaee/uuid-utils](https://github.com/aminalaee/uuid-utils) |
| uvicorn | 0.46.0 | BSD-3-Clause | [https://uvicorn.dev/](https://uvicorn.dev/) |
| websockets | 16.0 | BSD-3-Clause | [https://github.com/python-websockets/websockets](https://github.com/python-websockets/websockets) |
| zstandard | 0.25.0 | BSD-3-Clause | [https://github.com/indygreg/python-zstandard](https://github.com/indygreg/python-zstandard) |
| numpy | 2.4.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | [https://numpy.org](https://numpy.org) |
| pypdfium2 | 5.8.0 | BSD-3-Clause, Apache-2.0, dependency licenses | [https://github.com/pypdfium2-team/pypdfium2](https://github.com/pypdfium2-team/pypdfium2) |
| python-bidi | 0.6.7 | GNU Library or Lesser General Public License (LGPL) | [https://github.com/MeirKriheli/python-bidi](https://github.com/MeirKriheli/python-bidi) |
| shellingham | 1.5.4 | ISC License (ISCL) | [https://github.com/sarugaku/shellingham](https://github.com/sarugaku/shellingham) |
| annotated-doc | 0.0.4 | MIT | [https://github.com/fastapi/annotated-doc](https://github.com/fastapi/annotated-doc) |
| anyio | 4.13.0 | MIT | [https://anyio.readthedocs.io/en/stable/versionhistory.html](https://anyio.readthedocs.io/en/stable/versionhistory.html) |
| attrs | 26.1.0 | MIT | [https://www.attrs.org/en/stable/changelog.html](https://www.attrs.org/en/stable/changelog.html) |
| build | 1.5.0 | MIT | [https://build.pypa.io](https://build.pypa.io) |
| cffi | 2.0.0 | MIT | [https://cffi.readthedocs.io/en/latest/whatsnew.html](https://cffi.readthedocs.io/en/latest/whatsnew.html) |
| charset-normalizer | 3.4.7 | MIT | [https://github.com/jawah/charset_normalizer/blob/master/CHANGELOG.md](https://github.com/jawah/charset_normalizer/blob/master/CHANGELOG.md) |
| durationpy | 0.10 | MIT | [https://github.com/icholy/durationpy](https://github.com/icholy/durationpy) |
| ecdsa | 0.19.2 | MIT | [http://github.com/tlsfuzzer/python-ecdsa](http://github.com/tlsfuzzer/python-ecdsa) |
| fastapi | 0.136.1 | MIT | [https://github.com/fastapi/fastapi](https://github.com/fastapi/fastapi) |
| filelock | 3.29.0 | MIT | [https://github.com/tox-dev/py-filelock](https://github.com/tox-dev/py-filelock) |
| httptools | 0.7.1 | MIT | [https://github.com/MagicStack/httptools](https://github.com/MagicStack/httptools) |
| httpx-sse | 0.4.3 | MIT | [https://github.com/florimondmanca/httpx-sse](https://github.com/florimondmanca/httpx-sse) |
| instructor | 1.15.1 | MIT | [https://github.com/instructor-ai/instructor](https://github.com/instructor-ai/instructor) |
| jsonschema | 4.26.0 | MIT | [https://github.com/python-jsonschema/jsonschema](https://github.com/python-jsonschema/jsonschema) |
| jsonschema-specifications | 2025.9.1 | MIT | [https://github.com/python-jsonschema/jsonschema-specifications](https://github.com/python-jsonschema/jsonschema-specifications) |
| langchain-community | 0.4.1 | MIT | [https://github.com/langchain-ai/langchain-community](https://github.com/langchain-ai/langchain-community) |
| langgraph | 1.1.10 | MIT | [https://docs.langchain.com/oss/python/langgraph/overview](https://docs.langchain.com/oss/python/langgraph/overview) |
| langgraph-checkpoint | 4.0.3 | MIT | [https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint) |
| langgraph-prebuilt | 1.0.13 | MIT | [https://github.com/langchain-ai/langgraph/tree/main/libs/prebuilt](https://github.com/langchain-ai/langgraph/tree/main/libs/prebuilt) |
| langgraph-sdk | 0.3.14 | MIT | [https://github.com/langchain-ai/langgraph/tree/main/libs/sdk-py](https://github.com/langchain-ai/langgraph/tree/main/libs/sdk-py) |
| langsmith | 0.8.2 | MIT | [https://smith.langchain.com/](https://smith.langchain.com/) |
| markdown2 | 2.5.5 | MIT | [https://github.com/trentm/python-markdown2](https://github.com/trentm/python-markdown2) |
| markitdown | 0.1.5 | MIT | [https://github.com/microsoft/markitdown](https://github.com/microsoft/markitdown) |
| more-itertools | 11.0.2 | MIT | [https://github.com/more-itertools/more-itertools](https://github.com/more-itertools/more-itertools) |
| mypy_extensions | 1.1.0 | MIT | [https://github.com/python/mypy_extensions](https://github.com/python/mypy_extensions) |
| openai-whisper | 20250625 | MIT | [https://github.com/openai/whisper](https://github.com/openai/whisper) |
| pdfminer.six | 20251230 | MIT | [https://github.com/pdfminer/pdfminer.six](https://github.com/pdfminer/pdfminer.six) |
| pydantic | 2.13.3 | MIT | [https://github.com/pydantic/pydantic](https://github.com/pydantic/pydantic) |
| pydantic-settings | 2.14.0 | MIT | [https://github.com/pydantic/pydantic-settings](https://github.com/pydantic/pydantic-settings) |
| pydantic_core | 2.46.3 | MIT | [https://github.com/pydantic](https://github.com/pydantic) |
| referencing | 0.37.0 | MIT | [https://github.com/python-jsonschema/referencing](https://github.com/python-jsonschema/referencing) |
| rpds-py | 0.30.0 | MIT | [https://github.com/crate-py/rpds](https://github.com/crate-py/rpds) |
| ruff | 0.15.12 | MIT | [https://docs.astral.sh/ruff](https://docs.astral.sh/ruff) |
| soupsieve | 2.8.3 | MIT | [https://github.com/facelessuser/soupsieve](https://github.com/facelessuser/soupsieve) |
| SQLAlchemy | 2.0.49 | MIT | [https://www.sqlalchemy.org](https://www.sqlalchemy.org) |
| typer | 0.25.1 | MIT | [https://github.com/fastapi/typer](https://github.com/fastapi/typer) |
| typing-inspection | 0.4.2 | MIT | [https://github.com/pydantic/typing-inspection](https://github.com/pydantic/typing-inspection) |
| urllib3 | 2.7.0 | MIT | [https://github.com/urllib3/urllib3/blob/main/CHANGES.rst](https://github.com/urllib3/urllib3/blob/main/CHANGES.rst) |
| zipp | 3.23.1 | MIT | [https://github.com/jaraco/zipp](https://github.com/jaraco/zipp) |
| greenlet | 3.5.0 | MIT AND PSF-2.0 | [https://greenlet.readthedocs.io](https://greenlet.readthedocs.io) |
| annotated-types | 0.7.0 | MIT License | [https://github.com/annotated-types/annotated-types](https://github.com/annotated-types/annotated-types) |
| appdirs | 1.4.4 | MIT License | [http://github.com/ActiveState/appdirs](http://github.com/ActiveState/appdirs) |
| beautifulsoup4 | 4.14.3 | MIT License | [https://www.crummy.com/software/BeautifulSoup/bs4/](https://www.crummy.com/software/BeautifulSoup/bs4/) |
| dataclasses-json | 0.6.7 | MIT License | [https://github.com/lidatong/dataclasses-json](https://github.com/lidatong/dataclasses-json) |
| docstring_parser | 0.18.0 | MIT License | [https://github.com/rr-/docstring_parser](https://github.com/rr-/docstring_parser) |
| duckduckgo_search | 8.1.1 | MIT License | [https://github.com/deedy5/duckduckgo_search](https://github.com/deedy5/duckduckgo_search) |
| et_xmlfile | 2.0.0 | MIT License | [https://foss.heptapod.net/openpyxl/et_xmlfile](https://foss.heptapod.net/openpyxl/et_xmlfile) |
| future | 1.0.0 | MIT License | [https://python-future.org](https://python-future.org) |
| h11 | 0.16.0 | MIT License | [https://github.com/python-hyper/h11](https://github.com/python-hyper/h11) |
| jiter | 0.13.0 | MIT License | [https://github.com/pydantic/jiter/](https://github.com/pydantic/jiter/) |
| langchain | 1.2.17 | MIT License | [https://docs.langchain.com/](https://docs.langchain.com/) |
| langchain-classic | 1.0.6 | MIT License | [https://docs.langchain.com/](https://docs.langchain.com/) |
| langchain-core | 1.3.3 | MIT License | [https://docs.langchain.com/](https://docs.langchain.com/) |
| langchain-openai | 1.2.1 | MIT License | [https://docs.langchain.com/oss/python/integrations/providers/openai](https://docs.langchain.com/oss/python/integrations/providers/openai) |
| langchain-protocol | 0.0.15 | MIT License | [https://github.com/langchain-ai/agent-protocol/tree/main/streaming](https://github.com/langchain-ai/agent-protocol/tree/main/streaming) |
| langchain-text-splitters | 1.1.2 | MIT License | [https://docs.langchain.com/](https://docs.langchain.com/) |
| markdown-it-py | 4.0.0 | MIT License | [https://github.com/executablebooks/markdown-it-py](https://github.com/executablebooks/markdown-it-py) |
| markdownify | 1.2.2 | MIT License | [http://github.com/matthewwithanm/python-markdownify](http://github.com/matthewwithanm/python-markdownify) |
| marshmallow | 3.26.2 | MIT License | [https://github.com/marshmallow-code/marshmallow](https://github.com/marshmallow-code/marshmallow) |
| mdurl | 0.1.2 | MIT License | [https://github.com/executablebooks/mdurl](https://github.com/executablebooks/mdurl) |
| mmh3 | 5.2.1 | MIT License | [https://pypi.org/project/mmh3/](https://pypi.org/project/mmh3/) |
| onnxruntime | 1.25.1 | MIT License | [https://onnxruntime.ai](https://onnxruntime.ai) |
| openpyxl | 3.1.5 | MIT License | [https://openpyxl.readthedocs.io](https://openpyxl.readthedocs.io) |
| pdf2image | 1.17.0 | MIT License | [https://github.com/Belval/pdf2image](https://github.com/Belval/pdf2image) |
| pdfplumber | 0.11.9 | MIT License | [https://github.com/jsvine/pdfplumber](https://github.com/jsvine/pdfplumber) |
| piexif | 1.1.3 | MIT License | [https://github.com/hMatoba/Piexif](https://github.com/hMatoba/Piexif) |
| primp | 1.2.3 | MIT License | [https://github.com/deedy5/primp](https://github.com/deedy5/primp) |
| pyclipper | 1.4.0 | MIT License | [https://github.com/fonttools/pyclipper](https://github.com/fonttools/pyclipper) |
| pyee | 13.0.1 | MIT License | [https://github.com/jfhbrook/pyee](https://github.com/jfhbrook/pyee) |
| pyproject_hooks | 1.2.0 | MIT License | [https://github.com/pypa/pyproject-hooks](https://github.com/pypa/pyproject-hooks) |
| python-docx | 1.2.0 | MIT License | [https://github.com/python-openxml/python-docx](https://github.com/python-openxml/python-docx) |
| python-jose | 3.5.0 | MIT License | [http://github.com/mpdavis/python-jose](http://github.com/mpdavis/python-jose) |
| python-pptx | 1.0.2 | MIT License | [https://github.com/scanny/python-pptx](https://github.com/scanny/python-pptx) |
| PyYAML | 6.0.3 | MIT License | [https://pyyaml.org/](https://pyyaml.org/) |
| rich | 14.3.4 | MIT License | [https://github.com/Textualize/rich](https://github.com/Textualize/rich) |
| six | 1.17.0 | MIT License | [https://github.com/benjaminp/six](https://github.com/benjaminp/six) |
| tavily-python | 0.7.24 | MIT License | [https://github.com/tavily-ai/tavily-python](https://github.com/tavily-ai/tavily-python) |
| tiktoken | 0.12.0 | MIT License | [https://github.com/openai/tiktoken](https://github.com/openai/tiktoken) |
| typing-inspect | 0.9.0 | MIT License | [https://github.com/ilevkivskyi/typing_inspect](https://github.com/ilevkivskyi/typing_inspect) |
| watchfiles | 1.1.1 | MIT License | [https://github.com/samuelcolvin/watchfiles](https://github.com/samuelcolvin/watchfiles) |
| pillow | 12.2.0 | MIT-CMU | [https://python-pillow.github.io](https://python-pillow.github.io) |
| certifi | 2026.4.22 | Mozilla Public License 2.0 (MPL 2.0) | [https://github.com/certifi/python-certifi](https://github.com/certifi/python-certifi) |
| orjson | 3.11.8 | MPL-2.0 AND (Apache-2.0 OR MIT) | [https://github.com/ijl/orjson](https://github.com/ijl/orjson) |
| tqdm | 4.67.3 | MPL-2.0 AND MIT | [https://tqdm.github.io](https://tqdm.github.io) |
| typing_extensions | 4.15.0 | PSF-2.0 | [https://github.com/python/typing_extensions](https://github.com/python/typing_extensions) |
| aiohappyeyeballs | 2.6.1 | Python Software Foundation License | [https://github.com/aio-libs/aiohappyeyeballs](https://github.com/aio-libs/aiohappyeyeballs) |
| defusedxml | 0.7.1 | Python Software Foundation License | [https://github.com/tiran/defusedxml](https://github.com/tiran/defusedxml) |

---

**Compliance note**: JAMES is MIT licensed. Compatibility check 
for all listed dependencies is performed manually at major-version 
bumps. Copyleft (AGPL/GPL) dependencies, if any, would be flagged 
during this review and either replaced or isolated to optional packs.
