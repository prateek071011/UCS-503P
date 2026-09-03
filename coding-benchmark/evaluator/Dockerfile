FROM python:3.12-slim

WORKDIR /sandbox

RUN pip install --no-cache-dir numpy

RUN useradd --create-home --uid 10001 runner
USER runner

ENTRYPOINT ["python"]
